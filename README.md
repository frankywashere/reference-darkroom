# Reference Darkroom

A local, non-destructive RAW/JPG editor with a native macOS shell, reference-led
looks, project catalogs, GPU editing, feathered masks and full-resolution JPG export.

**Status:** active prototype, tested on Apple Silicon/macOS. Windows, tethering,
automated portrait retouching and an assistant/MCP connection are roadmap items,
not shipping features. No original photographs or user catalogs are included.

## Start

Install Python 3.12 and the external tools `dcraw_emu` (LibRaw) and `exiftool`.
On macOS, Homebrew packages `libraw` and `exiftool` provide these programs.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r photo_editor/requirements.txt
python photo_editor/app.py
```

Open `http://127.0.0.1:8765`. For the optional sensor diagnostics, install
`photo_editor/requirements-diagnostics.txt` into the same environment.

The native shell is built with `zsh native/build_native_app.sh`; this requires
Xcode command-line tools and ImageMagick (`magick`) for the icon. The app bundle
is generated locally, not checked in. The shell currently searches several Mac
Python locations; browser mode with the activated environment is the most
reproducible development launch. Native dependency bundling is still planned.

## Documentation

- [Product, architecture, data and operations](docs/PRODUCT_AND_ARCHITECTURE.md)
- [Roadmap and previously discussed features](docs/ROADMAP.md)
- [Development handoff](LLM_HANDOFF.md)
- [Detailed editor notes and historical changes](photo_editor/README.md)
- [Reference-first content workflow and historical case study](REFERENCE_FIRST_CONTENT_WORKFLOW.md)

## Verify

```sh
python -m unittest discover -s photo_editor -p 'test_*.py'
node photo_editor/test_pairs.cjs
```

GPU QA runs in an isolated Chromium page; see `photo_editor/qa_gpu.cjs` and the
editor README. Real-photo QA inputs are local and intentionally absent here.

## Data safety

Catalogs contain paths, stable asset IDs, fingerprints, recipes, masks and ratings;
they do not contain the originals. Back up both the catalogs and original files.
The screen-preview cache is disposable. Export uses fresh filenames rather than
overwriting an original or existing export. This server is intended for localhost
only and must not be exposed as an unauthenticated public service.

Repository scope: application/source code, tests and documentation. Runtime data,
photos, generated assets, exports, compiled binaries and credentials are ignored.
No redistribution license has been selected yet.
