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
- **Power-cycling is a normal operation, not a fault.** Each boot opens a new file with an incremented count in its name, so nothing is ever overwritten and no session is lost by turning a node off and on. This is why the boot counter exists.

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

One file per node per boot: `/LOG_<SHORTNAME>_<BOOTCOUNT>.csv`

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
| `STATUS` | Every 60 s | `rows`, `sd_ok`, `heap` |
| `NODE` | Every 300 s, one row per known node | `name`, `lat`, `lon`, `batt`, `last_heard` |

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

**Position.** Nodes are static once set down. Record the coordinate on site, while standing there, and write it to the device over USB before walking away:

```bash
meshtastic --port <PORT> --setlat <LAT> --setlon <LON> --setalt <ALT> \
  --set position.fixed_position true
```

Record the intended position as well as the one actually used — the difference between them matters when interpreting the results.

**Altitude.** Do not take altitude from GPS. Consumer GPS vertical accuracy is ±10–20 m, roughly twice as bad as horizontal. Instead:

```
node altitude = ground elevation at (lat, lon) from a 1 m DEM
              + height above ground, measured with a tape
```

Both terms are more accurate than any GPS module you could attach. This makes **measured height above ground a required field** on the field log sheet.

**Time.** The Meshtastic CLI pushes its clock to the device on connect. Connecting all four nodes to one laptop in one session immediately before deployment gives every node correct absolute time, which is what makes `dev_rx_time` meaningful. Meshtastic also propagates time across the mesh from any node that has it.

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

## 9. Firmware behaviour

```
setup()
  init display; if it does not answer, carry on regardless — see below
  read and increment boot counter in NVS
  run the boot self-test (§9.1), showing each result as it lands
  open /LOG_<SHORTNAME>_<BOOTCOUNT>.csv, write header and BOOT row
  init serial to the radio at 38400, register the packet-metadata callback
  request node report

loop()
  service the protocol (handles want_config and the 60 s heartbeat)
  on each packet: append one row, compute hops_used, increment counters
  flush every 5 s or 10 rows, whichever comes first
  every 60 s: STATUS row
  every 300 s: refresh node report
  on button press: wake display 10 s with the running summary, then blank
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
- **Boot counter in the filename**, so a brownout-and-reboot creates a new file instead of overwriting the old one.
- **On card failure, keep running.** Keep counting, signal on the LED, retry the mount. Do not halt — a node that stops logging is worse than one that logs a gap.

Power management: WiFi off, Bluetooth off, CPU at 80 MHz. **No deep sleep** — the logger must continuously service the serial stream.

Per-node settings live in `firmware/src/config.h`: short name, pins, baud, flush thresholds, timings. It is the only file that differs between the four units — change the name, flash, label the box.

**Build with the `pioarduino` platform, not `espressif32`.** The official PlatformIO ESP32 platform still ships Arduino core 2.x, which has no ESP32-C6 support at all and fails outright with *"This board doesn't support arduino framework!"*. The community fork carries Arduino core 3.x and is what every C6 board needs today. It is pinned in `platformio.ini` for the same reason the library is.

The `BOOT` row records the self-test outcome alongside the configuration, so a file can be judged later without anyone having to remember what the screen said at the time.

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

1. Continuity and short checks with everything unpowered — 3.3 V to ground must read open.
2. First power-up on the current-limited bench supply.
3. Prove the PROTO stream exists using a 3.3 V USB-serial adapter and `meshtastic --listen`, with no logger board involved. The pin numbers come from the board revision (§8) rather than from trial. If PROTO refuses but NMEA produces readable sentences on the same wiring, the wiring is fine and the problem is protocol-side.
4. Verify whether the CLI pushes device time.
5. Unmodified library, two boards on a desk — proves handshake, heartbeat and framing before touching library internals.
6. Forked library, RSSI and SNR printed to the console. From across a room expect −30 to −60 dBm and +5 to +12 dB.
7. Add card writing. Power-cycle mid-write repeatedly; confirm no corruption and a fresh file per boot.
8. Add the display and the boot self-test. Prove each check **fails** as designed, not just that it passes: pull the card, unplug the radio's serial line, clear the fixed position, and confirm the screen says so and the node still starts logging. A self-test that only ever shows green has not been tested.
9. Fit the switch and the button. Confirm the node survives fifty power cycles, that a press wakes the display and it blanks again, and that the button does nothing harmful if held down at power-up.
10. Measure actual current draw and replace the estimates in §5.3. Measure it twice — display lit and display blanked — so the cost of the screen is a number rather than an assumption.
11. Four nodes on a desk for two hours, antennas attached, real traffic intervals. Confirm every node saw every other and counts are roughly symmetric — `validate-csv --min-packets 100` answers both, and must report no errors.
12. One node on battery until it dies. **Multiply the planned session by 1.5 and confirm the battery beats it.**
13. Sealed enclosure, 300 m walk and back. Confirm sensible signal roll-off with distance, and that the switch and button are usable through the enclosure with cold hands.

A 3.3 V USB-serial adapter is required. **A 5 V logic adapter will damage the nRF52840.**

## 13. Repository layout

```
firmware/                 PlatformIO project for the logger board
  platformio.ini
  src/
    config.h              per-node settings; the only file that varies
    log_schema.h          the CSV contract, mirroring the Python schema
    logfile.*             card, boot counter, rows, flushing, recovery
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
config/                   per-node --info dumps
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

## 16. References

- [Serial module configuration](https://meshtastic.org/docs/configuration/module/serial/)
- [Client API and PROTO framing](https://meshtastic.org/docs/development/device/client-api/)
- [Range Test module](https://meshtastic.org/docs/configuration/module/range-test/)
- [RAK19003 datasheet](https://docs.rakwireless.com/product-categories/wisblock/rak19003/datasheet/)
- [XIAO ESP32-C6 pin multiplexing](https://wiki.seeedstudio.com/xiao_pin_multiplexing_esp32c6/)
- [Meshtastic-arduino](https://github.com/meshtastic/Meshtastic-arduino)
- [PROTO-over-serial troubleshooting](https://github.com/orgs/meshtastic/discussions/253)
- [USGS 3D Elevation Program](https://www.usgs.gov/3d-elevation-program)
