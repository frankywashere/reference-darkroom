# Reference Darkroom — developer handoff

Updated 2026-09-11. Read these current documents first:

1. [Product and architecture](docs/PRODUCT_AND_ARCHITECTURE.md)
2. [Roadmap and prior feature discussions](docs/ROADMAP.md)
3. [Launch and verification](README.md)
4. [Reference-first workflow](REFERENCE_FIRST_CONTENT_WORKFLOW.md), when working on content-production methodology.

The historical app was a CPU renderer with a simpler GPU preview. It is now a
shared float32 GPU preview/export engine with persistent screen previews and
progressive folder imports. Do not restore obsolete CPU render handoffs or use
legacy export endpoints for assistant integration without an explicit decision.

Preserve original media and all user catalog edits. Projects reference originals;
they do not copy them. Do not assume mount paths or runtime state are current.
Verify /api/config and an actual preview after restarting a changed backend.
The preview cache is disposable and is not a backup of catalog recipes.

Main editing code: photo_editor/static/gpu-engine.js and resident.js.
Library jobs/cache UI: photo_editor/static/library-progress.js.
Backend: photo_editor/app.py, catalog.py, preview_cache.py, import_jobs.py,
gpu_io.py, engine.py and headroom.py. Native shell: native/.

Run Python unit tests and Node pairing tests before delivery; run isolated GPU
QA when changing shaders. Never use a live catalog for destructive test fixtures.
Never claim all 891 historical originals were inspected at full resolution:
the documented full-resolution selection was 39, with 10 developed and 8 delivered.

Tether/live view, Nikon Z8 SDK control, automatic portrait retouching, Windows,
MCP integration, AI reference generation and 100% pan/zoom are roadmap items, not
implemented features. Their scope and prerequisites are recorded in ROADMAP.md.

Repository excludes photos, catalogs, compiled apps, cache and generated outputs.
Do not add credentials or user media to Git. Do not choose a redistribution
license or public visibility without the user's direction.
