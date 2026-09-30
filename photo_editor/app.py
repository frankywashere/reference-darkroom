from __future__ import annotations

# Capability reported by the running process, not inferred from static files.
MASK_ENGINE_VERSION = 2

import json
import asyncio
import hashlib
import os
import subprocess
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from catalog import Catalog

from engine import (DEFAULT_RECIPE, IMAGE_SUFFIXES, PRESETS, clipping_stats,
                    embedded_thumbnail, half_float_rgba, jpeg_bytes, load_image,
                    path_id, process, resize_linear)


HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('REFERENCE_DARKROOM_DATA', str(HERE / 'editor_data')))
CACHE = DATA / "cache"
PROJECTS = DATA / "projects"
EXPORTS = DATA / "exports"
for directory in (CACHE, PROJECTS, EXPORTS):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Reference Darkroom", version="1.0")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
pool = ThreadPoolExecutor(max_workers=2)
jobs: dict[str, dict[str, Any]] = {}
jobs_lock = threading.Lock()
preview_cache: OrderedDict[tuple[str, int, int], tuple[Any, int]] = OrderedDict()
preview_cache_lock = threading.Lock()
# Serialize full-resolution uploads so fast photo switching cannot decode many
# full RAW buffers concurrently. The browser retains only its active texture.
resident_decode_lock = threading.Lock()
gpu_decode_lock = asyncio.Lock()
PREVIEW_CACHE_MAX_BYTES = 192 * 1024 * 1024
PREVIEW_MASTER_SIDE = 1800
DRAFT_PREVIEW_SIDE = 900
catalog = Catalog(DATA / 'catalog', Path(os.environ.get('REFERENCE_DARKROOM_PROJECTS', str(Path.home() / 'Pictures' / 'Reference Darkroom Projects'))))
from preview_cache import PreviewCache
screen_previews = PreviewCache(DATA / 'screen_previews', hashlib.sha256((HERE/'static/gpu-engine.js').read_bytes()).hexdigest())
from import_jobs import ImportJobs
imports = ImportJobs(catalog)


class PreviewRequest(BaseModel):
    path: str
    recipe: dict[str, Any] = {}
    apply_crop: bool = False
    max_side: int = 1800
    draft: bool = False


class StatsRequest(BaseModel):
    path: str
    recipe: dict[str, Any] = {}


class SaveProjectRequest(BaseModel):
    source: str
    project_id: str | None = None
    photos: dict[str, Any]
    selected: str | None = None


class ExportRequest(BaseModel):
    items: list[dict[str, Any]]
    destination: str | None = None
    quality: int = 96
    prefix: str = "EDIT_"


def _safe_project_name(source: str) -> str:
    return path_id(source)


def _project_file(source: str) -> Path:
    return PROJECTS / f"{_safe_project_name(source)}.json"


def _preview_source(path: str) -> tuple[Any, bool]:
    """Return a copied, decoded preview master and whether it was cached."""
    source = Path(path).expanduser().resolve()
    stat = source.stat()
    key = (str(source), stat.st_mtime_ns, stat.st_size)
    with preview_cache_lock:
        cached = preview_cache.get(key)
        if cached is not None:
            preview_cache.move_to_end(key)
            return cached[0].copy(), True

    image = load_image(source, max_side=PREVIEW_MASTER_SIDE)
    estimated_bytes = image.nbytes
    with preview_cache_lock:
        for old_key in [candidate for candidate in preview_cache if candidate[0] == str(source) and candidate != key]:
            preview_cache.pop(old_key, None)
        preview_cache[key] = (image.copy(), estimated_bytes)
        preview_cache.move_to_end(key)
        while sum(item[1] for item in preview_cache.values()) > PREVIEW_CACHE_MAX_BYTES and len(preview_cache) > 1:
            preview_cache.popitem(last=False)
    return image, False


