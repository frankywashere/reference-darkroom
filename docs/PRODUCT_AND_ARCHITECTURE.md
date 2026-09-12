# Reference Darkroom: product and engineering record

Updated 2026-09-11. This and ROADMAP.md supersede outdated architecture/runtime
statements in older handoffs. Process state, mounts and installed packages must
always be checked live; this document is not proof that a service is running.

## Purpose and project history

The editor grew from a reference-led Fuji photography project: 891 originals,
six user-supplied inspiration photos, a historical selection funnel of 39
full-resolution inspections, 10 developed finalists and 8 delivered JPGs.
These numbers describe the recorded workflow, not a claim that every original
received full-resolution inspection. The user explicitly rejected early weak
results and requested closer before/after review and better contrast/crops.

The reference families were amber/teal color, gritty documentary B&W, refined
low-key B&W, graphic high-key B&W, architectural silhouettes and faded analog
color. Presets are starting points, not universal matches. The supplied references
were not generated during that successful photographic restart. The separate
reference-first workflow explains how gathering or generating references can
generalize to unrelated visual/content projects. The editor itself does not yet
generate reference images or infer recipes from arbitrary reference images.

## Implemented user workflow

1. Create an empty project and its managed folder; add paths to originals.
2. Browse a grid or filename list in a resizable/collapsible library.
3. Group same-directory RAW+JPG pairs, switch originals, or filter formats.
4. Rate/reject, edit, copy/paste recipes across RAW and JPG, undo/redo, compare.
5. Save edits automatically in the project's catalog. Green dots identify edited
   photos; grouped-pair indicators include edits to either original.
6. Export full-resolution, sRGB-tagged JPGs without overwriting originals.

RAW/JPG versions keep independent recipes. Identical numbers do not imply an
identical look because the camera JPG already contains processing. Ambiguous
pairs should not be guessed. Missing originals can be reconnected by fingerprint.

## Editing controls

- Crop ratios/free crop, straighten, rotation, flips.
- Exposure, contrast, selective shadows/highlights, whites/blacks.
- Temperature/tint, saturation/vibrance, reference grades, five-point curve.
- B&W channel mixing, clarity/dehaze, sharpening, chroma NR, grain, vignette.
- Brush, ellipse and linear masks: local exposure/color, enable/invert/amount,
  brush feather/flow/opacity, erasing, selection and colored overlay.

Shadows deliberately retains the selective dark-tone region (linear luminance
below 0.28) rather than becoming broad exposure. Maximum lift tends toward five
stops near black and tapers toward midtones. Highlights uses a logarithmic
shoulder. Neither reconstructs absent sensor data. Strong shadow lift can reveal
noise and compress local contrast. There is no separate legacy rolloff checkbox.

Clipping overlays and sampled percentages are derived from the developed GPU
linear image, not the sensor. Partial RGB clipping is not proof of recoverability.
Optional rawpy diagnostics inspect mosaic sites relative to decoder black/white
levels and provide explicitly qualified headroom/noise proxies. The temporary
exposure sweep never saves recipe changes.

## Current rendering architecture

`native/ReferenceDarkroomApp.swift` supplies a Cocoa/WKWebView shell and starts an
owned FastAPI process. HTML/CSS/JS implements the interface. The server binds to
localhost port 8765. The native shell is macOS-specific; the WebGL2 renderer is not.

`engine.py` decodes RAW via LibRaw's `dcraw_emu`, converts to scene-linear float32,
and preserves values above display white. `gpu_io.py` transports full-resolution
RGBA32F pixels. `static/gpu-engine.js` owns the shared editing shaders and
multi-pass GPU implementation used by live previews, Before, exposure sweep and
the app's JPG exports. Image buffers are RGBA32F; brush coverage uses RGBA16F
blending buffers. JPEG encoding/ICC tagging occurs on the CPU at the end.

