#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "hidapi==0.14.0",
# ]
# ///
"""
SayoDevice / FiiO KB1 (CM_F1) HID protocol - core.

Reverse-engineered from the official web app (Flutter + Rust->WASM over WebHID).
See capture/2026-09-01-*.md for the raw captures this is built on.

Design: we DON'T reimplement the device's checksum from scratch. Each Key ID / the LED
has one captured "template" write frame (with a known-good checksum). To change a binding
we copy the template, edit the class/value bytes, and adjust the 16-bit checksum by the
word-weighted delta of the bytes we changed. The checksum is a linear 16-bit little-endian
word-sum, so this is exact (validated in self_test() against every captured frame).

ACCESS: USB HID to VID 0x8089 / PID 0x0008 only. No network, no filesystem, no credentials.
Run directly (`./sayo_protocol.py`) to execute the offline self-test (no device needed).
"""
from __future__ import annotations

# ---------------------------------------------------------------- device identity
VID = 0x8089
PID = 0x0008
CONFIG_USAGE_PAGE = 0xFF11   # vendor config interface
CONFIG_USAGE = 0x02
REPORT_ID = 0x21
FRAME_LEN = 63               # payload length (report id is separate)

# ---------------------------------------------------------------- frame offsets
OFF_CMD = 3
OFF_KEY_ID = 6
OFF_CLASS = 23
OFF_VALUE = 27               # keyboard usage / media code (also LED red)
OFF_LED_R, OFF_LED_G, OFF_LED_B = 27, 28, 29

CLASS_KEYBOARD = 0x09
CLASS_MEDIA = 0x03
CMD_WRITE = 0x3C
CMD_SAVE = 0x06


def _hx(s: str) -> list[int]:
    b = [int(x, 16) for x in s.split()]
    return b + [0] * (FRAME_LEN - len(b))


# ---------------------------------------------------------------- captured templates
# 63-byte payloads (the data passed to sendReport(0x21, data) in the web app).
TEMPLATES: dict[int, list[int]] = {
    0: _hx("12 1a 3c 3c 00 10 00 01 00 00 00 ba 13 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 06 00 00 00 03"),
    1: _hx("12 ad 35 3c 00 10 01 01 00 00 00 4e 0c 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 05 00 00 00 03"),
    2: _hx("12 40 2f 3c 00 10 02 01 00 00 00 e2 04 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 04 00 00 00 03"),
    3: _hx("12 f0 45 3c 00 10 03 01 00 00 00 40 1f 6c 07 e8 03 e8 03 f4 01 00 00 03 00 00 00 0c 00 00 00 03"),
    4: _hx("12 8a 59 3c 00 10 04 01 02 00 00 2e 22 6c 07 dc 05 b8 0b dc 05 00 00 03 00 00 00 0c 00 00 00 03"),
    5: _hx("12 ae 53 3c 00 10 05 01 01 00 00 52 1c 6c 07 dc 05 b8 0b dc 05 00 00 03 00 00 00 0c 00 00 00 03"),
}
LED_TEMPLATE = _hx("12 84 ad 3c 00 11 03 01 00 00 00 40 1f 6c 07 e8 03 e8 03 f4 01 00 00 42 00 64 64 00 00 ff 02")
SAVE_FRAME = _hx("12 ca 84 06 00 0d 00 96 72")

# which Key IDs are the three keys vs the rotary encoder
KEY_IDS = (0, 1, 2)
ROTARY_CCW, ROTARY_CW, ROTARY_PRESS = 5, 4, 3

# ---------------------------------------------------------------- value maps
# Standard USB HID keyboard usage IDs (class 0x09).
KEYBOARD_USAGES: dict[str, int] = {}
for i, c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    KEYBOARD_USAGES[c] = 0x04 + i
for i, c in enumerate("1234567890"):
    KEYBOARD_USAGES[c] = 0x1E + i
KEYBOARD_USAGES.update({
    "enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
    "-": 0x2D, "=": 0x2E, "[": 0x2F, "]": 0x30, "\\": 0x31, ";": 0x33, "'": 0x34,
    "`": 0x35, ",": 0x36, ".": 0x37, "/": 0x38, "capslock": 0x39,
    "f1": 0x3A, "f2": 0x3B, "f3": 0x3C, "f4": 0x3D, "f5": 0x3E, "f6": 0x3F,
    "f7": 0x40, "f8": 0x41, "f9": 0x42, "f10": 0x43, "f11": 0x44, "f12": 0x45,
    "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52,
})

# Media / consumer codes (class 0x03). Confirmed by capture where noted.
MEDIA_CODES: dict[str, int] = {
    "mute": 0x08,        # confirmed
    "bass": 0x09,        # inferred (list order)
    "volume+": 0x0A,     # confirmed
    "volume-": 0x0B,     # confirmed
    "play/pause": 0x0C,  # confirmed
    "stop": 0x0D,        # inferred
    "previous": 0x0E,    # inferred
    "next": 0x0F,        # inferred
}


# ---------------------------------------------------------------- checksum (delta method)
def _wordsum_le(frame: list[int], start: int = OFF_CMD) -> int:
    """16-bit little-endian word sum over frame[start:], excluding tag/checksum bytes 0-2."""
    total = 0
    i = start
    while i + 1 < FRAME_LEN:
        total += frame[i] | (frame[i + 1] << 8)
        i += 2
    return total & 0xFFFF


def _template_chk(t: list[int]) -> int:
    return t[1] | (t[2] << 8)


