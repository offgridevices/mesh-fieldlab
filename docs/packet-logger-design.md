# Standalone packet logger — design

**Status:** design agreed, implementation starting. Hardware not yet in hand.
**Date:** 2026-08-11

A self-contained field logger that records per-packet RSSI, SNR, hop data and node identity from a Meshtastic mesh to a microSD card, with **no phone and no laptop present at the node**. Data is retrieved afterwards by pulling the card.

Four are being built. They run unattended for a full field session.

---

## 1. What this is

A microSD packet logger for a Meshtastic node. It records the metadata of every packet the node receives — signal strength, signal-to-noise ratio, hop count, sender, packet ID — as CSV, unattended, with no phone or computer attached.

Stock tooling does not cover this. A paired phone displays signal strength live but writes nothing to disk and has to stay within Bluetooth range. The natural alternative — having the radio firmware write the file itself — does not work on this hardware, for reasons worth documenting since the official documentation currently suggests otherwise.

## 2. Why the radio cannot do this alone

Verified directly against `meshtastic/firmware` at commit `546b9d9` (2026-08-11) and `meshtastic/Meshtastic-arduino` at `v0.0.7`. If you are reading this later, re-check — these are the kind of facts that change.

### 2.1 Serial `LOG` mode is documented but not implemented

The Meshtastic docs describe serial mode `LOG` as "ideal for logging mesh activity to a data logger such as a SparkFun OpenLog", and the protobuf enum defines both `LOG = 9` and `LOGTEXT = 10`.

No handler exists. In `src/modules/SerialModule.cpp`, `handleReceived` branches on `PROTO`, `DEFAULT`/`SIMPLE`, `TEXTMSG`, `NMEA`/`CALTOPO`, `WS85` and `MS_CONFIG`. Setting a device to mode 9 or 10 produces no output at all.

**The documentation is ahead of the code.** Anyone planning around `LOG` mode should test it before building on it.

### 2.2 Range Test cannot save to file on nRF52 boards

`RangeTestModule` looks like it solves this — it has a `save` option and writes a CSV including RSSI. But in `src/modules/RangeTestModule.cpp`, the entire body of `appendFile` is wrapped in `#ifdef ARCH_ESP32`. The `#else` branch logs `Can't store range test results - ESP32 only` and returns.

The call site *is* compiled for nRF52, so on a RAK4631 the function is called on every packet and does nothing. `range_test.save` silently has no effect.

Range Test remains useful as a **traffic generator**, and is used that way here.

### 2.3 GPS and a serial logger are mutually exclusive on the RAK19003

On the RAK19003 base board, WisBlock sensor slots C and D carry `TXD1` and `RXD1` — the same UART1 that the `J7` header exposes. A UART GPS module in either slot contends with the serial logger for the same peripheral.

You can have a GPS module or a serial logger, not both. Positions are handled another way (§7).

### 2.4 What does work

`SerialModule` is compiled for nRF52 (the arch guard in `SerialModule.h` includes `ARCH_NRF52`), and `PROTO` mode exposes the full Meshtastic client API over the serial port — the same protocol the phone apps use. That is the path this design takes.

## 3. Architecture

Each node is a Meshtastic radio, a small logger microcontroller pretending to be a phone, and a memory card.

```
   [ RAK4631 + RAK19003 base ]                 [ XIAO ESP32-C6 ]
   stock Meshtastic firmware                   Meshtastic-arduino (forked)
   Serial Module = PROTO                       acts as a client, as a phone would
   whip antenna via U.FL -> SMA pigtail
                                                        |
   J7 pin 2  TX1  ------------------------->  D7 (GPIO17) RX
   J7 pin 1  RX1  <-------------------------  D6 (GPIO16) TX
   J7 pin 3  GND  --------------------------  GND   (signal return)
   J6 pin 1  VDD 3.3V --------------------->  3V3
   J6 pin 2  GND  --------------------------  GND   (power return)
                                                        |
                                                        v
                                            [ 3.3V microSD breakout ]
                                            SCK D8 / MISO D9 / MOSI D10 / CS D3

   P2  <---  one ~2000 mAh LiPo (the only battery in the node)
```

The radio runs unmodified firmware. All custom code lives on the logger board.

### 3.1 The logger must transmit, not just listen

A passive tap on the radio's transmit line does not work. The client has to talk back:

- The radio streams nothing until it receives a `want_config_id` request. Silence in, silence out.
- The library sends a heartbeat every 60 seconds. The firmware comment is explicit — it cannot detect whether a client is attached, so it infers presence from recent messages.

A receive-only wiring goes quiet after about a minute. **Both directions must be connected.**

### 3.2 Alternatives considered and rejected

| Option | Why not |
|---|---|
| Range Test `save` | ESP32-only; these boards are nRF52 (§2.2) |
| Serial `LOG` mode + OpenLog | Not implemented in firmware (§2.1) |
| Phone or laptop at each node | Not possible with nodes kilometres apart and two people |
| Raspberry Pi Zero 2 W | Chronic availability problems |
| Raspberry Pi 5 | Needs 5 V at several amps; will not run from a 3.7 V LiPo |
| XIAO nRF52840 / RP2040 / SAMD21 | Library falls back to software serial — unreliable at 38400 continuous |
| SD module with a level-shifter chip | Its regulator wants 4.5–5.5 V. There is no 5 V rail on a battery node |
| Separate LoRa sniffer per node | Measures the sniffer's link, not the node's |

## 4. The library change

