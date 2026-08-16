# firmware

Logger firmware for the Seeed XIAO ESP32-C6. Sits on a Meshtastic node's
serial header pretending to be a phone and writes what the radio hears to a
microSD card. No phone, no laptop, no network.

See [`docs/packet-logger-design.md`](../docs/packet-logger-design.md) for the
wiring, the file format, and the bench sequence.

## Build

```sh
pio run                 # compile
pio run -t upload       # flash over USB-C
pio device monitor      # watch the console
```

**Use the platform pinned in `platformio.ini`, not `espressif32`.** The
official PlatformIO ESP32 platform still ships Arduino core 2.x, which has no
ESP32-C6 support and fails with *"This board doesn't support arduino
framework!"*. The `pioarduino` fork carries Arduino core 3.x and is what every
C6 board needs today.

Last built clean at 5.4% of RAM and 27.2% of flash, so there is plenty of room
left for whatever the bench turns up.

## Per-node setup

`src/config.h` is the only file that differs between the four units. Change
`NODE_SHORT_NAME`, flash, label the box. Everything else is identical on
purpose: four units that differ only in a string behave the same way in a
field.

## What it does

**At power-up** it runs a self-test somebody can read while standing there —
card mounts, a row is written *and read back*, the radio answers, its region
and preset and hop limit are shown, fixed position and clock are set, and
which neighbours it can hear during a thirty-second listen. Then it writes all
of that into the log file and the screen blanks.

A failed check is shown and recorded but does **not** stop the node. A logger
running with a bad clock is worth far more than one refusing to start.

**While running** it appends a row per received packet, flushes every five
seconds or ten rows, writes a status row every minute, and refreshes the node
list every five minutes. The button lights the screen for ten seconds.

**If the card fails** it keeps counting, blinks the LED fast, and retries the
mount every five seconds, forever. It never halts.

## Layout

| File | What it owns |
|---|---|
| `config.h` | Per-node settings. The only file that varies between units |
| `log_schema.h` | The CSV contract. Must match `tools/src/fieldlab/schema.py` |
| `logfile.*` | The card: mounting, the boot counter, rows, flushing, recovery |
| `screen.*` | The OLED. Entirely optional at runtime |
| `selftest.*` | The boot checks and how they are rendered |
| `main.cpp` | Callbacks, and the loop |

The Python test suite reads `log_schema.h` and fails if it drifts from the
schema module — the two halves of the contract are written in different
languages and cannot share a definition, so a column added on one side must
not silently go missing on the other.

## Not tested on hardware

Nothing here has met a radio. It compiles and the logic that could be checked
without one has been. The bench sequence in the design document is what turns
that into evidence.
