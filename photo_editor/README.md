# Reference Darkroom

Current consolidated documentation: [Product and architecture](../docs/PRODUCT_AND_ARCHITECTURE.md)
and [roadmap](../docs/ROADMAP.md). Those documents supersede historical notes below.

A local, non-destructive RAW/JPG photo editor built for the 891-frame Fuji shoot and the six supplied reference looks.

The editor is one implementation of the broader [Reference-First Content Workflow](../REFERENCE_FIRST_CONTENT_WORKFLOW.md). The write-up contains both a detailed case study of this 891-frame project and a subject-independent production playbook for unrelated photo, video, writing, design, advertising, 3D, and generative-content work.

## Launch

The easiest option is to double-click the native macOS app beside this folder:

`/Users/frank/Documents/ChatGPT/photos/Reference Darkroom.app`

The app opens the editor in its own macOS window and starts/stops the local photo engine automatically. The editor code remains in this folder, so future feature changes appear in the native app without rewriting the interface.

Alternatively, double-click `run_editor.command`, or run:

```sh
cd /Users/frank/Documents/ChatGPT/photos/photo_editor
python3 app.py
```

Then open <http://127.0.0.1:8765>. The server binds only to the local Mac.

## Included workflow

Projects are available in the left library panel. **New project** references a folder recursively; **Add folder** adds more references to the selected project. Originals are not copied. Each asset has a stable ID, and edits, ratings, crop and mask settings are saved in `editor_data/catalog`. Existing folder recipes are migrated when that folder is first added. The last selected project reopens on launch.

Missing originals remain in their project. On opening, the editor searches known folders, nearby parent folders and equivalent paths on renamed mounted volumes. **Reconnect** searches a new folder you specify. File size and a SHA-256 fingerprint of three sampled regions identify candidates even after renaming. This is a sampled identity check, not a full-file hash; ambiguous duplicates are left unresolved. Moving files somewhere outside these search locations requires pointing Reconnect at the new parent folder. Back up `editor_data/catalog` along with the original photos to retain edits.

- Browse and cull whole folders; reject or assign 1–5 stars.
- Open RAF, DNG, CR2/CR3, NEF, ARW, JPG, PNG, and TIFF files.
- Non-destructive crop presets, free crop, straighten, rotation, and flip parameters.
- Exposure, contrast, highlights, shadows, whites, blacks, temperature, tint, vibrance, saturation, clarity, dehaze, sharpening, chroma noise reduction, grain, and vignette.
- Five-point tone curve and red/green/blue monochrome mixer.
- Feathered ellipse and linear local masks for dodge/burn, color temperature, and saturation.
- Six reference-derived looks: amber/teal cinema, gritty documentary B&W, refined low-key B&W, graphic high-key B&W, architectural silhouette, and faded warm film.
- A reference-first method that is independent of these particular six images; new projects can gather or generate their own reference families and translate them into new recipes.
- Before/after split view, undo/redo, recipe copy/paste, project autosave, and batch full-resolution sRGB JPG export.
- A scene-linear float32 master pipeline. RAW files decode to 16-bit linear RGB, ordinary 8/16-bit images are converted to linear light, edits retain highlight headroom, and quantization to 8-bit happens only when the final JPG or on-screen preview is encoded.
- Responsive two-stage previews: decoded float32 images are cached once per photo; WebGL2 receives an RGBA16F linear proxy once and runs the complete global recipe as sliders move; the exact 1800-pixel float32 engine result replaces it on release. Local masks retain the cached server-preview fallback.
- Source-precision status plus display-highlight and near-black clipping overlays. Partial RGB clipping is not a guarantee of recoverable sensor detail; use the separate RAW diagnostics panel.

The originals are read-only. Each project saves ratings, recipes and masks in its own `catalog.darkroom.json`. Thumbnails are disposable caches in `editor_data/cache`; exports default to the active project's `Exports` folder and can be changed in the export dialog.

## Projects and moving between machines

**Create project** asks for a name and a parent location (default: `~/Pictures/Reference Darkroom Projects`). It creates a new named folder containing `catalog.darkroom.json`, with an empty photo list. **Add photos** references images in a chosen source folder; it never copies originals. Multiple source folders can belong to one project.

**Open catalog location** reveals the active catalog in Finder. Its full path is also displayed below the save status. Wait for All edits saved before transferring the catalog. Bring that single JSON file (or its project folder) to another Mac running Reference Darkroom, then choose **Import catalog → Choose…**. All photo IDs, ratings, recipes, crops and mask strokes continue in the imported project. Missing originals appear as offline; **Find missing originals** reconnects them by size and content fingerprint. The originals must be accessible separately, for example on the same external drive. The catalog does not contain photo pixels.