The logger uses [`meshtastic/Meshtastic-arduino`](https://github.com/meshtastic/Meshtastic-arduino), which speaks the client protocol over a wire. It needs one change.

**The library decodes RSSI and SNR and then discards them.** `meshtastic_MeshPacket` carries `rx_rssi` and `rx_snr`; the library's nanopb decode populates both. But all three public callbacks — text message, portnum, encrypted — omit them from their signatures. Neither field is read anywhere in `mt_protocol.cpp`. There is no setting that changes this.

Since RSSI and SNR are the entire measurement, this is not optional.

### 4.1 The change

Add a fourth callback carrying the full packet metadata, fired at the top of `handle_mesh_packet` for **every** packet — before the portnum switch, whose `default:` branch would otherwise drop unrecognised port numbers from the log entirely.

```c
typedef struct {
  uint32_t from, to, id, rx_time;
  uint8_t  channel;
  float    rx_snr;
  int32_t  rx_rssi;
  uint8_t  hop_limit, hop_start, next_hop, relay_node;
  bool     via_mqtt, is_decoded;
  uint32_t portnum;      // valid only when is_decoded
  uint16_t payload_size;
} mt_packet_meta_t;

void set_packet_meta_callback(void (*cb)(const mt_packet_meta_t *meta));
```

Roughly 30 lines across two files. **Existing callback signatures and return values are untouched**, so the library's own examples still compile and future merges stay simple. With no callback registered the added cost is one null check per packet.

**Status: written, and pinned below.** The change also ships an example sketch and a host-side test suite that builds the library against a stub Arduino layer, so the callback can be exercised on a development machine. Twenty-eight checks cover field-by-field propagation, direct versus relayed receptions, encrypted payloads, unrecognised port numbers, and registering and unregistering the callback. Passing them says nothing about real hardware — that is what §12 is for — but it means the first bench session starts from code already known to compile and behave.

### 4.2 Delivered as a fork

The change lives in a **fork of `Meshtastic-arduino` under the `offgridevices` org**, and this repository references it pinned to an exact commit:

```ini
lib_deps = https://github.com/offgridevices/Meshtastic-arduino.git#8f17d8010a916ca1307dc9ae0da31bb4964b17d7
```

This keeps the repository's no-vendored-source rule intact — what is committed here is a reference, not somebody else's code. It also satisfies GPL-3.0's requirement that modified versions carry clear notice of change, structurally: the fork's commit history *is* the notice.

**Pin to a commit, never a branch.** A floating reference means the firmware that produced a given day's measurements can no longer be rebuilt, and reproducibility is most of the reason to work this way.

**Fork base is upstream `master` at `04af41a`**, not the `v0.0.7` tag. The tag predates a substantial May 2025 rework (upstream #42) that restructured packet handling and added the portnum and encrypted callbacks; the change described above builds directly on that structure and would be considerably more awkward against the tag. Most recent upstream source change: January 2026.

The change will be offered upstream once it has proven itself in a real multi-node field run. Upstream does merge outside contributions — the rework above came from a community pull request — so this has a reasonable chance of being accepted rather than living as a fork forever.

## 5. Hardware

### 5.1 Per node

| Item | Notes |
|---|---|
| RAK4631 Core + RAK19003 Mini base | nRF52840 MCU, SX1262 radio. Arduino bootloader, not RUI3 |
| Seeed XIAO ESP32-C6 | Needs Arduino ESP32 core 3.x or newer |
| 3.3 V microSD breakout | Bare socket. Power pin must read **3V3**, not 5 V |
| microSD card | 32 GB or smaller, **FAT32, MBR partition scheme**. On macOS that is Disk Utility → *Show All Devices* → select the **card**, not the volume → Erase → Format `MS-DOS (FAT)`, Scheme `Master Boot Record`. exFAT does not work with the Arduino SD library, and a GUID scheme often fails to mount. The card is left empty; the firmware creates its own file |
| 915 MHz whip antenna | Same model on all four within a run |
| U.FL → SMA pigtail | |
| LiPo ~2000 mAh, JST-PH 2.0 | Protected cell |
| 0.91" 128×32 OLED, SSD1306, I²C | Status display. Four-pin module; must accept 3.3 V |
| SPST slide switch, ≥1 A | Inline on the battery positive lead. Recessed or guarded |
| Momentary push button | Wakes the display. Panel-mounted, beside the switch |
| 100 µF electrolytic × 2, 0.1 µF ceramic × 2 | One pair at the logger, one at the card |
| 10 kΩ × 2 | Contingency only — MISO and CS pull-ups if mounts prove flaky |

### 5.2 Wiring

| RAK19003 | Signal | XIAO ESP32-C6 | GPIO |
|---|---|---|---|
| J7 pin 2 | TX | **D7** (RX) | 17 |
| J7 pin 1 | RX | **D6** (TX) | 16 |
| J7 pin 3 | GND | GND | — |
| J6 pin 1 | VDD 3.3 V | 3V3 | — |
| J6 pin 2 | GND | GND | — |
| J7 pin 4 | BOOT | **do not connect** | — |

**Wire by the printed label, not by these pin numbers.** RAK changed which UART reaches `J7` between board revisions and did not update the datasheet: Rev B silkscreens `RX1`/`TX1`, Rev D and later silkscreen `RX0`/`TX0`. The positions and the wiring are identical — only the radio's configuration differs, which is §8.

**`J6` carries `VDD`, which is the always-on 3.3 V rail.** The switched rail is `3V3_S`, controlled by `IO2` from the Core module, and it feeds the sensor slots. Powering the logger from `VDD` means the radio's own power management cannot cut it. Worth confirming with a meter on the first board anyway.

The `RAK4630` marking on the Core module is the radio stamp soldered to it; the module as a whole is the `RAK4631`, which is the Meshtastic build to flash, and it needs the **Arduino bootloader, not RUI3**.

| microSD module | XIAO | GPIO |
|---|---|---|
| CLK *(labelled SCK on some modules)* | D8 | 19 |
| MISO | D9 | 20 |
| MOSI | D10 | 18 |
| CS | D3 | 21 |
| 3V3, GND | 3V3, GND | — |

**The module must be 3.3 V native.** Many cheap microSD breakouts carry an `AMS1117` regulator and a `74LVC125` level shifter and expect 5 V, which does not exist anywhere in this build. A module whose only power pin is labelled `3V3` and which has no regulator on it is the right kind.

| OLED (SSD1306) | XIAO | GPIO |
|---|---|---|
| SDA | D4 | 22 |
| SCL *(labelled `SCK` on some modules — it is the I²C clock, not SPI)* | D5 | 23 |
| VCC, GND | 3V3, GND | — |

**Check the power and ground order before wiring.** These modules ship as `GND VCC SCL SDA` and as `VCC GND SCL SDA`, and reversing the first two is the usual way to destroy one.

| Panel control | XIAO | GPIO |
|---|---|---|
| Momentary button, other leg to GND | D0 | 0 |
| Slide switch | *not wired to the logger* — see §5.3 | — |

**The display is on I²C, deliberately.** The C6 has exactly one hardware SPI bus and the card already owns it. Putting the display on a separate two-wire bus means a dead screen, a shorted display wire, or a display library that misbehaves cannot disturb a card write. The card's job is the only one that matters after the node is walked away from.

The button uses the internal pull-up and reads low when pressed; no external resistor.

**Do not use the XIAO's own BOOT button for this.** It is the boot-select strapping pin, so holding it while the power switch is flicked on puts the board into firmware-update mode instead of logging — a silent failure in exactly the situation the switch creates. It is also unreachable once the enclosure is sealed.

Pins after all of the above: **D1 and D2 spare.**

Cross-connect rule: each device's transmit goes to the other's receive. Getting this backwards is the most common cause of "no data".

Cover the BOOT pad with Kapton so a stray strand cannot bridge to it.

**Known quirk:** GPIO16/17 are the C6's boot-log pins. At power-up the ROM bootloader may emit characters into the radio's receive line. Harmless — the protocol framing rejects it — but if it causes instability, any GPIO can be reassigned via `Serial1.begin(baud, SERIAL_8N1, rx, tx)`.

### 5.3 Power

One battery per node, on the radio's `P2` connector. The logger, card and display all run from the radio's 3.3 V rail via `J6`.

**The switch goes in the battery's positive lead, between the cell and `P2`** — not anywhere on the logger. It cuts power to the whole node at once, which is the point: everything stops together and the log simply ends.

Three consequences worth knowing before the first field day:

- **USB overrides it.** Plugging USB into the radio powers the node whether the switch is on or off. On the bench you will forget this and conclude the switch is broken.
- **Charging needs the switch on.** With it off, the radio's charger is disconnected from the cell.
- **Power-cycling is a normal operation, not a fault.** Each boot opens a new file stamped with the date and time it started, so nothing is ever overwritten, no session is lost by turning a node off and on, and no single file grows without bound. Switch a node off on Tuesday and on again on Thursday and you get two files that say so on the outside.

Why single-supply beats a split one: only one connector ever sees a battery, so the polarity check happens once; and if power fails, everything stops together and the log simply ends — rather than the logger dying silently while the radio keeps transmitting.

| Device | Average | Peak |
|---|---|---|
| RAK4631 + base, mostly receiving | 20–35 mA | 130 mA transmit, ~1 s bursts |
| XIAO at 80 MHz, radios off | 20–35 mA | — |
| SD module, one write per 2 s | 5–15 mA | 30–100 mA, few-ms bursts |
| OLED, blanked after boot | <0.1 mA | 5–8 mA while displaying |
| **Total** | **design to 80 mA** | ~275 mA worst case |

The display is the one part that is switched off in software rather than left running. It is lit for the thirty-second boot test and for ten seconds per button press; the rest of the session it is asleep and draws microamps. Left permanently lit it would add roughly a tenth to the node's total draw for information nobody is standing there to read.

The base board's 3.3 V rail is rated 750 mA, so worst case is about a third of budget.

Estimated runtime on 2000 mAh, derated for real capacity, cutoff voltage and summer heat: **roughly 17 hours**, about twice an eight-hour session. **These are estimates and must be replaced with measurements.**

### 5.4 Safety

- Battery voltage must not exceed **4.3 V** — base board absolute maximum.
- **The RAK19003 battery connector is reverse-polarity versus the common hobby JST-PH pinout.** Confirm with a meter before every first connection. Label every battery.
- **Adding the switch means cutting a battery lead**, which is a fresh opportunity to get that polarity wrong on a connector that is already backwards. Cut and splice one lead at a time so the two are never both open, keep the switch in the positive leg, sleeve the joint, and meter the connector again afterwards. Never cut both leads at once — a LiPo with two bare ends is a short waiting for a workbench.
- First power-up on a **current-limited bench supply**, never a LiPo. Set 3.9 V, 200 mA limit; expect 20–60 mA. Pinned at the limit means a short; near zero means an open or reversed connection.
- **A bench supply on `P2` is a fine substitute for the cell on the bench**, and is the better way to work up to the first field day. Stay inside the battery range — **3.8–4.0 V**, never above the 4.3 V absolute maximum, and not as low as 3.3 V or the regulator drops out under load. Raise the limit to **500 mA once the radio transmits**, because 130 mA bursts against a 200 mA limit brown the node out and read as random resets.
- **Never run USB and a bench supply at the same time.** The base board charges a cell from USB, and with a supply on `P2` the charger pushes current into a source that cannot absorb it. USB alone for flashing and configuring; supply alone for powering.
- **Confirm `J6` reads 3.3 V with a meter before connecting anything downstream.** One probe, and it is the difference between a working node and three dead modules.
- **Never plug USB into the logger board while it is being fed 3.3 V from the radio.** One source at a time. Charging via the radio's USB is fine.
- **Never power the radio with no antenna attached.** Transmit power reflects into the amplifier, and the measurement is invalid anyway.

## 6. File format

One file per node per power cycle: `/LOG_<SHORTNAME>_<YYYYMMDD>_<HHMM>.csv`

The stamp is the node's **local** time at the moment logging started — a person holding a box of cards wants to recognise the afternoon they collected them, and no file can grow without bound because switching a node off ends it. Two boots inside the same minute, which is how a brownout loop looks, break the collision with a trailing `-2`, `-3`.

**Every timestamp inside the rows stays UTC.** People get local time on the outside of the file; machines get UTC on the inside, so no analysis ever has to reason about which side of a daylight-saving change a session landed on. The `BOOT` row records `tz` and `utcoff`, which is what lets the local-time name be turned back into UTC without anyone remembering which week the clocks changed.

**Nothing is logged until the clock is set.** The boot holds after the self-test and waits for the time, showing on screen what it is waiting for, because a file that starts before the clock cannot be lined up against the other three and the rows written in that window would be the only ones in the session with no absolute time on them. See §9.2.

**The wait is bounded, not absolute.** If the time never arrives the node logs anyway, under `/LOG_<SHORTNAME>_<BOOTCOUNT>.csv`, and the `BOOT` row records how long it waited in `clkwait`. An undated file still holds every RSSI and SNR reading and every link statistic within itself; coming home with nothing because a phone would not pair is not a trade worth making. If the clock turns up later the file is renamed in place. A boot-counter name surviving in a delivered set therefore means one specific thing: **that node waited, gave up, and never learned the time all session.** `validate-csv` reports this as `FILENAME_NO_CLOCK` rather than leaving it to be noticed.

Where the time comes from at all is §8.

```
schema_ver,uptime_ms,dev_rx_time,rx_node,tx_node,pkt_id,rx_rssi_dbm,rx_snr_db,
hop_limit,hop_start,hops_used,relay_node,next_hop,via_mqtt,portnum,payload_size,
channel,row_type,extra
```

`tools/src/fieldlab/schema.py` is the machine-readable version of this section, and `validate-csv --schema` prints the exact header the firmware must write.

| Field | Meaning |
|---|---|
| `schema_ver` | Starts at 3. Bump on any change |
| `uptime_ms` | Milliseconds since boot — the authoritative relative clock |
| `dev_rx_time` | Device epoch seconds — absolute clock, `0` if never set |
| `rx_node` | The logging node. Constant for the whole file |
| `tx_node` | Packet originator on `PKT` rows; the node being described on `NODE` rows |
| `pkt_id` | Dedupe key for flood copies |
| `rx_rssi_dbm` | Negative; closer to zero is stronger. **`0` means locally originated — filter out** |
| `rx_snr_db` | LoRa decodes to roughly −20 dB |
| `hop_limit` / `hop_start` | Remaining hops, and hops the packet started with |
| `hops_used` | Computed as `hop_start - hop_limit`. **`0` means direct reception** |
| `relay_node` / `next_hop` | Single bytes — the *last byte* of a node number, not a whole one. Routing hints, `0` if none |
| `via_mqtt` | Must be `0`; anything else means an internet gateway is polluting the data |
| `portnum`, `payload_size`, `channel` | Application port, byte count, channel index |
| `row_type` | `PKT` \| `STATUS` \| `NODE` \| `BOOT` |
| `extra` | Empty on `PKT` rows. Everything a non-packet row needs to say, as `key=value` pairs joined by `;` |

### 6.1 Non-packet rows

Four kinds of row share one set of columns, because one open file on a microSD card is far more robust on an unattended node than four. The packet columns are fixed and typed; anything a `BOOT`, `STATUS` or `NODE` row needs beyond them goes in `extra`. Packet columns are written as `0` on those rows, so a reader filtering by `row_type` never has to wonder whether a value is real.

Values may not contain a comma or a semicolon. That keeps the field unquoted and readable by any CSV parser, and a stray separator is reported as an error rather than silently truncating a value.

| Row | Written | Required in `extra` |
|---|---|---|
| `BOOT` | Once at startup | `fw`, `preset`, `boot`, `lat`, `lon`, `alt`, `ant` |
| `BOOT` also carries | optionally | `st_card`, `st_write`, `st_radio`, `st_pos`, `st_clock`, `st_heard`, `batt`, `disp` — what the boot self-test (§9.1) found |
| `BOOT` also carries | on a resumed file | `resume` — seconds of session already elapsed when this file was opened, because the card arrived late or was swapped (§9.4) |
| `STATUS` | Every 60 s | `rows`, `sd_ok`, `heap` |
| `STATUS` also carries | optionally | `drops` — rows formed with nowhere to write them; `recov` — the blocks that just came back, joined with `+` (§9.4) |
| `NODE` | Every 300 s, one row per known node | `name`, `lat`, `lon`, `batt`, `last_heard` |

Adding an **optional** key does not bump the schema version: a reader that does not know it emits a warning and carries on, and every old file stays valid. Adding a column, changing a range, or adding a *required* key does.

### 6.2 The checker

**This format is the contract between the logger and the analysis tooling**, so its checker was written before the firmware. `validate-csv` separates two kinds of problem.

An **error** means the file cannot be trusted: a wrong header, an impossible value, a hop count that contradicts itself, a node apparently receiving its own transmission, packets that arrived over MQTT rather than the air, a fixed position left at 0,0. Analysing a file with errors produces numbers that look reasonable and mean nothing.

A **warning** means the file is readable but something is worth knowing: a truncated last row where the node lost power mid-write, a gap where the status heartbeat stopped, a link with too few packets to take a median from.

The checker also re-reports whatever the boot self-test found, so a file can be judged weeks later without anyone having to remember what the screen said in the field.

Run it on the card before leaving the site:

```bash
uv run validate-csv /Volumes/LOGGER/ --min-packets 100
```

`synth-log` writes schema-valid files with invented numbers, so the analysis tooling can be built and tested before there is hardware to record anything real.

## 7. Position and time without GPS

A GPS module cannot coexist with the logger (§2.3), and is not needed.

**Position is set from a phone, on site, at the moment the node is placed.** Everything else about a node is configured once on a bench and never touched again; position is the one setting that cannot be, because it is not known until somebody is standing where the node will sit. Requiring a laptop for it would mean carrying one to every drop point.

So the deployment step is: connect the Meshtastic app over Bluetooth, open the position settings, **enter the coordinate and switch fixed position on**, disconnect, walk away. The logger reads the result back off the radio and shows it, which is what makes the phone enough.

```bash
# The same thing over USB, for a bench node or to check what the phone wrote.
meshtastic --port <PORT> --setlat <LAT> --setlon <LON> --setalt <ALT> \
  --set position.fixed_position true
```

**`fixed_position` does not create a coordinate. It freezes the one the node already has.** A node that has never held a position has nothing to freeze, so the switch does nothing at all — while the app shows it on, which is the trap. The order is therefore not optional:

1. **Fixed position OFF.** A node that already considers itself fixed may ignore what the phone sends it.
2. **Let the phone share its location with the node,** and wait for a send to actually happen. The share interval is a setting; shortening it to fifteen seconds is worth doing before a deployment day, because the default leaves somebody standing in a field waiting for a minute with no indication of why.
3. **Confirm the node now holds a position** — it appears on the app's map.
4. **Fixed position ON.** This is the step that makes it permanent, and it can only work now.
5. **Confirm on the logger's screen** that the position block is filled before walking away.

Step 5 is the one that matters, because it is the only check that reads the radio rather than the phone. A node with the flag set and no coordinate behind it joins the mesh, relays traffic, looks entirely healthy from the app, and records a whole session of rows that can never be tied to a place. The logger therefore treats position as set only when a coordinate is actually there (§9.1) — the flag alone is not evidence, and was believed for most of one bench session precisely because it looks like it is.

Record the intended position as well as the one actually used — the difference between them matters when interpreting the results.

**Position flags** control which fields ride along in a transmitted position. Most of them — satellites in view, heading, speed, dilution of precision, geoidal separation — come from a GPS receiver, and there is none here, so they carry nothing. Altitude is the one that earns its place. Whatever is chosen, **set all four nodes identically**: the cost of a stray flag is not airtime, it is another axis on which one node can quietly differ from the other three.

**Altitude.** Do not take altitude from GPS. Consumer GPS vertical accuracy is ±10–20 m, roughly twice as bad as horizontal. Instead:

```
node altitude = ground elevation at (lat, lon) from a 1 m DEM
              + height above ground, measured with a tape
```

Both terms are more accurate than any GPS module you could attach. This makes **measured height above ground a required field** on the field log sheet.

**Time.** The logger has no clock of its own. The XIAO has no battery-backed RTC, so every cold boot starts knowing nothing, and the only automatic source of real time is the radio — which stamps received packets with `rx_time`, and only knows the time itself if something told it.

That makes the chain worth stating plainly, because every link can break:

| Step | What supplies it | What happens if it is missing |
|---|---|---|
| Something knows the time | A GPS on any node, or a laptop running the Meshtastic CLI | **Nothing on the mesh has a clock, ever** |
| The radio learns it | CLI on connect, or another node propagating it over the mesh | That node's rows have `dev_rx_time = 0` |
| The logger learns it | `rx_time` on the first packet it receives | The file keeps its boot-counter name |

The practical consequence: **a full power-down loses the time.** The nRF52840 in the radio has no battery-backed clock either, so a node switched off on Tuesday and switched on again on Thursday starts with no idea what day it is, and stays that way until a packet arrives from something that does know.

Two ways to close that, and they are not equivalent:

- **Give one node a GPS.** It reacquires time by itself on every power-up and seeds the whole mesh. This is the only option that survives an unattended power cycle in a field with no laptop present, which is exactly the workflow the logger is built for.
- **Push the clock from the CLI before each deployment.** Connecting all four nodes to one laptop in one session gives every node correct absolute time and costs nothing extra. It has to be redone after every full power-down.

Until one of those happens the logger still records everything — `uptime_ms` is unaffected, RSSI and SNR are unaffected, and per-link statistics within a single file are unaffected. What is lost is the ability to line one node's file up against another's, and the ability to date the file.

This is **unverified** and must be tested on the bench. If it does not hold, fall back to `uptime_ms` plus a manually recorded start time — sufficient here, because the analysis computes session medians rather than time-of-flight.

## 8. Radio configuration

Identical on all four nodes except name and position.

```bash
meshtastic --port <PORT> \
  --set serial.enabled true \
  --set serial.mode PROTO \
  --set serial.txd 20 --set serial.rxd 19 \
  --set serial.baud BAUD_38400 \
  --set position.gps_mode NOT_PRESENT \
  --set lora.region US --set lora.modem_preset LONG_FAST \
  --set device.role CLIENT --set lora.hop_limit 3
```

Notes that will cost you an afternoon if missed:

- **Baud must be set explicitly on both sides.** The firmware default is 38400; the Arduino library's own default is 9600. A mismatch produces silent garbage.
- `override_console_serial_port` is valid **only** with NMEA and CALTOPO. With PROTO it produces a config error and the module will not start. Leave it false.
- `NOT_PRESENT` matters because the same UART routes to sensor slots C and D.
- **The pin numbers depend on the base board revision, and the revision is printed on the board.** RAK moved the UART that reaches `J7` at Rev D: Rev B exposes UART1 there, Rev D and later expose UART0. The wiring is identical; only these two numbers change.

  | RAK19003 revision | `J7` silkscreen | `serial.rxd` | `serial.txd` |
  |---|---|---|---|
  | Rev B | `RX1` / `TX1` | 15 | 16 |
  | **Rev D, Rev E** | `RX0` / `TX0` | **19** | **20** |

  The command above is set for **Rev E**. This was previously an open item to be resolved by trial; it is resolved by reading the silkscreen. Confirmed against the RAKwireless forum thread on the Rev E schematic change, Meshtastic issue #2267, and Meshtastic's own serial-module documentation, which gives 20/19 for "RAK19003 v2 variants" and 16/15 for the RAK19007.
- Keep the modem preset identical across all nodes and all runs. Changing spreading factor mid-experiment invalidates every comparison.

Save `meshtastic --info` for every node alongside the logs. Config drift between nodes is the most common invisible way to ruin a test.

**Redact it first.** `--info` prints the node's PKI **private key** in its `security` block, and its fixed position with it. A private key in a public repository lets anyone impersonate that node on the mesh, and publishing one cannot be undone — a rotation on every affected node is the only remedy. Strip the `security` block and commit the result as `config/<node>.redacted.json`; `.gitignore` is set so the raw dump cannot be added by accident. This is what `configure_node.py` will write, so the redaction is not left to whoever is holding the laptop that day.

## 9. Firmware behaviour

```
setup()
  init display; if it does not answer, carry on regardless — see below
  read and increment boot counter in NVS
  run the boot self-test (§9.1), showing each result as it lands
  if the clock is not set, hold and wait for it (§9.2), up to CLOCK_WAIT_MS
  open /LOG_<SHORTNAME>_<YYYYMMDD>_<HHMM>.csv, write header and BOOT row
    (or /LOG_<SHORTNAME>_<BOOTCOUNT>.csv if the wait timed out, renamed later)
  init serial to the radio at 38400, register the packet-metadata callback
  request node report

loop()
  service the protocol (handles want_config and the 60 s heartbeat)
  on each packet: append one row, compute hops_used, increment counters
  flush every 5 s or 10 rows, whichever comes first
  re-attempt whatever is currently broken (§9.4)
  every 60 s: STATUS row
  every 300 s: refresh node report
  on button press: wake the display 10 s, or step one page deeper (§9.3)
  LED: slow blink healthy | double-blink packet logged recently | fast continuous SD failure
```

### 9.1 The boot self-test

The node is switched on, watched for half a minute, and walked away from. That half minute is the only chance to notice a problem before it costs a session, so the test answers the questions that are expensive to get wrong — not merely "did it start".

Each line appears as its check completes, so a hang is visible at the step that hung.

| Check | What it proves | Failure means |
|---|---|---|
| Card mounts | The socket and wiring work | Reseat the card |
| **A row is written, flushed, and read back** | The card actually accepts data | A card that mounts but cannot write is the worst failure mode there is — it looks healthy for hours |
| Free space, and hours it will hold | The session fits | Swap the card |
| Radio answers on the serial link | Wiring, baud rate and PROTO mode are all correct at once | See §8; this is the single most common setup failure |
| Region, preset, hop limit | This node matches the others | Config drift silently invalidates every comparison |
| Fixed position set, and its value | The rows can be tied to a place | A node logging from 0,0 measures nothing usable |
| Clock set | Rows can be lined up against the other nodes | Fall back to recording the start time by hand |
| Battery voltage, estimated hours | The node outlives the session | Swap the cell |
| **Which other nodes were heard in 30 s, and how strongly** | This node is actually in range | A link that is dead at drop-off is dead all day |

Then `READY`, the filename, and the display blanks.

**The last check only works for nodes placed after the first.** Node 1 hears nothing at its own drop-off because nothing else is on yet. Turn nodes on in placement order and walk back past the earlier ones, pressing the button to confirm they picked up their neighbours.

**A failed check does not stop the node.** It is shown, recorded in the `BOOT` row, and logging starts anyway. A node logging with a bad clock is worth far more than a node refusing to start; the analysis can be told about a known-bad field, but it cannot invent data that was never captured.

**The display is optional at runtime.** If it does not answer at startup the firmware notes it and carries on — a failed screen must never cost a session. The LED remains the running indicator regardless.

Non-negotiable for unattended use:

- **Flush often.** A field day that dies with forty minutes buffered in RAM is a wasted field day.
- **Date and time in the filename**, so a brownout-and-reboot creates a new file instead of overwriting the old one, and so a card full of sessions sorts itself. The boot counter still backs it up when the clock is unset, and still breaks ties inside a single minute.
- **On card failure, keep running.** Keep counting, signal on the LED, retry the mount. Do not halt — a node that stops logging is worse than one that logs a gap.
- **Nothing the self-test can do may be a one-time-only ability.** Every check it makes has to be re-makeable while the node runs (§9.4).

Power management: WiFi off, Bluetooth off, CPU at 80 MHz. **No deep sleep** — the logger must continuously service the serial stream.

Per-node settings live in `firmware/src/config.h`: short name, pins, baud, flush thresholds, timings. It is the only file that differs between the four units — change the name, flash, label the box.

**Build with the `pioarduino` platform, not `espressif32`.** The official PlatformIO ESP32 platform still ships Arduino core 2.x, which has no ESP32-C6 support at all and fails outright with *"This board doesn't support arduino framework!"*. The community fork carries Arduino core 3.x and is what every C6 board needs today. It is pinned in `platformio.ini` for the same reason the library is.

The `BOOT` row records the self-test outcome alongside the configuration, so a file can be judged later without anyone having to remember what the screen said at the time.

### 9.2 Waiting for the clock

After the self-test, a node with no time **stops and waits before it logs anything.** The screen says what it wants:

```
N1 waiting for time
CONNECT YOUR PHONE
hold button to skip
logs anyway in 8:42
```

The LED blinks throughout, because a still screen and a dark LED for several minutes is indistinguishable from a node that has crashed.

**Holding the button for two seconds skips the wait** and logs undated. This is for the bench, where there is no mesh to hand over a time and sitting through the full timeout to test something else wastes ten minutes. It must be held rather than pressed, so that a knock in a bag cannot quietly cost a session its timestamps.

A node whose radio never answered skips the wait automatically — there is no point waiting for a time to arrive down a link that is not there. That is also what makes a bench test with no radio attached start immediately instead of hanging.

The deployment ritual this is built around: **switch a node on, connect your phone to any node on the mesh, walk away.** The phone hands its clock to the radio it connects to, that radio passes the time on to its neighbours, and each logger picks it up from the first packet it hears. The wait normally ends within seconds of the phone connecting, so its usual cost is nothing.

This is why the ritual matters: **a full power-down loses the time everywhere at once.** Neither the logger nor the radio has a battery-backed clock, so four nodes switched off on Tuesday and on again on Thursday all wake up blank together, with nobody left on the mesh to ask. Something outside the mesh has to reintroduce the time, and the phone in your pocket is the cheapest thing that can.

`CLOCK_WAIT_MS` in `config.h` sets the give-up bound — ten minutes by default, far longer than pairing a phone takes and short enough that nobody sits through it by accident. Set it to `0` to restore the older behaviour of logging immediately regardless, or to something enormous to refuse to log at all without a clock.

### 9.3 The menu

The summary page carries five state blocks in a fixed order — **C R P K H** — and the button walks through them in exactly that order, one page each. The menu is the home screen read one block at a time, not a second thing to learn.

| Press | Page | Block | Answers |
|---|---|---|---|
| — | Summary | all five | Can I walk away? |
| 1 | Card | **C** | Is it recording, and will the card last? |
| 2 | Radio | **R** | Is it set up like the other three? |
| 3 | Position | **P** | Can these rows be tied to a place? |
| 4 | Clock | **K** | Can this file be lined up against the others? |
| 5 | Heard | **H** | Who can it hear, and how well? |
| 6 | Power | *(battery)* | How much is left, and how busy has it been? |
| 7 | back to Summary | | |

Every detail page opens with **the same block, drawn by the same code as the summary row** — solid for passing, hollow with a slash for failing — in the top-left corner, ahead of the title:

```
[C] CARD                 1871 MB
--------------------------------
/LOG_N1_20260817_1432.csv
5218 rows written
```

Read left to right, that is the order the question is actually asked: which check this is, what it is called, and how it is doing. The block leads because it is the thing that was wrong on the summary row — you pressed through to find out about that mark, so it is what the page opens with. You press `P` because it looked wrong on the home screen, and the page you land on is still showing you `P`, still wrong, with the reason underneath.

Page 6 is the catch-all for everything with no block of its own: battery, uptime, packets heard and how long ago the last one was. The battery shape stands in the icon's place there, so the run of pages keeps its rhythm.

The first press wakes the screen wherever it was left rather than jumping home, so a second visit to the same node opens on what you were looking at last time.

### 9.4 Recovering without a power cycle

The self-test answers five questions once, while somebody is stood there. Every one of those answers can change afterwards — and the only way to act on a changed answer used to be to open the box and cycle the power, which throws away everything recorded so far. That trade is never worth making, so the running loop re-attempts each check on a timer.

The rule: **nothing the self-test can do may be a one-time-only ability.**

| Block | The fault that can clear | What the loop does about it |
|---|---|---|
| **C** Card | No card at switch-on; a card reseated, swapped, or that failed a write | Re-mount and re-prove writability, backing off 5 s → 30 s. Resumes the session's own file if it is still there; opens a new one, with its own `BOOT` row, if it is not |
| **R** Radio | Still booting; reset, brownout, connector shaken loose | Any word from the radio counts as proof of life. After 8 minutes of total silence it is treated as gone, and asked every 3 s until it answers |
| **P** Position | A coordinate set from a phone part-way through a session | Settings are re-read continuously; while anything is wrong the radio is also asked directly, every 30 s |
| **K** Clock | The first packet carrying a time arrives | Already recovered on its own; the file renames itself from its boot counter to its date |
| **H** Heard | A neighbour finally transmits | Already recovered on its own |

**The case that motivated this.** A node switched on with an empty slot could never start recording, however many cards were pushed in afterwards. The old retry path could only reattach to a filename that already existed, and with no card at boot there was never a file to reattach to — so the card was mounted, proven, and then ignored for the rest of the day.

**A radio that dies is worse than a radio that never starts.** The old check moved one way only, from "no answer" to "answered". A radio that reset mid-session went on reading `RADIO OK` on the screen while the node quietly recorded nothing for hours. Silence is now the evidence, and the window is deliberately longer than the gap between node reports — on a dead-quiet mesh those reports are the only thing proving the link is alive, so a shorter window would condemn a working radio every time.

**Recovery is written down, not just performed.** Two audiences need different things and neither can reconstruct the other's:

- Rows formed while the card was down are **counted**, not buffered, and the count appears on every status row from then on as `drops=`. That number is the true size of the hole; a gap in the timestamps only says that *something* stopped.
- The moment a fault clears, a status row carries `recov=card`, or `recov=card+radio` when several clear at once.
- A file opened part-way through a session carries `resume=<seconds>` in its `BOOT` row, marking it as a continuation rather than a power cycle — which would otherwise look identical to a node that rebooted itself in the field.

`validate-csv` surfaces all three (`RESUMED`, `ROWS_DROPPED`, `RECOVERED`) as warnings rather than errors. A node that healed itself produced usable data; it just produced less of it than the session length suggests, and that has to reach whoever reads the card.

**Recovery probes are not written to the card.** While something is wrong the radio is asked for a node report every 30 s, far more often than the ordinary five minutes. With forty-odd nodes known to a radio, logging every one of those replies would bury the packet rows the session exists to collect — so probe replies update the node's own state and are otherwise discarded. The five-minute schedule that *does* reach the card is untouched.

**One thing this fixed by accident.** The screen's single-word verdict was built from the boot snapshot while the state blocks underneath were read live. A node that lost its card mid-session therefore showed a red `C` block and the word `READY` at the same time. The verdict is now built from the same live state as the blocks, so the two can no longer disagree.

**What is still lost.** Everything heard while the card was unusable is gone — formed, counted, and discarded. Buffering those rows in RAM would close the gap for short outages and is noted in §15.

## 10. Generating traffic to measure

Range Test works as a traffic generator even though it cannot save:

```bash
meshtastic --port <PORT> \
  --set range_test.enabled true --set range_test.sender 60
```

`sender` is seconds between packets. Both sender and receiver need the module enabled.

**Airtime discipline.** Four nodes at one packet per minute on LONG_FAST is modest, but a hop limit of 3 means flooding multiplies packets on air. **Start at 60 s.** Going below 30 s without computing airtime will saturate the channel and you will measure congestion rather than path loss.

**Target ≥100 received packets per directed link** for a stable median — per *link*, not per node. That distinction sets the length of the whole field day, and getting it wrong is how a session comes home a third short.

With four nodes each sending once a minute, a node hears about three packets a minute, but only **one per minute from any one sender**. Reaching 100 on every link therefore takes roughly **100 minutes of received packets, not 35** — and longer in practice, because only direct receptions (`hops_used == 0`) count toward a path measurement and some fraction of arrivals will have been relayed.

Plan on **two hours at 60 s intervals**. Shortening the interval shortens the session proportionally but loads the channel by the same factor, and below 30 s you are measuring congestion rather than path loss. Check progress on the card before packing up: `validate-csv --min-packets 100` reports the count on every link it saw.

## 11. Analysis

### 11.1 Direct versus relayed — the filter that matters most

```
hops_used = hop_start - hop_limit
```

**Only rows with `hops_used == 0` measure a direct RF path** between transmitter and receiver. Everything else measured the last relay's link. Build the link matrix from direct rows only; keep relayed rows for routing behaviour.

### 11.2 Deduplication

Flood routing means the same packet ID arrives via multiple relays. Dedupe on `(tx_node, pkt_id, hops_used)` before counting anything.

### 11.3 Per-link metrics

For each ordered pair, direct rows only: packet count; RSSI median, 10th and 90th percentile; the same for SNR; distance from actual coordinates; elevation difference; and **asymmetry** between the two directions — real links are often several dB asymmetric.

Use **medians, not means.** RSSI distributions are skewed and a single multipath null wrecks a mean. Below ten samples the tenth and ninetieth percentiles are reported as the plain minimum and maximum, because interpolating a percentile from a handful of readings dresses up a range as a statistic.

Treat **+7 dB SNR as the practical reliable-link threshold**, not the theoretical −20 dB floor.

**On delivery ratio.** Nothing in these files records what was *transmitted* — only what arrived somewhere. So a true delivery rate is not recoverable, and `analyze-logs` reports instead the share of a sender's packets that reached anyone which also reached a given receiver directly. That is a useful comparison between receivers and a misleading one if read as an absolute.

`analyze-logs` does all of the above, refuses files the checker rejected, and reports nodes whose configuration differs from the rest — readings across differently-configured nodes are not comparable however clean the data looks.

### 11.4 Comparing antennas

Do not mix antenna models within a run. When comparing, **interleave A/B/A/B** rather than running all of A then all of B — weather, foliage moisture and channel conditions drift over hours, and a blocked design attributes that drift to the antenna. ≥100 packets per antenna per link, compared on medians.

## 12. Validation

Build **one** complete node and validate it end to end before assembling the other three. A wiring error found on unit one costs an hour; found on unit four it costs four.

**Confirmed on the first unit, 17 August 2026, firmware 0.4.1** — logger board only, radio not yet powered:

- Firmware builds, flashes and runs on the XIAO ESP32-C6.
- The card mounts and passes the write-and-read-back test. 1871 MB free reported on a 2 GB card.
- The OLED is found on the I²C bus and shows the self-test.
- The button wakes the running summary and the screen blanks again.
- The boot counter survives power cycles, so each boot opens its own file.
- With the radio absent the self-test reports it and the node **carries on into the loop rather than halting**, which is the degradation behaviour the whole design depends on.
- With the radio absent the clock gate (§9.2) is skipped rather than waiting out its timeout, so a bench test with no radio starts immediately.

**Confirmed on the first unit, 17 August 2026, firmware 0.5.0** — radio wired and powered, one complete node:

- The radio answers over `J7` at 38400 in `PROTO` mode. The screen shows the node number, `US`, `LONG_FAST` and hop limit 3, read back from the radio rather than assumed.
- The clock arrives from the radio and is correct to the minute, so the file is dated.
- Real packets from the surrounding mesh are received, counted per neighbour with RSSI, and written.
- Both power directions work: the radio's `VDD` runs the logger, and the logger's `3V3` runs the radio. **Only the first is the field configuration** — see the battery note below.

**Waiting for something you never asked for is not a timeout, it is a deadlock.** The first version of the boot self-test waited `RADIO_WAIT_MS` for `my_node_num` to become non-zero, having never sent a `want_config`. That value is only ever set by the reply to that request, and the library issues neither the request nor a retry on its own, so the check could not have passed on any node, ever — while packets still streamed in and the clock and neighbour checks went green, which made it read convincingly like a wiring fault. Two rules came out of it, and both are now in the code:

- **Ask before waiting**, and keep asking. Both boards share one supply and therefore boot together, so the first request usually lands on a radio that is still starting and is dropped in silence.
- **No check may latch at boot.** Card, radio, position, clock and neighbours are all re-read from live state on every screen refresh. A fault that has cleared but still shows red teaches people to stop believing the screen, which costs more than the original fault.

That second rule turned out to be half a rule. Re-*reading* live state keeps the screen honest, but it does not make anything come back — the check that failed has to be *re-attempted*, and until §9.4 none of them were. A node switched on without a card showed the fault correctly on the screen and then never recorded a row, no matter what anyone did short of a power cycle.

**The radio's battery percentage is only meaningful when the radio is the power source.** Back-fed from the logger's 3.3 V rail it reports that rail as a nearly-flat cell — 9% on the bench. The battery belongs on the radio's `P2` with the switch in its positive lead (§5.3), which is the same direction the field build uses anyway.

**First real capture, 17 August 2026 — 56 minutes, 421 rows, read back off the card and put through the checker and the analysis.** The format survived contact with the firmware, which is what writing the checker first was for. Three things came out of it:

- **A node logs its own transmissions.** The radio hands back everything it sends over the same serial link, with no RSSI and no SNR, and 37 of 82 packet rows were ours. Left in, they would have been averaged into the link statistics as perfect receptions at 0 dBm — more of them than there were real ones. The logger now drops any packet it originated, keeping only genuine receptions, and still takes the clock from them.
- **`channel` is not always a channel.** The protocol reuses that field to carry a channel *hash* whenever the payload is encrypted, which it says plainly in `mesh.proto`. A logger on a shared channel sees this constantly — 10 and 170 inside the first hour — and the checker was rejecting honest rows for it.
- **One MQTT packet condemned a clean fifty-six-minute file.** Traffic reaching the mesh through an internet gateway measures nothing about a radio path and the analysis drops it, but on any shared channel some will always arrive. It is a warning now. A checker that fails every real file is a checker people run with their eyes shut.

With those corrected the capture reduces to one warning, and the analysis produces its first real link: a node in the same room at **−28 dBm, +6.2 dB SNR, p10–p90 spread of 2 dB** over five packets.

**A card can pass on the logger and still be dead.** The first card mounted on the ESP32 and accepted a written row, while macOS could not mount it at all and could not read back a filesystem it had just written. The microcontroller's FAT implementation is far more forgiving than a desktop's. Prove a new card on a computer — write a large file, eject, read it back, compare — before trusting it with a session. The replacement was verified that way over 100 MB.

**The fixed position was the phone, not the radio.** With the iOS app's *Accurate Locations Only* setting on, every fix taken indoors — 10 to 65 m of accuracy — was rejected before it reached the radio, and the app then displayed *Fixed Position: on* regardless. The node looked configured and had no coordinate behind it, which is exactly the failure `st_pos` exists to catch. Turning the setting off produced a real coordinate on the next boot and all six checks green for the first time.

Still unproven on one node: steps 9 onward, including every recovery path in §9.4. Nothing involving four nodes has been attempted.

**The radio has to be configured before any of it means anything** — Meshtastic flashed, the Serial module enabled in `PROTO` mode at the right pins and baud, region set, fixed position written. This is what `tools/configure_node.py` is for, and it is **not written yet**; unit one was configured by hand with the §8 command. Doing it by hand once is fine for proving the link; doing it by hand four times is how three nodes end up differing from the fourth in a way nobody wrote down.

**Read the configuration back after writing it.** The radios ship with the Serial module disabled and its pins unassigned, and a node in that state still joins the mesh, still relays, still looks healthy from a phone — it simply never speaks to its logger. `meshtastic --info` is the only thing that distinguishes it from a working node.

1. Continuity and short checks with everything unpowered — 3.3 V to ground must read open.
2. First power-up on the current-limited bench supply.
3. Prove the PROTO stream exists using a 3.3 V USB-serial adapter and `meshtastic --listen`, with no logger board involved. The pin numbers come from the board revision (§8) rather than from trial. If PROTO refuses but NMEA produces readable sentences on the same wiring, the wiring is fine and the problem is protocol-side.
4. Verify whether the CLI pushes device time.
5. Unmodified library, two boards on a desk — proves handshake, heartbeat and framing before touching library internals.
6. Forked library, RSSI and SNR printed to the console. From across a room expect −30 to −60 dBm and +5 to +12 dB.
7. Add card writing. Power-cycle mid-write repeatedly; confirm no corruption and a fresh file per boot.
8. Add the display and the boot self-test. Prove each check **fails** as designed, not just that it passes: pull the card, unplug the radio's serial line, clear the fixed position, and confirm the screen says so and the node still starts logging. A self-test that only ever shows green has not been tested.
9. Prove each check **recovers**, which is the other half of step 8 and the one that decides whether a box can be left alone (§9.4). Four separate runs, no power cycle in any of them:
    - Switch on with an empty slot, wait a minute, push a card in. A new file must appear within thirty seconds, carrying its own `BOOT` row with `resume=` on it and `st_card=1`. Run `validate-csv` on it: `RESUMED` and `ROWS_DROPPED` as warnings, no errors.
    - Pull the card mid-session and put the **same** card back. The node must resume the same file — one `BOOT` row in it, not two — and the next status row must carry `recov=card` and a non-zero `drops=`.
    - Pull the card mid-session and put a **different** card in. A new file, again with its own `BOOT` row.
    - Unplug the radio's serial line for ten minutes and reconnect it. The screen's `R` block and its verdict must both go bad, and both must come back; a status row must carry `recov=radio`. Ten minutes because the silence window is eight — anything shorter proves nothing.
10. Fit the switch and the button. Confirm the node survives fifty power cycles, that a press wakes the display and it blanks again, and that the button does nothing harmful if held down at power-up.
11. Measure actual current draw and replace the estimates in §5.3. Measure it twice — display lit and display blanked — so the cost of the screen is a number rather than an assumption.
12. Four nodes on a desk for two hours, antennas attached, real traffic intervals. Confirm every node saw every other and counts are roughly symmetric — `validate-csv --min-packets 100` answers both, and must report no errors.
13. One node on battery until it dies. **Multiply the planned session by 1.5 and confirm the battery beats it.**
14. Sealed enclosure, 300 m walk and back. Confirm sensible signal roll-off with distance, and that the switch and button are usable through the enclosure with cold hands.

A 3.3 V USB-serial adapter is required. **A 5 V logic adapter will damage the nRF52840.**

## 13. Repository layout

```
firmware/                 PlatformIO project for the logger board
  platformio.ini
  src/
    config.h              per-node settings; the only file that varies
    log_schema.h          the CSV contract, mirroring the Python schema
    clock.*               absolute time, the timezone rule, the file stamp
    logfile.*             card, boot counter, rows, flushing, remounting
    recovery.*            re-attempting every failed check while the node runs
    screen.*              the OLED; optional at runtime
    selftest.*            the boot checks and how they are shown
    main.cpp              callbacks and the loop
tools/                    Python, uv-managed
  src/fieldlab/
    schema.py             the file format; single source of truth
    validate.py           the checker; written before the firmware
    analyze.py            dedupe, direct-only filter, per-link metrics
    synth.py              a whole synthetic session, for building the analysis
    cli.py                validate-csv, analyze-logs, synth-log
    configure_node.py     applies radio config, saves --info dump
    dem_lookup.py         lat/lon -> ground elevation
  tests/
config/                   per-node --info dumps, redacted (§8) — raw ones are gitignored
data/                     field logs (data/raw is gitignored)
docs/
```

## 14. Licensing

This repository is **GPL-3.0**, because it builds on `Meshtastic-arduino`, which is GPL-3.0. That was already true of the Python tooling for the same reason.

The forked library remains GPL-3.0 and is referenced, not copied — see §4.2. Its licence is recorded in the dependency table in the README, as every dependency here is.

## 15. Open items

Determined only with hardware in hand:

1. ~~Whether this RAK19003 revision maps `J7` to 16/15 or 20/19~~ — **resolved by the board revision, see §8.** The boards in hand are Rev E, so 19/20
2. Whether the CLI pushes device time on connect
3. Whether these microSD modules need added pull-ups on this bus
4. Real per-node current draw — §5.3 is estimated, lit and blanked
5. Which antenna model shipped with the radio kits, for the baseline record
6. The OLED's I²C address — `0x3C` on most of these modules, `0x3D` on some. Scan the bus on the first unit and record it; a wrong address looks exactly like a dead screen
7. Whether the OLED module's regulator is happy at 3.3 V — many are sold as "3.3–5 V" but a few assume 5 V and are dim or dead on a 3.3 V rail. There is no 5 V rail here
8. Whether altitude survives the trip. `Meshtastic-arduino` narrows the protocol's 32-bit altitude to a **signed byte** in its node struct, so anything outside ±127 m is already lost before the logger sees it. Fine for the sites in mind, but it is a third field the library quietly damages, and it would need the same treatment as the other two if a taller site is ever used

Each is written so it is a one-line change, not a rewrite.

Deliberately not built yet:

9. **Buffering rows through a card outage.** Recovery (§9.4) restores logging without a power cycle, but everything heard while the card was unusable is still counted and discarded. A few hundred packets held in RAM — well within the ~300 KB spare — would close the gap for a card reseated by hand, which is the common case. It is not built because the retry loop had to exist first: without it the buffer would have had nowhere to drain to.

## 16. References

- [Serial module configuration](https://meshtastic.org/docs/configuration/module/serial/)
- [Client API and PROTO framing](https://meshtastic.org/docs/development/device/client-api/)
- [Range Test module](https://meshtastic.org/docs/configuration/module/range-test/)
- [RAK19003 datasheet](https://docs.rakwireless.com/product-categories/wisblock/rak19003/datasheet/)
- [XIAO ESP32-C6 pin multiplexing](https://wiki.seeedstudio.com/xiao_pin_multiplexing_esp32c6/)
- [Meshtastic-arduino](https://github.com/meshtastic/Meshtastic-arduino)
- [PROTO-over-serial troubleshooting](https://github.com/orgs/meshtastic/discussions/253)
- [USGS 3D Elevation Program](https://www.usgs.gov/3d-elevation-program)