Fit mode renders display-sized pixels. Full-detail mode processes native pixels
but still fits the result on screen; actual 100% pan/zoom is future work. Preview
and export share algorithms, but different resolutions and JPEG compression are
not bit-identical. Legacy CPU endpoints remain for old scripts/tests and are not
the current app's export path. Do not build new automation on those endpoints
without explicitly accounting for this distinction.

GPU requirements include WebGL2, floating-point render targets and float-linear
filtering. Unsupported allocations/sizes fail explicitly. Full-resolution
processing can use several GB. A small 1800-pixel benchmark with masks/clarity
showed roughly 16–24 ms warmed-up frames on the development Mac; this is not a
cross-device performance guarantee. RAM caching removes loading costs, not the
cost of applying image operations. No equivalent optimized CPU-vs-GPU study was
performed, so GPU is not asserted to be the only way to achieve responsiveness.

## Screen previews and background preparation

`preview_cache.py` stores bounded, disposable JPEG previews under
`photo_editor/editor_data/screen_previews`. Keys include source path, file size,
mtime, normalized recipe and GPU shader hash. Reloaded apps can reuse edited
previews. Changed originals, recipes or shaders cause cache misses. Eviction
removes only cache-owned JPEGs, never originals, recipes or exports (2 GB budget).

On selection, an in-memory or persistent edited preview is preferred. On a miss,
the app extracts a larger embedded camera preview (up to 1800 pixels), keeping
natural proportions, and labels it as a camera preview rather than saved edits.
The 420-pixel sidebar thumbnail is no longer stretched into the main view.
Some files only contain small embedded images; a cold/offline source cannot be
promised an instant high-resolution preview. RAW decoding proceeds independently.

After edits settle, the app saves the rendered screen preview. After idle time it
prepares the neighboring visible photos using the same GPU renderer. An explicit
Prepare project previews action prepares the whole project, with status and Stop.
Navigation aborts/preempts background preparation to prioritize the selected photo.
Cancellation cannot instantly interrupt a native RAW decoder already running.
Background work uses another GPU context and therefore extra RAM/GPU memory.

## Progressive folder import

`import_jobs.py` scans directories, reports discovered-photo counts, fingerprints
files outside the catalog lock, and commits reference batches. Polling endpoints
report phase, found/processed/added counts and errors. The UI makes committed
photos browsable without waiting for the rest. Scanning is indeterminate until
the total is known. Cancel preserves committed references and leaves originals
untouched. Duplicate paths are skipped; per-file errors are surfaced.

Each batch reads the latest catalog before writing so concurrent rating/recipe
changes are preserved. Import jobs are in-process, not durable after an engine
restart. Completed reference batches remain in the catalog; unfinished work can
be restarted. The UI remembers the active job ID across a page reload while the
same backend is alive. Other long actions (catalog import/reconnection) still
have coarser status text and are candidates for the same job system.

## Catalogs, recovery and portability

Default project location on the current Mac: Pictures/Reference Darkroom Projects.
Each managed folder contains `catalog.darkroom.json` and an ownership marker.
The runtime registry in `editor_data/catalog` locates projects. Catalogs contain
versioned JSON, stable asset IDs, path references, sampled file fingerprints,
recipes, brush strokes, ratings and selection. Originals are not copied.

Open catalog location reveals the file. Import catalog creates a local managed
project without overwriting an existing project's edits. Reconnect searches the
chosen roots and preserves IDs/settings; ambiguous matches remain unresolved.
Fingerprints combine size and three byte samples, not a complete-file hash.

Remove from library keeps project files. Move project to Trash requires a managed
folder and explicit confirmation; safeguards prevent trashing referenced originals
inside that folder. Missing/deleted catalogs are not silently recreated; locate or
save a recovery snapshot. Cache files are not a backup of the catalog.

Windows portability is intended but not certified. Mac absolute paths and
`/Volumes` heuristics require cross-platform root mapping. Both machines must have
access to the originals; importing the catalog alone does not transfer photos.
Keep renderer/decoder versions consistent and test round trips before relying on
cross-platform production use.