def _scan(source: Path) -> list[dict[str, Any]]:
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError(source)
    result = []
    for path in sorted(source.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            stat = path.stat()
            result.append({"id": path_id(path), "path": str(path), "name": path.name, "type": path.suffix.lower()[1:].upper(), "bytes": stat.st_size, "modified": int(stat.st_mtime)})
    return result


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    static = HERE / "static"
    stamp = max((static / name).stat().st_mtime_ns for name in ("index.html", "styles.css", "polish.css", "app.js", "brushes.js", "projects.js"))
    html = (static / "index.html").read_text()
    html = html.replace('/static/styles.css', f'/static/styles.css?v={stamp}')
    html = html.replace('/static/polish.css', f'/static/polish.css?v={stamp}')
    html = html.replace('/static/app.js', f'/static/app.js?v={stamp}')
    html = html.replace('/static/brushes.js', f'/static/brushes.js?v={stamp}')
    html = html.replace('/static/projects.js', f'/static/projects.js?v={stamp}')
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/api/config")
def config() -> dict[str, Any]:
    # Capability gate prevents new recipes being rendered by an old process.
    result = _config_base()
    result["tone_engine_version"] = 4
    result["resident_preview_version"] = 1
    result["unified_gpu_version"] = 1
    result["raw_headroom_version"] = 1
    return result


def _config_base() -> dict[str, Any]:
    return {"mask_engine_version": MASK_ENGINE_VERSION, "presets": PRESETS, "default_recipe": DEFAULT_RECIPE, "suggested_source": "/Volumes/SU800/DCIM/100_FUJI", "fallback_source": str(HERE.parent / "output" / "reference_restart_final_jpg"), "preview_master_side": PREVIEW_MASTER_SIDE, "draft_preview_side": DRAFT_PREVIEW_SIDE, "pipeline": "scene-linear float32 / shared GPU RGBA32F preview and export / final JPG 8-bit"}


@app.get("/api/scan")
def scan(path: str = Query(...)) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    try:
        files = _scan(source)
    except FileNotFoundError:
        raise HTTPException(404, f"Folder is offline or missing: {source}")
    saved = {}
    project = _project_file(str(source))
    if project.exists():
        try:
            saved = json.loads(project.read_text())
        except Exception:
            saved = {}
    return {"source": str(source), "files": files, "saved": saved}


@app.get("/api/thumb")
def thumb(path: str = Query(...)) -> Response:
    source = Path(path).expanduser().resolve()
    key = path_id(source)
    cached = CACHE / f"thumb_{key}.jpg"
    try:
        if not cached.exists() or cached.stat().st_mtime < source.stat().st_mtime:
            cached.write_bytes(jpeg_bytes(embedded_thumbnail(source, 420), 84))
        return Response(cached.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/preview")
def preview(req: PreviewRequest) -> Response:
    try:
        started = time.perf_counter()
        image, cache_hit = _preview_source(req.path)
        requested_side = DRAFT_PREVIEW_SIDE if req.draft else max(800, min(req.max_side, PREVIEW_MASTER_SIDE))
        image = resize_linear(image, requested_side)
        rendered = process(image, req.recipe, apply_crop=req.apply_crop, preview=True, seed=int(path_id(req.path)[:8], 16))
        quality = 82 if req.draft else 90
        elapsed_ms = (time.perf_counter() - started) * 1000
        return Response(jpeg_bytes(rendered, quality), media_type="image/jpeg", headers={"Cache-Control": "no-store", "X-Preview-Mode": "draft" if req.draft else "final", "X-Source-Cache": "hit" if cache_hit else "miss", "Server-Timing": f"render;dur={elapsed_ms:.1f}"})
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/linear-preview")
def linear_preview(path: str = Query(...), resident: bool = False,
                   max_side: int = Query(8192, ge=1800, le=16384)) -> Response:
    """High-bit scene-linear pixels uploaded once into the browser's RGBA16F texture."""
    try:
        if resident:
            with resident_decode_lock:
                image = load_image(path, max_side=max_side)
                payload = half_float_rgba(image)
            cache_hit = False
        else:
            image, cache_hit = _preview_source(path)
            payload = half_float_rgba(image)
        return Response(
            payload,
            media_type="application/octet-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Width": str(image.width),
                "X-Height": str(image.height),
                "X-Source-Bits": str(image.source_bits),
                "X-Source-Kind": image.source_kind,
                "X-Pixel-Format": "RGBA16F-linear",
                "X-Source-Cache": "hit" if cache_hit else "miss",
            },
        )
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post('/api/screen-preview')
def screen_preview(req: StatsRequest):
    try:
        payload,kind,key=screen_previews.lookup(req.path,req.recipe)
        return Response(payload,media_type='image/jpeg',headers={'X-Preview-Kind':kind,'X-Preview-Key':key,'Cache-Control':'no-store'})
    except (ValueError,OSError) as exc:raise HTTPException(400,str(exc))


@app.post('/api/camera-look')
async def camera_look_analysis(req: StatsRequest):
    from camera_look import camera_look
    try:
        async with gpu_decode_lock:
            return await run_in_threadpool(camera_look, req.path)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post('/api/screen-preview-key')
def screen_preview_key(req: StatsRequest):
    try:
        key=screen_previews.key(req.path,req.recipe)
        return {'key':key,'cached':screen_previews.file(key).is_file()}
    except (ValueError,OSError) as exc:raise HTTPException(400,str(exc))


@app.put('/api/screen-preview/{key}')
async def save_screen_preview(key: str,request: Request):
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>24*1024**2:raise HTTPException(413,'Preview too large')
    try:await run_in_threadpool(screen_previews.put,key,bytes(data));return {'saved':True}
    except (ValueError,OSError) as exc:raise HTTPException(400,str(exc))


@app.get('/api/gpu-source')
async def gpu_source(request: Request, path: str, limit: int = Query(16384, ge=1800, le=16384)):
    from gpu_io import source_pixels
    async with gpu_decode_lock:
        if await request.is_disconnected():
            return Response(status_code=499)
        try:
            payload, w, h, bits, kind = await run_in_threadpool(source_pixels, path, limit)
        except (ValueError, OSError, RuntimeError) as exc:
            raise HTTPException(422, str(exc))
        if await request.is_disconnected():
            return Response(status_code=499)
        return Response(payload, media_type='application/octet-stream', headers={
            'Cache-Control': 'no-store', 'X-Width': str(w), 'X-Height': str(h),
            'X-Source-Bits': str(bits), 'X-Source-Kind': kind, 'X-Pixel-Format': 'RGBA32F-linear'})


@app.post('/api/gpu-jpg')
async def gpu_jpg(request: Request, width: int, height: int, source: str,
                  destination: str, prefix: str = 'EDIT_', quality: int = 96):
    from gpu_io import save_jpg
    if width < 1 or height < 1 or width > 16384 or height > 16384 or width * height > 120_000_000:
        raise HTTPException(400, 'Invalid export dimensions')
    expected = width * height * 4
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > expected:
            raise HTTPException(400, 'Export buffer is larger than declared dimensions')
    try:
        path = await run_in_threadpool(save_jpg, bytes(payload), width, height, source, destination, prefix, quality)
        return {'path': path, 'renderer': 'unified-gpu-1', 'width': width, 'height': height}
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/clipping-stats")
def clipping(req: StatsRequest) -> dict[str, Any]:
    try:
        image, _ = _preview_source(req.path)
        return {**clipping_stats(image, req.recipe), "source_bits": image.source_bits,
                "source_kind": image.source_kind, "working_precision": "float32"}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/raw-headroom")
def raw_headroom(path: str) -> dict[str, Any]:
    from headroom import analyze
    from engine import RAW_SUFFIXES
    if Path(path).suffix.lower() not in RAW_SUFFIXES:
        raise HTTPException(400, "Sensor analysis needs the original RAW, not a JPG/TIFF preview.")
    try:
        return analyze(path)
    except Exception as exc:
        raise HTTPException(422, f"RAW sensor analysis unavailable: {exc}")


@app.post("/api/project")
def save_project(req: SaveProjectRequest) -> dict[str, bool]:
    if req.project_id:
        try:
            catalog.save_edits(req.project_id, req.photos, req.selected)
            tether.sync_saved_edits(req.project_id, req.photos, req.selected)
        except (ValueError, OSError) as exc:
            raise HTTPException(409, f'Catalog could not be saved: {exc}')
        return {'saved': True}
    destination = _project_file(str(Path(req.source).expanduser().resolve()))
    temp = destination.with_suffix(".tmp")
    temp.write_text(json.dumps(req.model_dump(), indent=2, sort_keys=True) + "\n")
    temp.replace(destination)
    return {"saved": True}


class ProjectImport(BaseModel):
    folder: str
    name: str | None = None


class ProjectCreate(BaseModel):
    name: str | None = None
    parent: str | None = None
    folder: str | None = None  # Legacy folder-open/bootstrap workflow.


class CatalogImport(BaseModel):
    path: str
    asset_ids: list[str] | None = None


@app.get('/api/catalog-capabilities')
def catalog_capabilities():
    return {'version': 2, 'default_parent': str(catalog.project_directory)}


@app.get('/api/projects/{project_id}/status')
def catalog_status(project_id: str):
    return catalog.status(project_id)


@app.post('/api/projects/{project_id}/remove')
def remove_from_library(project_id: str):
    try:
        return catalog.forget(project_id)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))


