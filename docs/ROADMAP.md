# Roadmap and prior decisions

Updated 2026-09-30. These are discussed directions, not permission to implement
everything automatically. See PRODUCT_AND_ARCHITECTURE.md for working features.

## 1. Preview and interaction polish (partly implemented)

Implemented: persistent edited screen previews; larger camera-preview fallback;
natural image proportions; adjacent-photo preparation; optional project preparation;
cache invalidation; folder scan/add progress, progressive availability and cancellation.

Next: test cold/reloaded/offline libraries; improve prioritization and memory
budgets; retain previews across moved source roots where identity is verified;
durable/resumable import jobs; progress for catalog imports and reconnect scans;
100% zoom/pan and tiled rendering; incremental brush-mask caching; visible task
queue; cache-management controls. Do not reintroduce low-res sidebar thumbnails as
full-size main previews or show camera processing as though it were saved edits.

## 2. Assistant integration via MCP (not implemented)

Decision: build a typed application command API, then expose it through an MCP
adapter. Do not let the assistant directly overwrite catalog JSON or pretend
legacy CPU endpoints invoke the new GPU export engine.

Candidate tools: list/open projects; list/select photos; read recipe/state; return
screen/native-detail previews; apply validated adjustments; create/edit masks;
copy/paste recipes; rate/cull; undo/redo; submit export; inspect/cancel jobs.

Requirements: stable IDs, versioned command schemas, transactional undo, request
IDs/idempotency, live-window acknowledgement, UI synchronization, scoped file
access, explicit approval for destructive actions, and useful image feedback.
GPU commands must reach the running renderer or a supported offscreen host.

Local MCP is the initial direction; other assistant clients can reuse the same
protocol. Cloud access needs separately reviewed authentication/tunnel/hosting
and privacy design. Sending previews to a cloud model is data sharing even if
the editor and MCP server run locally. A built-in AI chat panel is a separate
product decision, not a prerequisite for external MCP control.

## 3. Windows / cross-platform desktop (not implemented)

Reuse the HTML interface, WebGL2 shaders, recipes and catalog schema. Replace or
supplement the Swift/Cocoa shell with a Windows host (WebView2) or a shared shell
such as Tauri. These are candidates, not a finalized framework choice. A desktop
webview shell is distinct from rewriting every control as a native OS widget.

Required work: Windows packaging/installer; bundled Python and RAW tools; portable
file pickers/reveal/recycle-bin; root mapping between Mac volumes and drive letters;
case/Unicode/path tests; catalog migration and round-trip tests; filesystem access
to original media; renderer and decoder version records; sRGB/color validation;
NVIDIA/AMD/Intel GPU tests, float32 capabilities, memory limits and failure UX.

Do not promise bit-identical images across different drivers or performance on
every integrated GPU. Do not rewrite the renderer into Mac-only Metal if that
would undermine the agreed portability goal without a clear cross-platform plan.

Research references: https://v2.tauri.app/reference/webview-versions/ and
https://github.com/google/angle . Re-check current support before implementation.

## 4. Nikon Z8 tethering and live view (Mac implementation)

Implemented with the user's Nikon Remote SDK 2.0.0: isolated native camera
process, discovery/connect/disconnect, live-view window, remote one-frame capture,
camera-provided exposure options, completed-file catalog ingestion, and optional
global starting recipe. See NIKON_TETHERING.md for setup, behavior, and testing.
Windows SDK hosting, burst controls and autofocus-point placement remain future
work. The following notes preserve the original requirements and alternatives.

The requested tether camera is the **Nikon Z8**, not the Fuji used for development.
Scope includes capture arrival into a project, live view, camera/capture control,
connection status, disconnect recovery and applying an approved starting recipe.

Two possible stages discussed:

1. Watch a capture folder written by Nikon NX Tether; import only completed files.
   This can ingest captures but does not itself embed live view in our editor.
2. Direct Nikon SDK integration for supported live-view/camera controls. Confirm
   SDK terms, supported OS/architectures, exact Z8 features and firmware requirements
   before committing to a design. Keep camera code behind a portable interface.

Earlier research identified Nikon's unified Z-series SDK and NX Tether as leads;
these must be reverified against the currently available SDK and license. The
camera's USB data connection is distinct from its power-delivery port; verify
the actual connection mode and cabling during hardware testing. Test NEF lossless
compression first, then other Z8 compression modes and RAW+JPG pairing.

Engineering requirements: file-completion detection, no partially written imports,
duplicate suppression, capture sequence IDs, camera/source timestamps, orientation,
live-view frame latency/backpressure, optional disk destination and recipe association.
Never couple UI responsiveness to a blocking SDK callback.

## 5. Tethered portrait retouching (research only)

User goal: adjust one representative shot, then automatically locate faces and
apply controlled blemish removal, iris brightening and under-eye treatment as
new photographs arrive. Preserve identity, natural skin texture and reversibility.

Preferred research direction: hybrid AI + conventional image processing. Use
landmarks/segmentation for face, eye and skin regions; controlled local algorithms
for brightness/color; evaluate a dedicated blemish/retouch model only where needed.
A spatial mask cannot simply be copied between poses. Transfer retouch intent
and strength, then re-detect/re-align each face in each capture.

Previously mentioned research leads include RetouchFormer and Retouch4me's API.
No model has been selected, installed, licensed or validated as suitable. Compare
actual hardware/runtime requirements, commercial licenses, privacy, latency,
skin-tone/pose coverage, multiple faces, glasses/hair occlusion, failure rates and
full-resolution quality. Cloud retouching requires explicit image-sharing approval.

UX: show detected regions and per-operation strengths, let users approve/disable
automatic application, retain before/after, confidence/failure indicators and
per-photo overrides. Avoid indiscriminate smoothing or generative identity changes.

## 6. Reference-led assistance and broader content workflow (future)

Continue documenting the general pipeline beyond the Fuji or any unrelated
Elon-themed work: gather/generate references, articulate target attributes, test
controlled variants, inspect actual outputs and deliver reproducibly.

Possible editor additions: reference board; side-by-side style study; suggested
recipes with confidence and constraints; variant sets; before/after review tools.
AI reference generation, automatic reference matching, segmentation, inpainting,
generative fill, compositing/layers and Photoshop-level retouching are not current
capabilities. They require separate prioritization and implementation approval.

## Recommended sequence

1. Stabilize preview/import UX and regression tests on the real library.
2. Establish versioned app commands and renderer/catalog contracts.
3. Add the local MCP adapter and verify undo/UI synchronization.
4. Prototype Windows packaging and catalog round trips early.
5. Prototype Z8 capture-folder ingestion, then SDK live view if feasible.
6. Evaluate assisted retouching on an approved test set before automatic tether use.

This sequence is a recommendation, not a commitment or a release schedule.