Import creates a separate local project, even if another catalog has the same project ID. Selecting a catalog already registered at exactly that location simply reopens it. This is a transfer workflow, not simultaneous multi-machine sync or edit merging. Save and transfer the latest catalog when changing machines again.

The local registry at `editor_data/catalog/_locations.json` remembers catalog locations but contains no edits. Older centrally stored catalogs are migrated on opening into named project folders while keeping their previous JSON as recovery copies. If a project folder is moved or the registry is lost, import its catalog again. Catalog files use format `reference-darkroom`, version `1`.

**Manage project…** provides **Remove from library** (keeps all files) and **Move project to Trash** (moves the managed project folder, including exports, to macOS Trash). Both close the project. Import its catalog to reopen a removed project; restore a trashed folder first. The app refuses to trash a folder that contains originals referenced by any registered project, or a folder it cannot identify as a managed project folder. Removed IDs are recorded in `_removed.json` so legacy catalog copies do not reappear in the list or accept late saves.

The open catalog is checked every five seconds and when the app regains focus. A missing or unreadable catalog produces a persistent recovery warning. **Locate catalog** reconnects the same project's file and saves currently loaded edits. **Save recovery copy** writes the in-memory references and settings into a separate `(Recovered)` project folder, including edits that could not be saved to the old file. Keep the editor open until recovery succeeds; an in-memory recovery cannot survive quitting the app. Unsaved projects must be recovered before removal.

RAF decoding uses `dcraw_emu -4 -H 2` and embedded previews use `exiftool`, both already installed on this Mac. `-4` means 16-bit linear output with fixed white level and gamma 1.0; the editor then applies a non-clipping float baseline exposure so the untouched RAW is viewable while values above display white remain recoverable. `-H 2` blends clipped channels when surviving colour information permits it. Truly saturated photosites and values buried below the sensor noise floor cannot be recovered by any editor.

The precision pipeline has automated 16-bit fixtures and export coverage. A real Fuji RAF still needs to be re-run whenever the camera volume is mounted before describing a particular camera/file combination as verified.
## Brush masks and library layout

Choose **Masks → New brush**. The dedicated Masks workspace replaces global controls while you work locally. New masks start neutral: paint the area first, then adjust exposure, saturation or temperature. The red overlay appears while painting and hides when you move a local adjustment slider; use **Show colored mask** or **O** to toggle it yourself. **Done** returns to global editing without discarding the mask.

Select a named mask card to edit it, rename it in Mask name, and use its On/Off control to compare its effect without deleting strokes. Effect strength scales the selected mask's adjustment. Add to mask and Erase from mask refine the area; hold Option for temporary erase. Size and feather stay visible, while flow (dab buildup) and opacity (per-stroke coverage limit) are under Advanced brush settings. The brush cursor shows its outer extent and feather core. [ / ] changes size. Undo/redo works per stroke; Delete mask is also undoable. Brush settings affect new strokes, not previously painted strokes.

The overlay updates while painting; the float32 photo adjustment renders after release. Strokes, names, visibility and effect strength are saved in the project's per-photo recipe and replayed at export resolution; originals are not modified.

Masks currently use the uncropped, geometrically transformed image coordinates: finish rotation/flips before painting. Crop is applied afterward. Masked photos use server previews rather than the global-only GPU shortcut; long stroke histories and full-resolution exports can take longer. Pressure sensitivity and automatic subject selection are not implemented.

Drag the divider at the photo library's right edge to resize it. The **Library** toolbar button collapses/restores it. Width and collapsed state persist across launches. The divider also supports arrow keys when focused.
# RAW + JPG pairs and enhanced recovery

Project deletion now asks **Are you sure you want to delete this project?** and
names the project before any save, removal or Trash operation begins. Cancel is
focused by default. Removing from the library also has a distinct confirmation
explaining that files remain on disk. No project is deleted by installing updates.

Green thumbnail dots indicate a recipe different from the app defaults (not
ratings). Grouped pairs report either member; hover names the edited files.
Returning all settings to defaults removes the dot. Indicators update on edits,
undo, paste and reset, and are recomputed from catalog recipes after reopening.