@app.post('/api/projects/{project_id}/trash')
def trash_project(project_id: str):
    try:
        return catalog.trash_project(project_id)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise HTTPException(400, str(exc))


@app.post('/api/projects/{project_id}/locate')
def locate_catalog(project_id: str, req: CatalogImport):
    try:
        return catalog.locate(project_id, req.path, req.asset_ids)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))


@app.post('/api/catalog-recovery')
def recover_catalog(snapshot: dict[str, Any]):
    try:
        p = catalog.recover(snapshot)
        return catalog.open(p['id'])
    except (ValueError, OSError, TypeError) as exc:
        raise HTTPException(400, str(exc))


@app.post('/api/catalog-import')
def import_catalog(req: CatalogImport):
    try:
        p = catalog.import_catalog(req.path)
        return catalog.open(p['id'])
    except (ValueError, OSError, TypeError) as exc:
        raise HTTPException(400, str(exc))


@app.post('/api/projects/{project_id}/reveal')
def reveal_catalog(project_id: str):
    try:
        path = catalog.ensure_folder(project_id)
        if not path.is_file():
            raise ValueError('Catalog is unavailable. Import it again from its new location.')
        subprocess.run(['/usr/bin/open', '-R', str(path)], check=True)
        return {'path': str(path)}
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise HTTPException(400, str(exc))