def _apply_checksum(frame: list[int], template: list[int]) -> None:
    """Set frame's checksum = template checksum + word-delta of the changed bytes.

    Exact because the device checksum is a linear 16-bit LE word-sum, so any correct
    base (the template's) plus the delta of what we changed reproduces the real value.
    """
    delta = (_wordsum_le(frame) - _wordsum_le(template)) & 0xFFFF
    chk = (_template_chk(template) + delta) & 0xFFFF
    frame[1] = chk & 0xFF
    frame[2] = (chk >> 8) & 0xFF


# ---------------------------------------------------------------- frame builders
def build_key_binding(key_id: int, value: int, klass: int) -> list[int]:
    if key_id not in TEMPLATES:
        raise ValueError(f"no template for key_id {key_id}")
    f = list(TEMPLATES[key_id])
    f[OFF_CLASS] = klass
    # zero the 32-bit value field then set low byte (all our codes are < 256)
    f[24] = f[25] = f[26] = f[27] = 0
    f[OFF_VALUE] = value & 0xFF
    _apply_checksum(f, TEMPLATES[key_id])
    return f


def build_keyboard(key_id: int, key_name: str) -> list[int]:
    name = key_name.strip().lower()
    if name not in KEYBOARD_USAGES:
        raise ValueError(f"unknown key '{key_name}'")
    return build_key_binding(key_id, KEYBOARD_USAGES[name], CLASS_KEYBOARD)


def build_media(key_id: int, media_name: str) -> list[int]:
    name = media_name.strip().lower()
    if name not in MEDIA_CODES:
        raise ValueError(f"unknown media button '{media_name}'")
    return build_key_binding(key_id, MEDIA_CODES[name], CLASS_MEDIA)


def build_led_rgb(r: int, g: int, b: int) -> list[int]:
    f = list(LED_TEMPLATE)
    f[OFF_LED_R], f[OFF_LED_G], f[OFF_LED_B] = r & 0xFF, g & 0xFF, b & 0xFF
    _apply_checksum(f, LED_TEMPLATE)
    return f


def to_report(frame: list[int]) -> bytes:
    """Prepend the report id -> the 64-byte buffer for hid_write."""
    return bytes([REPORT_ID] + frame)


# ---------------------------------------------------------------- offline self-test
def self_test() -> None:
    """Reconstruct every captured ground-truth frame from a template + values and
    assert the checksum matches. No device required."""
    # (name, expected_full_frame, builder)
    GT = {
        "key0=C": ("12 1a 3c 3c 00 10 00 01 00 00 00 ba 13 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 06 00 00 00 03",
                   lambda: build_keyboard(0, "c")),
        "key1=B": ("12 ad 35 3c 00 10 01 01 00 00 00 4e 0c 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 05 00 00 00 03",
                   lambda: build_keyboard(1, "b")),
        "key2=A": ("12 40 2f 3c 00 10 02 01 00 00 00 e2 04 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 04 00 00 00 03",
                   lambda: build_keyboard(2, "a")),
        # keyboard remaps to NEW values -> must match the app's clear-frame checksums we captured
        "key2=clear": ("12 3c 2f 3c 00 10 02 01 00 00 00 e2 04 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 00 00 00 00 03",
                       lambda: build_key_binding(2, 0x00, CLASS_KEYBOARD)),
        "key1=clear": ("12 a8 35 3c 00 10 01 01 00 00 00 4e 0c 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 00 00 00 00 03",
                       lambda: build_key_binding(1, 0x00, CLASS_KEYBOARD)),
        "key0=clear": ("12 14 3c 3c 00 10 00 01 00 00 00 ba 13 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 00 00 00 00 03",
                       lambda: build_key_binding(0, 0x00, CLASS_KEYBOARD)),
        # rotary media (only the captured play/pause template value is real ground truth)
        "rot5=play/pause": ("12 ae 53 3c 00 10 05 01 01 00 00 52 1c 6c 07 dc 05 b8 0b dc 05 00 00 03 00 00 00 0c 00 00 00 03",
                            lambda: build_media(5, "play/pause")),
        # LED
        "led_red":   ("12 84 ad 3c 00 11 03 01 00 00 00 40 1f 6c 07 e8 03 e8 03 f4 01 00 00 42 00 64 64 ff 00 00 02",
                      lambda: build_led_rgb(0xFF, 0x00, 0x00)),
        "led_green": ("12 85 ab 3c 00 11 03 01 00 00 00 40 1f 6c 07 e8 03 e8 03 f4 01 00 00 42 00 64 64 00 ff 00 02",
                      lambda: build_led_rgb(0x00, 0xFF, 0x00)),
        "led_blue":  ("12 84 ad 3c 00 11 03 01 00 00 00 40 1f 6c 07 e8 03 e8 03 f4 01 00 00 42 00 64 64 00 00 ff 02",
                      lambda: build_led_rgb(0x00, 0x00, 0xFF)),
    }
    ok = 0
    for name, (expected, builder) in GT.items():
        exp = _hx(expected)
        got = builder()
        # compare checksum bytes AND the meaningful payload
        if got[:32] == exp[:32]:
            ok += 1
            print(f"  PASS {name}: chk=0x{got[1] | got[2] << 8:04x}")
        else:
            diffs = [(i, exp[i], got[i]) for i in range(32) if exp[i] != got[i]]
            print(f"  FAIL {name}: diffs (idx,exp,got)={diffs}")
    print(f"\n{ok}/{len(GT)} frames reproduced exactly.")
    assert ok == len(GT), "self-test failed"
    print("SELF-TEST PASSED - checksum-delta method is exact.")


if __name__ == "__main__":
    self_test()