The clipping status describes the developed preview before its final display
curve: any RGB channel >=1, luminance <=0.0005, and partial RGB clipping.
“Partial RGB clipping” replaces the misleading “channel-recoverable” label.
Neither this statistic nor a maxed slider measures sensor recovery headroom.
Open **Light → RAW headroom & exposure sweep** for separate original-sensor
diagnostics. This uses rawpy 0.27.1 without modifying or replacing the existing
development pipeline. Optional dependency installation (same Python as app):

```
python3 -m pip install --only-binary=:all: --no-deps --target photo_editor/editor_data/analysis_deps rawpy==0.27.1
```

The panel counts visible mosaic sites at/above the decoder's nominal white level,
at/below black, positive signal below 1/256 of the available range, and unclipped
sites within one stop of white. It reports each CFA channel independently and
the white-level source. These are sensor-site counts, not complete RGB pixels.
Black/white calibration, lossy RAW encoding and decoder support limit certainty.
The 99.9th-percentile headroom statistic describes bright-tail capture headroom,
not recoverable stops; a small population can already be saturated.

Dark-region variation is an explicitly uncalibrated proxy: median absolute
deviation of same-color neighbor differences, divided by 0.67449 * sqrt(2),
using signals in the bottom 1% of range and at least 128 eligible pairs. Texture,
gradients, denoising and compression affect this number; it is not a sensor read
noise measurement or a reliable clean-shadow recovery limit. No estimate is
reported when variation is unresolved or too few pairs exist.

The temporary -6 to +6 EV sweep uses either current edits or a neutral baseline.
It previews at up to 1400 pixels, ignores crop, and never writes a recipe/catalog.
Use it to distinguish returning texture from simply darkened white or lifted
noise. Native-resolution noise judgment remains a separate task. JPGs can use
the sweep but cannot provide original sensor diagnostics. Unsupported RAW formats
show an explicit error. Results cache by path, size and modification time.