class ReconnectRequest(BaseModel):
    folder: str | None = None


@app.get('/api/projects')
def list_projects():
    return catalog.listing()


@app.post('/api/projects')
def create_project(req: ProjectCreate):
    try:
        if not req.folder:
            project = catalog.create_empty(req.name, req.parent)
            return catalog.open(project['id'])
        source = str(Path(req.folder).expanduser().resolve())
        legacy_path = _project_file(source)
        legacy = json.loads(legacy_path.read_text()) if legacy_path.exists() else {}
        project = catalog.create(source, req.name, legacy)
        return catalog.open(project['id'])
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))


@app.get('/api/projects/{project_id}')
def open_project(project_id: str):
    try:
        return catalog.open(project_id)
    except (ValueError, OSError) as exc:
        raise HTTPException(404, str(exc))


@app.post('/api/projects/{project_id}/import')
def import_project_folder(project_id: str, req: ProjectImport):
    try:
        catalog.add(project_id, req.folder)
        return catalog.open(project_id)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))


@app.post('/api/projects/{project_id}/import-job')
def start_import_job(project_id: str,req: ProjectImport):
    try:return imports.start(project_id,req.folder)
    except (ValueError,OSError) as exc:raise HTTPException(400,str(exc))


@app.get('/api/import-jobs/{job_id}')
def import_job_status(job_id: str):
    try:return imports.snapshot(job_id)
    except KeyError:raise HTTPException(404,'Import job not found')


@app.post('/api/import-jobs/{job_id}/cancel')
def cancel_import_job(job_id: str):
    try:return imports.cancel(job_id)
    except KeyError:raise HTTPException(404,'Import job not found')


@app.post('/api/projects/{project_id}/reconnect')
def reconnect_project(project_id: str, req: ReconnectRequest):
    try:
        return catalog.reconnect(project_id, req.folder)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))


def _run_export(job_id: str, req: ExportRequest) -> None:
    destination = Path(req.destination).expanduser().resolve() if req.destination else EXPORTS
    destination.mkdir(parents=True, exist_ok=True)
    completed = []
    errors = []
    total = len(req.items)
    for index, item in enumerate(req.items):
        source = Path(item["path"]).expanduser().resolve()
        try:
            image = load_image(source)
            rendered = process(image, item.get("recipe"), apply_crop=True, preview=False, seed=int(path_id(source)[:8], 16))
            out = destination / f"{req.prefix}{source.stem}.jpg"
            counter = 2
            while out.exists():
                out = destination / f"{req.prefix}{source.stem}_{counter}.jpg"
                counter += 1
            out.write_bytes(jpeg_bytes(rendered, req.quality))
            completed.append(str(out))
        except Exception as exc:
            errors.append({"path": str(source), "error": str(exc)})
        with jobs_lock:
            jobs[job_id].update({"done": index + 1, "total": total, "completed": completed, "errors": errors})
    with jobs_lock:
        jobs[job_id]["status"] = "complete" if not errors else "complete_with_errors"


@app.post("/api/export")
def export(req: ExportRequest) -> dict[str, str]:
    if not req.items:
        raise HTTPException(400, "No photos selected for export")
    job_id = os.urandom(8).hex()
    with jobs_lock:
        jobs[job_id] = {"status": "running", "done": 0, "total": len(req.items), "completed": [], "errors": []}
    pool.submit(_run_export, job_id, req)
    return {"job_id": job_id}


@app.get("/api/export/{job_id}")
def export_status(job_id: str) -> JSONResponse:
    with jobs_lock:
        state = jobs.get(job_id)
        if not state:
            raise HTTPException(404, "Unknown export job")
        return JSONResponse(dict(state))


from tether import register_tether
tether = register_tether(app, DATA, catalog)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
