"""Read a UF2's family ID and say which chip it is actually for.

The filename is a label; the family ID inside every 512-byte block is the
thing the bootloader actually matches on.
"""
import struct
import sys

MAGIC0 = 0x0A324655
MAGIC1 = 0x9E5D5157
MAGIC_END = 0x0AB16F30
FLAG_FAMILY_ID = 0x00002000

FAMILIES = {
    0xE48BFF56: "RP2040            (RAK11310, Raspberry Pi Pico)",
    0x1C5F21B0: "nRF52840          (RAK4631)",
    0xADA52840: "nRF52840 Adafruit (RAK4631, Adafruit bootloader)",
    0x621E937A: "nRF52833",
    0xBFDD4EEE: "ESP32-S2",
    0x2B88D29C: "ESP32-C3",
    0x540DDF62: "ESP32-C6",
    0xC47E5767: "ESP32-S3",
}

path = sys.argv[1]
with open(path, "rb") as fh:
    blob = fh.read()

if len(blob) % 512 != 0:
    print("WARNING: size %d is not a multiple of 512 — may not be a UF2" % len(blob))

families = {}
blocks = 0
addrs = []
for off in range(0, len(blob) - 511, 512):
    b = blob[off:off + 512]
    m0, m1, flags, addr, size, blkno, numblk, famid = struct.unpack("<8I", b[:32])
    if m0 != MAGIC0 or m1 != MAGIC1:
        print("block %d: bad magic — not a UF2 file" % (off // 512))
        sys.exit(2)
    if struct.unpack("<I", b[508:512])[0] != MAGIC_END:
        print("block %d: bad end magic" % (off // 512))
        sys.exit(2)
    blocks += 1
    addrs.append(addr)
    if flags & FLAG_FAMILY_ID:
        families[famid] = families.get(famid, 0) + 1

print("file      : %s" % path)
print("size      : %d bytes" % len(blob))
print("blocks    : %d" % blocks)
if addrs:
    print("flash addr: 0x%08X .. 0x%08X" % (min(addrs), max(addrs)))
if not families:
    print("family    : NONE DECLARED (no family ID flag set)")
else:
    for fam, count in sorted(families.items()):
        print("family    : 0x%08X  %s   [%d blocks]"
              % (fam, FAMILIES.get(fam, "UNKNOWN CHIP"), count))
