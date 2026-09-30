# Nikon Z8 tethered shooting

The Mac editor uses the user's Nikon Remote SDK 2.0.0 to discover a camera,
control live view, request captures, read/change supported exposure settings,
and add completed NEF/JPG files to a project. Nikon code runs in a separate native
process, keeping SDK callbacks and camera communication outside the editor's
rendering and catalog threads.

## Use

1. Connect the Z8's USB **data** port to the Mac, switch it on, and close NX Tether,
   Camera Control Pro, and Nikon Transfer if they are using the camera.
2. Create or open the receiving project. Click **Tether** in the header.
3. Select the camera after Scan. Choose a capture destination if desired; the
   default is `Captures` inside this project's folder. Every connection creates
   a separate dated session folder, avoiding collisions with earlier shoots.
4. Optionally enable **Use the current photo's look**. Click **Connect to current
   project**. Live view starts automatically. Its floating window can be moved,
   resized, or hidden while continuing to edit photographs.
5. Press **Capture**, or use the camera's shutter. **Autofocus** controls remote
   shutter focusing. The remote request asks for one frame, including when the
   body's normal release mode is continuous. Unusual release modes can still
   require setting single-frame mode on the camera.
6. **Lossless RAW for full-resolution editing** defaults on. The editor's current
   LibRaw decoder cannot open Z8 High Efficiency/High Efficiency* NEFs. This option
   selects lossless RAW during the connection and restores the prior setting on
   normal disconnect. Disable it to keep the camera's compression selection;
   High Efficiency files will transfer but cannot yet be developed in the editor.
   Support through Nikon's separate Image SDK remains future work.
7. Captures are saved to the computer and camera card during this connection.
   Disconnect restores the prior save-media setting on a normal shutdown.
   RAW+JPG selection remains the camera's setting.
8. **Select new captures** follows arrivals in the receiving project. Turn it off
   to keep editing the current photograph. Switching or creating projects now
   automatically changes the receiving project without stopping live view or
   reconnecting. The session's physical capture folder stays unchanged; the new
   project references subsequent originals there. Already-started transfers stay
   assigned to their earlier project; RAW/JPG siblings stay together. Previous
   shots are not moved. The active starting look is retained until explicitly
   updated. The receiving project and physical folder remain displayed.
9. **Auto-apply latest capture's edits to incoming photos** defaults on and
   remembers your choice across app restarts. Saving edits to the latest captured
   shot updates the starting look automatically, even with the Tether window
   hidden. Either RAW/JPG version of that latest shot can supply the look; editing
   an older shot or another project's photo does not change it. Remote Capture
   waits for queued editor saves. A body-shutter shot uses the look saved before
   its transfer starts; files already transferring retain their starting recipe.
   Existing photographs are not batch-updated. Only global color/tone/detail
   settings transfer; crops, rotation, masks, and cloned pixels stay separate.
   Switching automatic mode off freezes the current starting look and reveals
   **Use current look for next captures** for explicit manual updates.

Supported camera-provided options appear for ISO, shutter speed, aperture, and
exposure mode when the SDK supplies a supported values list. Use **Settings** to
refresh after adjusting controls on the camera. Capture settings may be read-only
in some camera modes; errors remain visible without resubmitting the command.

## Local SDK installation

The Nikon headers, binaries and configuration profiles are **not in Git**.
Install from your own authorized Nikon Z-series SDK ZIP:

```sh
python3 native/install_nikon_sdk.py /path/to/S-SDKZ-200BF-ALLIN.zip
```

This unpacks the Mac runtime into `photo_editor/editor_data/nikon`, builds
`darkroom-nikon`, and installs the SDK's three required profiles in
`~/Library/Preferences/Nikon/NXTether`. Existing differing profiles are preserved
and reported instead of overwritten. The helper uses the shipped universal
arm64/x86_64 module and local Apple command-line tools. Rebuild it after changing
`native/NikonBridge.mm`. Install the SDK separately on each Mac; distributing
Nikon components requires following Nikon's license terms.