## Validation and source map

Core files: `app.py` (HTTP orchestration), `catalog.py` (persistence), `engine.py`
(decoding/legacy CPU reference), `gpu_io.py`, `preview_cache.py`, `import_jobs.py`,
`headroom.py`, and the focused JS modules under `photo_editor/static`.

Python tests cover tone/masks, project safety/recovery, diagnostics, source packing,
JPEG orientation/profile/non-overwrite, persistent cache invalidation and import
batch/cancellation/edit preservation. Node tests cover pairing and edit indicators.
`qa_gpu.cjs` uses a separate test page and does not open user catalogs; it checks
mask confinement/erase, transformations, determinism and display/export agreement.
Optional real RAW QA must be supplied locally and outputs to temporary directories.

Always verify the running `/api/config`, restart an outdated backend, and inspect
actual rendered results; source correctness alone previously hid a stale-mask-engine
bug. Never declare all originals visually inspected from contact-sheet review alone.

For isolated integration QA, run a second backend on port 8766 with
`REFERENCE_DARKROOM_DATA` and `REFERENCE_DARKROOM_PROJECTS` pointing at disposable
directories, then run `node photo_editor/qa_library.cjs`. It creates only synthetic
fixtures and verifies progressive import, disk-cache reuse after reload and aspect
ratio. The historical finishing scripts under `tools/` are not the app renderer
and may require additional scientific/image-processing dependencies.

## Repository and security boundaries

Only application code/tests/docs are versioned. Media, catalogs, cache, dependencies,
compiled app bundles and output directories are excluded. Git history is not a
catalog backup. Do not publish runtime logs, API keys, or photo attachments.
The localhost service currently has local-development trust assumptions. Public
remote control requires authentication, authorization, request limits, explicit
write approvals and a defined app command protocol first.
# Camera-inspired starting tone

The editing panel has a per-photo **RAW starting look → Camera-inspired tone**
toggle, off by default. The first activation analyzes a 640-pixel RAW decode and
the embedded camera JPEG, fitting a bounded, monotonic luminance transform from
tonal percentiles. It estimates brightness and contrast only: no manufacturer
film-simulation color profile, sharpening, denoise, or local tone reconstruction
is claimed. A missing JPEG or insufficient tonal variation reports an error.

The fit and enabled flag live in the photo recipe, supporting undo, persistence,
copy/paste, and preview-cache invalidation. The transform runs before ordinary
adjustments in both GPU preview/export and legacy CPU processing. Turning it off
restores the existing neutral starting tone without changing other sliders or
the RAW. Existing edited photos are not changed automatically. Initial analysis
can take a few seconds; subsequent toggles do not re-decode the RAW. A backend
restart is required after installing this endpoint.

# Browsing cache update

Photo browsing uses a bounded 2 GiB decoded-preview cache and 192 MiB
compressed-preview cache, in addition to the existing small recent-frame cache
and GPU buffers. A lightweight worker prepares the next 12 visible photos in the
travel direction and three behind, then visits the remaining project sources to
populate the disk cache and compressed RAM cache. Camera previews are labeled as
before-edits images; use **Prepare project previews** to develop saved-edit
previews for the full project. Cache limits are not a total process-memory limit.

The rolling worker's deadline is not postponed by navigation. Successful
whole-project preparation does not prevent fetching an evicted near-window
preview again. Failed sources use a 30-second retry cooldown; project changes
discard old in-flight lookup results. The decoded limit is an on-demand ceiling,
not an upfront reservation. `node photo_editor/test_preview_rolling.cjs` tests
sustained cycling, eviction from both caches, direction reversal, and byte limits.

Arrow-key holds defer foreground RAW decoding until release; other selections
use a 350 ms settling delay. Cache misses retain the previous photo with an
explicit loading label instead of blanking the canvas. View-only pinch zoom and
two-finger pan do not modify recipes; **Fit** resets the view. The larger
**Loading photo into GPU** indicator sits over the photo's upper-right corner.
