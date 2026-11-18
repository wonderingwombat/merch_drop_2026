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

## Repo layout
- `site_clone/` - full static download of the web app (protocol reference only).
- `capture/2026-09-01-*.md` - raw HID captures + decoded protocol (keys, LED, rotary, templates).
- `sayo_protocol.py` - proven protocol core. `uv run sayo_protocol.py` runs the offline self-test.
- `tools/crack_checksum.py` - checksum reverse-engineering script.
- `docs/index.html` - the single-page WebHID keypad configurator (keys, dial, LED, modifiers,
  profiles). Served via **GitHub Pages** from the `docs/` folder. `docs/.nojekyll` disables Jekyll.

## Hosting the configurator (GitHub Pages)
The configurator needs **HTTPS** (WebHID is blocked on plain `http://` and `file://`). GitHub Pages
provides that for free:
1. Push to GitHub, then in the repo: **Settings → Pages → Source: "Deploy from a branch" →
   Branch `master`, folder `/docs` → Save.**
2. Wait ~1 min; the page goes live at **https://wonderingwombat.github.io/merch_drop_2026/**
   (Chrome/Edge only — WebHID isn't in Safari/Firefox).

Local dev (also a secure context): `python3 -m http.server 8100` from the repo root, then open
`http://localhost:8100/docs/`.

## Protocol summary (all captured/confirmed)
Device VID `0x8089` / PID `0x0008`, config usage page `0xFF11`, report id `0x21`, 63-byte payload.
Frame `12 [chk16-LE] [cmd] [payload]`; cmd `0x3c`=write, `0x04`=read, `0x06`=save.
Bindings addressed by Key ID (byte6): keys=0,1,2 (class `0x09` keyboard, usage@27);
rotary press=3 / CW=4 / CCW=5 (class `0x03` media, code@27). LED: selector `00 11`, RGB@27/28/29.
Checksum = 16-bit LE word-sum, handled by template + word-delta (see sayo_protocol.py). Details and
full write templates in `capture/2026-09-01-device-and-templates.md`.

**Hardware-confirmed corrections (2026-11-17, via `docs/index.html` on the real unit):**
- Rotary direction is the reverse of the capture labels: physical **clockwise fires id 5**,
  counter-clockwise fires id 4. The configurator's SLOT_DEFS is keyed to this real behaviour.
- **No brightness support.** The device's media enum is exactly `hidmedia_Mute`(8)…`hidmedia_WWWFavorites`(30)
  — 30 codes, no brightness. The official app's entire bindable set is only `hidkey` (keyboard usages),
  these 30 `hidmedia` codes, and `mouseKey`; the sole non-standard key is `hidkey_Power`. Brightness
  (HID Consumer 0x6F/0x70) is not emittable by this firmware — don't re-attempt it.

## Status
- [x] Site cloned
- [x] Architecture + protocol recon
- [x] Scope decided: 3 keys + LED + rotary (FiiO KB1 / CM_F1)
- [x] Live HID capture of all target actions
- [x] Protocol core built + self-test (10/10 real frames reproduced exactly)
- [ ] Live `hidapi` hardware write test (LED=green) - user OK'd, not yet run
- [ ] easygui app (remap keys / rotary / LED / branded profile / save)
- [ ] Branding/injokes decision from user (build placeholders if none)

## Browser-only (WebHID) experiments
- 2026-10-18: `tools/webhid_test.html` as a base64 `data:` URL in Chrome: `origin: null`,
  `isSecureContext: false`, `navigator.hid` missing. **`data:` URLs cannot use WebHID.** Dead end.
- The cloned Flutter app (25 MB) would never fit a data URL anyway (Chrome caps URLs at 2 MB).
- Next: test the same page opened as a local `file://` and/or served over HTTPS.
- Direction (user, 2026-10-18): likes the idea of a **small single-page WebHID configurator**
  (3 keys + rotary + LED, ~20-50 KB) instead of the cloned Flutter app. Parked for now.
  Open question: does it run from `file://`, or does it need HTTPS hosting? (keypad was unplugged during the first test)