Implementation references: [rawpy sensor APIs](https://letmaik.github.io/rawpy/api/rawpy.RawPy.html).

The photo list defaults to **Group RAW + JPG**, with **All / RAW / JPG** filters.
A pair requires exactly one recognized RAW and one JPG/JPEG with the identical
filename stem in the same directory; ambiguous groups remain separate. Capture
timestamps are compared when present in the catalog (older catalogs do not
contain them). This is filename-based grouping, not an image-similarity claim.
RAW is preferred for new selections; the saved selection and session choices
are respected. The toolbar RAW/JPG buttons switch the original being edited.
Each file retains its own recipe and rating. Rating filters select eligible
members before grouping. A missing RAW falls back to its available JPG in All.
View preferences persist locally. No originals are moved or deleted.

Recipe Copy/Paste works across formats, with an in-app clipboard fallback.
Copied recipes are independent, including masks. Identical settings can look
different on a camera-processed JPG. “Visible photos” export uses the displayed
versions; “All picked photos” still includes every individually rated file.

Exposure is labeled in EV (stops), retaining its -5 to +5 range. Light uses one
tone model (runtime capability version 4), with no legacy/upgrade switch, as
requested. Old tone_engine recipe tags are ignored; existing edits can render
differently after this update. No catalogs or originals are deleted or rewritten
as a migration step.

Shadows restores the original linear-luminance boundary of 0.28, after Exposure
and Contrast. Above that boundary, Shadows has no effect. Below it, a monotonic
rational curve supplies up to five stops of gain near black, tapering to zero
at the boundary with a matching slope (no abrupt join or tonal reversal).
The range is not expanded to display white. The five-stop maximum is asymptotic:
tones nearer the midtones receive less lift, preventing them from overtaking
unaffected tones. Strong settings necessarily compress contrast inside shadows.
Highlights remains unchanged and uses a logarithmic shoulder above middle
gray without the old finite ceiling. The two controls overlap and strong
settings compress tonal contrast; they are not edge-aware local dodging/burning.
Both preserve RGB ratios prior to output clipping and use equivalent CPU/GPU
formulas. Neither reconstructs sensor-clipped detail. Visual regression:
`python3 photo_editor/qa_tone.py /tmp/darkroom-tone-qa.jpg` compares three real
Fuji RAWs, including DSCF2820.RAF, with neutral, shadow, exposure and highlight
adjustments without changing their recipes.

Tests: `node photo_editor/test_pairs.cjs` and the Python unittest suite.
## Unified GPU renderer (current architecture)

This supersedes the older CPU-preview and resident-preview descriptions above.
`static/gpu-engine.js` is now the shared editing implementation for the app's
preview, Before comparison, exposure-sweep preview and JPG exports. It covers
geometry, global tone/color, grades, local masks, monochrome, curve, CIE Lab chroma
noise reduction, separable Gaussian clarity/sharpening, vignette and deterministic
grain. The old approximate single-pass shader has been removed.

- The original is decoded once per selection and uploaded as **RGBA32F**. Image
  editing passes use RGBA32F targets. Brush coverage uses RGBA16F blending targets;
  it does not quantize the image to 16-bit. Final JPGs are 8-bit, tagged sRGB.
- Brushes replay feathered dabs on the GPU, including flow, opacity, erase,
  invert, enable and amount. Mask textures are cached while adjustment values move.
- **Preview: Fit** renders display-sized pixels (up to 2560 on the long side).
  **Preview: Full detail** processes all pixels with the same shaders, then fits
  the resulting image on screen. It is not yet a pan/zoom-at-100% tool.
- Fit and full modes use the same spatially scaled effects. They are not promised
  bit-identical across resolutions: resampling and JPEG encoding still matter.
  At equal resolution, QA compares displayed and exported pixels within 1/255.
- The CPU handles RAW decoding, sensor diagnostics, file/catalog operations and
  JPG encoding. It does not render the app's interactive edits or JPG export looks.
  Legacy `/api/preview` and `/api/export` remain for older scripts/tests; they are
  not the current app's export path and may give different detail/grain results.
- `/api/gpu-source` returns native-size linear pixels; `/api/gpu-jpg` saves GPU
  pixels with exclusive-create filenames, preserving originals and existing exports.
  Unsupported GPU sizes fail explicitly, never silently export reduced resolution.
- Switching photos immediately shows a loaded camera thumbnail or an in-session
  edited preview. RAW loading runs in the background. Camera thumbnails are
  labeled because they may not show the saved recipe. Sixteen recent edited
  previews are cached; loading is debounced, obsolete requests are aborted, and
  response tokens prevent old photos replacing the current one.
- Loading a large source and full-detail/export processing still take time and
  memory. Full-resolution export can use several GB. Cancel stops a batch after
  the current in-flight operation; completed JPGs are kept. The app must stay open.

### Clone stamp / retouch layers

Open **Clone** in the right panel. Option/Alt-click a clean source area (or click
**Set source**, then the photo), and paint over a distraction. Brush size,
feather, stroke opacity, and flow affect new strokes. The outer circle shows the
brush diameter; the inner circle shows its firm core; the cross marks the source.
Aligned source keeps the offset between strokes; switch it off to restart each
stroke from the chosen source. Sampling outside the original leaves pixels alone.

The first stroke creates a dedicated retouch layer. Layers can be named, hidden,
deleted, and faded with layer opacity. Erase retouch restores the image below the
selected layer. Undo/redo covers strokes and layer changes. Original photo samples
the unretouched image; Retouch stack samples the pre-stroke composite including
earlier strokes and lower layers, avoiding feedback smearing within a stroke.

Strokes persist in each photo's catalog recipe, not in the source file. They use
original-image coordinates and scene-linear float32 values before color, masks,
rotation and crop. Reference looks preserve them; Reset photo clears them.
JPG export replays them at source resolution. Fit previews replay at display
resolution; choose Full detail to inspect fine retouch edges. Large retouch
histories and full-resolution exports require additional GPU memory and time.
This is a clone stamp, not automatic healing or AI blemish removal.

Regression tests: `test_clone.py` and `qa_clone.cjs` (isolated backend on 8766,
with temporary `REFERENCE_DARKROOM_DATA` and `REFERENCE_DARKROOM_PROJECTS`).

### Renderer regression tests

`python3 -m unittest discover -s photo_editor -p 'test_*.py'` includes float32
transport, size-limit, sRGB profile, orientation and non-overwrite checks.
`node photo_editor/qa_gpu.cjs --raw --export` uses an isolated headless Chrome
page, not the catalog UI. Install Playwright in a temporary directory with
`npm install --prefix /tmp/darkroom-gpu-test --ignore-scripts playwright` first,
or set `PLAYWRIGHT_PATH` to an existing installation. The optional RAW fixture is
`/Volumes/SU800/Ari/DSCF2876.RAF`; QA exports go only to `/tmp/darkroom-unified-qa`.

Tests cover local-mask confinement, erasing, disabled/zero/empty masks, rotated
dimensions, curve/detail combinations, determinism, display/export agreement,
and a real 6246 × 4170 RAW export. A measured 1800-pixel test with clarity and a
brush mask took about 16–24 ms per settled frame after warm-up on this Mac;
this is one workload, not a guaranteed frame rate for every recipe or device.
