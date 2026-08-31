#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Brute-force the SayoDevice HID frame checksum (bytes 1-2) against captured
ground-truth frames. Pure stdlib, no device needed. ACCESS: none (offline compute)."""

# Captured full write frames (padded to 63 bytes) with their real chk field (b1,b2).
FRAMES = {
    # keyboard writes (cmd 3c, class 09)
    "key_idx2_kc00": "12 3c 2f 3c 00 10 02 01 00 00 00 e2 04 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 00 00 00 00 03",
    "key_idx2_kcA":  "12 40 2f 3c 00 10 02 01 00 00 00 e2 04 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 04 00 00 00 03",
    "key_idx1_kc00": "12 a8 35 3c 00 10 01 01 00 00 00 4e 0c 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 00 00 00 00 03",
    "key_idx1_kcB":  "12 ad 35 3c 00 10 01 01 00 00 00 4e 0c 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 05 00 00 00 03",
    "key_idx0_kc00": "12 14 3c 3c 00 10 00 01 00 00 00 ba 13 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 00 00 00 00 03",
    "key_idx0_kcC":  "12 1a 3c 3c 00 10 00 01 00 00 00 ba 13 6c 07 08 07 08 07 64 00 00 00 09 00 00 00 06 00 00 00 03",
    # LED writes (cmd 3c, selector 00 11), RGB at 27/28/29
    "led_red":   "12 84 ad 3c 00 11 03 01 00 00 00 40 1f 6c 07 e8 03 e8 03 f4 01 00 00 42 00 64 64 ff 00 00 02",
    "led_green": "12 85 ab 3c 00 11 03 01 00 00 00 40 1f 6c 07 e8 03 e8 03 f4 01 00 00 42 00 64 64 00 ff 00 02",
    "led_blue":  "12 84 ad 3c 00 11 03 01 00 00 00 40 1f 6c 07 e8 03 e8 03 f4 01 00 00 42 00 64 64 00 00 ff 02",
    # rotary Key ID 5 (cmd 3c, class 03) play/pause
    "rot_id5_pp":"12 ae 53 3c 00 10 05 01 01 00 00 52 1c 6c 07 dc 05 b8 0b dc 05 00 00 03 00 00 00 0c 00 00 00 03",
}


def parse(s):
    b = [int(x, 16) for x in s.split()]
    b += [0] * (63 - len(b))
    return b


DATA = {k: parse(v) for k, v in FRAMES.items()}


def real_chk(b):
    return b[1] | (b[2] << 8)  # little-endian: b1 low, b2 high


# ---- candidate algorithms over a byte slice ----
def sum16(sl):
    return sum(sl) & 0xFFFF

def sum8(sl):
    return sum(sl) & 0xFF

def fletcher16_256(sl):
    s1 = s2 = 0
    for x in sl:
        s1 = (s1 + x) & 0xFF
        s2 = (s2 + s1) & 0xFF
    return (s2 << 8) | s1

def fletcher16_255(sl):
    s1 = s2 = 0
    for x in sl:
        s1 = (s1 + x) % 255
        s2 = (s2 + s1) % 255
    return (s2 << 8) | s1

def weighted_index(sl, start_idx):
    return sum(x * (start_idx + i) for i, x in enumerate(sl)) & 0xFFFF

def wordsum_le(sl):
    total = 0
    for i in range(0, len(sl) - 1, 2):
        total += sl[i] | (sl[i + 1] << 8)
    if len(sl) % 2:
        total += sl[-1]
    return total & 0xFFFF

def wordsum_be(sl):
    total = 0
    for i in range(0, len(sl) - 1, 2):
        total += (sl[i] << 8) | sl[i + 1]
    if len(sl) % 2:
        total += sl[-1] << 8
    return total & 0xFFFF

def crc16(sl, poly, init, refin, refout, xorout):
    def rb(v, w):
        r = 0
        for _ in range(w):
            r = (r << 1) | (v & 1); v >>= 1
        return r
    crc = init
    for x in sl:
        if refin: x = rb(x, 8)
        crc ^= x << 8
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    if refout: crc = rb(crc, 16)
    return crc ^ xorout


def try_slices(fn, label):
    """Try fn over every [start:end] slice; report slices matching ALL frames."""
    hits = []
    for start in range(3, 10):
        for end in range(20, 64):
            ok = all(fn(b[start:end]) == real_chk(b) for b in DATA.values())
            if ok:
                hits.append((start, end))
    if hits:
        print(f"  MATCH {label}: slices {hits}")
    return hits


def main():
    print("Ground truth (name: chk):")
    for k, b in DATA.items():
        print(f"  {k:14s} chk=0x{real_chk(b):04x}")
    print("\nBrute-forcing algorithms over all [start:end] slices...")

    found = False
    found |= bool(try_slices(sum16, "sum16"))
    found |= bool(try_slices(lambda sl: sum8(sl), "sum8->16"))
    found |= bool(try_slices(fletcher16_256, "fletcher16/256"))
    found |= bool(try_slices(fletcher16_255, "fletcher16/255"))
    found |= bool(try_slices(wordsum_le, "wordsum_LE"))
    found |= bool(try_slices(wordsum_be, "wordsum_BE"))
    # weighted by absolute index needs start offset; test separately
    for start in range(3, 10):
        for end in range(20, 64):
            if all(weighted_index(b[start:end], start) == real_chk(b) for b in DATA.values()):
                print(f"  MATCH weighted_index: [{start}:{end}]"); found = True

    # CRC16 common variants
    variants = [
        ("CCITT-FALSE", 0x1021, 0xFFFF, False, False, 0x0000),
        ("XMODEM",      0x1021, 0x0000, False, False, 0x0000),
        ("KERMIT",      0x1021, 0x0000, True,  True,  0x0000),
        ("MODBUS",      0x8005, 0xFFFF, True,  True,  0x0000),
        ("IBM/ARC",     0x8005, 0x0000, True,  True,  0x0000),
        ("USB",         0x8005, 0xFFFF, True,  True,  0xFFFF),
    ]
    for name, poly, init, ri, ro, xo in variants:
        for start in range(3, 10):
            for end in range(20, 64):
                if all(crc16(b[start:end], poly, init, ri, ro, xo) == real_chk(b) for b in DATA.values()):
                    print(f"  MATCH CRC16-{name}: [{start}:{end}]"); found = True

    if not found:
        print("  no full-set match yet - inspect deltas below")
        # linearity probe: does changing one byte shift chk linearly?
        pairs = [("key_idx2_kc00","key_idx2_kcA",27),("key_idx1_kc00","key_idx1_kcB",27),
                 ("key_idx0_kc00","key_idx0_kcC",27)]
        for a,c,idx in pairs:
            da = real_chk(DATA[c]) - real_chk(DATA[a])
            db = DATA[c][idx] - DATA[a][idx]
            print(f"    {a}->{c}: dchk={da:+d} dbyte[{idx}]={db:+d}")


if __name__ == "__main__":
    main()
