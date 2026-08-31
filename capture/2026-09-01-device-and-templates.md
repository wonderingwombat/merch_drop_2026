# FiiO KB1 - device identity + full write templates (captured 2026-09-01)

## Device identity (WebHID getDevices, live)
```
productName : FiiO KB1
VID         : 0x8089
PID         : 0x0008
collections : 0xff00:0x01 (vendor), 0xff11:0x02 (vendor CONFIG iface <- we write here),
              0x01:0x02 (keyboard), 0x0c:0x01 (consumer)
Config write: usage_page 0xFF11, usage 0x02, report id 0x21, 63-byte payload (64 w/ id)
```

## Full write templates (the 63-byte payload passed to sendReport(0x21, ...))
Value byte = index 27, class byte = index 23, checksum = bytes 1-2 (16-bit LE word-sum).
```
key_id 0 (keyboard, class 09, was 'C'):
  12 1a 3c 3c 00 10 00 01 00 00 00 ba 13 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 06 00 00 00 03
key_id 1 (keyboard, class 09, was 'B'):
  12 ad 35 3c 00 10 01 01 00 00 00 4e 0c 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 05 00 00 00 03
key_id 2 (keyboard, class 09, was 'A'):
  12 40 2f 3c 00 10 02 01 00 00 00 e2 04 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 04 00 00 00 03
key_id 3 (media, class 03, rotary PRESS, captured as Play/Pause):
  12 f0 45 3c 00 10 03 01 00 00 00 40 1f 6c 07 e8 03 e8 03 f4 01 00 00 03 00 00 00 0c 00 00 00 03
key_id 4 (media, class 03, rotary CW, captured as Play/Pause):
  12 8a 59 3c 00 10 04 01 02 00 00 2e 22 6c 07 dc 05 b8 0b dc 05 00 00 03 00 00 00 0c 00 00 00 03
key_id 5 (media, class 03, rotary CCW, captured as Play/Pause):
  12 ae 53 3c 00 10 05 01 01 00 00 52 1c 6c 07 dc 05 b8 0b dc 05 00 00 03 00 00 00 0c 00 00 00 03
LED effect (selector 00 11, RGB at 27/28/29, captured as blue):
  12 84 ad 3c 00 11 03 01 00 00 00 40 1f 6c 07 e8 03 e8 03 f4 01 00 00 42 00 64 64 00 00 ff 02
SAVE/commit frame:
  12 ca 84 06 00 0d 00 96 72
```

## Media button codes (class 03, value at byte 27) - CONFIRMED by capture
```
Mute=0x08  Bass=0x09(*)  Volume+=0x0a  Volume-=0x0b  Play/Pause=0x0c
Stop=0x0d(*) Prev=0x0e(*) Next=0x0f(*)   (* = inferred from list order, sequential)
```

## Keyboard usage codes (class 09, value at byte 27) = standard USB HID Keyboard usage IDs
A=0x04 ... Z=0x1d, 1=0x1e..0=0x27, Enter=0x28, Esc=0x29, Space=0x2c, F1=0x3a.., arrows 0x4f-0x52.

## Checksum: 16-bit little-endian word-sum (position-dependent). We DON'T need the exact
## range/base: it is linear, so we mutate a captured template and adjust the checksum by the
## word-weighted delta of the changed bytes. Proven exact for keys AND LED (see crack_checksum.py
## / sayo_protocol.py self-test).
