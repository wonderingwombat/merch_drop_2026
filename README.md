# fiio_custom

Reverse-engineering / rebuild project for the SayoDevice web configurator (as used by the FiiO KB1 / SayoDevice keypads), targeting a branded internal Python tool for the dev team.

## Contents
- `site_clone/` - full static download of https://app.sayodevice.com/ (~28 MB), captured 2026-09-01.

## What the original app actually is
- **Flutter web** UI compiled to `main.dart.js`, rendered on a **CanvasKit (Skia WASM)** canvas. No meaningful HTML/CSS to scrape - it's all drawn to a canvas.
- **Device protocol** is a **Rust library compiled to WASM** (`pkg/sayo_lib_rs_bg.wasm`) via `flutter_rust_bridge`.
- Talks to hardware over **WebHID** (`device.sendReport`, `inputreport`).

## Implications for the rebuild
- A native Python app can talk to the device directly via `hidapi` (no browser needed).
- The *transport* and *firmware framing* are visible in the clone; the *semantic command map* (which bytes = which setting) is inside the WASM and needs live HID capture or WASM disassembly to recover.
- `easygui` is enough for a simple remap/utility tool but cannot reproduce the rich canvas UI (LCD/LED/per-key editors). Tkinter/Qt would be needed for parity.

See `/Users/marcu/claude_notes/2026-09-01-sayodevice-clone-recon.md` for full recon notes.

## Status
- [x] Site cloned
- [x] Architecture + protocol recon
- [ ] Scope decision for the Python rebuild
- [ ] Live HID capture of target actions
- [ ] `hidapi` connect prototype