For isolated testing, `REFERENCE_DARKROOM_DATA` and
`REFERENCE_DARKROOM_PROJECTS` select scratch storage, and
`REFERENCE_DARKROOM_NIKON_RUNTIME` points at the installed `TestApp/TestApp`
runtime directory containing the helper and module bundle.

## Data and connection behavior

- Nikon `ImageSaved` callbacks identify completed transfers (some report only
  the filename, which is resolved inside the session directory). A worker verifies
  stable nonempty files and JPG/TIFF signatures, validates the session root,
  fingerprints each photo, and registers it under a stable catalog asset ID.
  Duplicate callbacks do not create duplicate photographs.
- Photos are referenced in their capture folder. Edits persist as ordinary
  per-photo recipes in the receiving project's catalog. RAW+JPG pairing uses
  the existing library grouping and format filters.
- Live view publishes the latest JPEG atomically, capped near 12 frames/second.
  The browser requests at most one frame at a time; old frames do not accumulate
  in a queue. It shows a waiting message when frames become stale.
- An SDK crash or disconnected camera ends the connection and leaves completed
  imported captures available. Scan/connect opens a fresh session. Shutter
  commands are never repeated automatically after timeout.
- SDK diagnostics are local in `photo_editor/editor_data/nikon/bridge.log`.
  Interrupting the application or unplugging during transfer can leave an
  unfinished file in the capture folder; it is not imported as a complete photo.
- Hiding the window leaves the connected session active. Stop live view or
  Disconnect to stop streaming. App/backend shutdown closes the SDK process.
- Capture event history is bounded. A page reload reads persisted catalog assets;
  it does not rely solely on ephemeral event messages.

## Scope and future work

This implementation targets macOS and the supplied Nikon 2.0 SDK. Windows can
reuse the HTTP interface, catalog ingestion, and UI, with a Windows SDK helper.
Video recording, multi-camera sessions, autofocus point placement, burst-count
controls, and automatic facial retouching remain future work. Starting-look
transfer does not detect faces or transfer brushes between poses.

The SDK's own readme lists the Z8 and macOS 13–26, and warns against running
competing Nikon camera-control applications simultaneously. Nikon's public
[SDK information page](https://sdk.nikonimaging.com/information/en/) provides
current availability and compatibility notices.

## Verification

`python3 -m unittest discover -s photo_editor -p 'test_*.py'` checks completed-file
ingestion, duplicate suppression, invalid/incomplete file rejection, and recipe
transfer without spatial edits. `qa_tether.cjs --hardware` runs against an
isolated backend on port 8766: it discovers the real camera, checks live view,
requests **one real exposure**, verifies catalog arrival and GPU decoding,
disconnects, and reopens the catalog. It must be explicitly invoked for hardware
testing. Screenshots and captures remain in temporary local QA storage.

Hardware verification on 2026-09-30 used the connected Z8: live view delivered
640 × 424 frames; two consecutive remote exposures in one session transferred
approximately 54 MB lossless NEFs, decoded at 8280 × 5520 into the GPU editor,
and remained available after reopening the catalog. `--repeat` requests the
second real exposure. The automated suite covers 64 tests, including safe
disconnected-helper behavior. This does not establish autofocus accuracy,
portrait live-view orientation, every camera release mode, or High Efficiency
NEF compatibility.

`qa_tether.cjs --switch` uses a mocked camera interface against the scratch
backend to check that creating a project updates the live target without a
disconnect. Unit tests cover future routing, in-flight transfer retention, and
RAW/JPG sibling routing across a switch.
It also checks the default-on automatic-look checkbox and its manual-mode button.
Unit tests verify next-capture recipe inheritance, older-shot exclusion, RAW/JPG
version eligibility, exclusion of spatial retouching, and preference persistence.
