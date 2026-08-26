# Hardware

The boards live in **[offgridevices/offgrid-hardware](https://github.com/offgridevices/offgrid-hardware)**.

The packet logger carrier — the 86 × 58 mm board the RAK19003, the XIAO
ESP32-C6 and the microSD module plug into — is at
[`packet-logger-carrier/`](https://github.com/offgridevices/offgrid-hardware/tree/main/packet-logger-carrier).
Gerbers, bill of materials, 3D models for enclosure design, and the scripts
that generate all of it are there, along with instructions for ordering one.

## Why it is not here

Two reasons.

**Licensing.** This repository is GPL-3.0, inherited from the Meshtastic
libraries the firmware and tooling depend on. A PCB has no such dependency,
and GPL's language — source code, object code, installation information —
does not map onto Gerbers and drill files. The boards are **CERN-OHL-S v2**,
a licence written for hardware with the same reciprocal intent. One licence
per repository is honest; a per-directory split is not.

**Cadence and weight.** Firmware moves weekly. A board revision is a
months-scale event that drags a few megabytes of regenerated binaries behind
it. Keeping them apart means a clone of this repository stays small for
people who only want the measurement tooling.

## The one thing to watch

The firmware drives pins this board defines, so that agreement now spans two
repositories and nothing fails at build time when it drifts.

`tools/tests/test_pinmap.py` checks the pin definitions in
`firmware/src/config.h` against the wiring table in
[`docs/packet-logger-design.md`](../docs/packet-logger-design.md) §5.2. If you
change the wiring, all three have to move together: the firmware, that table,
and the carrier board in the hardware repository.
