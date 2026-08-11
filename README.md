# cairn-fieldlab

Open measurement and packet-logging tooling for LoRa mesh field tests.

**Status:** early. Structure and scope are being set up; implementation is in progress.

## Why this exists

A Meshtastic node paired with a phone shows you signal strength *live*. That is useful for a smoke test and useless for a measurement. It does not write every packet to a file, so there is no way to turn "I saw a few bars on my phone out there" into a dataset you can analyse, plot, or hand to somebody else.

`cairn-fieldlab` is the logging layer that closes that gap. It tethers to LoRa mesh nodes in the field, records what actually arrives, and writes it to disk in a stable format so that outdoor tests produce evidence instead of impressions.

## Scope

This repository is **measurement and analysis only**. Concretely, that means:

**In scope**
- Connecting to Meshtastic nodes over USB/serial (and BLE where practical)
- Recording every received packet: timestamp, source, destination, RSSI, SNR, hop count, port/type
- Stable CSV schemas that stay readable years from now
- Per-node test metadata: GPS position, antenna, height above ground, firmware and radio settings
- Derived measures such as packet delivery ratio and per-link statistics
- Analysis notebooks and plots over collected runs
- Hardware setup, wiring, and power notes for the logging rig
- Clock synchronisation and calibration procedures

**Out of scope**
- Anything unrelated to capturing or analysing measurements
- Vendored third-party source (see below)
- Credentials, API keys, or private configuration
- Raw logs containing precise coordinates of private property

## Intended hardware

- **Nodes:** RAK WisBlock / RAK4631 running Meshtastic, US915 region
- **Logger:** Seeed XIAO ESP32-C6 wired to the node's UART header, writing to a microSD card. It speaks the Meshtastic client protocol over serial — the same one a phone uses — so the node needs no modified firmware.
- **Power:** a single LiPo on the node's battery connector feeds both boards; there is no second supply and no 5 V rail.
- Anything else that speaks the Meshtastic serial protocol should work.

See [docs/packet-logger-design.md](docs/packet-logger-design.md) for the wiring, file format, and validation procedure.

## Dependencies and licensing

This project depends on the official [Meshtastic Python library](https://github.com/meshtastic/Meshtastic-python) and, for the logger firmware, on [Meshtastic-arduino](https://github.com/meshtastic/Meshtastic-arduino). Both are licensed **GPL-3.0**, so **this repository is also licensed GPL-3.0**. That is a deliberate choice rather than a default: it keeps the licensing honest and unambiguous.

Expected dependency set:

| Dependency | Purpose | License |
|---|---|---|
| `meshtastic` | Node communication (Python tooling) | GPL-3.0 |
| `Meshtastic-arduino` | Node communication (logger firmware) | GPL-3.0 |
| `pyserial` | Serial transport | BSD-3-Clause |
| `pandas` | Log analysis | BSD-3-Clause |
| `matplotlib` | Plots | PSF-based |

If you add a dependency, record its license in this table in the same commit.

### Our fork of Meshtastic-arduino

The firmware builds against [`offgridevices/Meshtastic-arduino`](https://github.com/offgridevices/Meshtastic-arduino), a fork of the upstream library, pinned to an exact commit.

The fork exists for one reason: upstream decodes each packet's RSSI and SNR and then discards them — none of its three callbacks pass those fields to the caller, and no setting changes that. Since RSSI and SNR are the entire measurement, the fork adds one additional callback carrying the full packet metadata. Existing callbacks are untouched. The change will be offered upstream once it has been validated in the field.

The fork remains GPL-3.0, and its commit history is the record of what was modified.

## Third-party source is never vendored here

Dependencies are installed from package managers, or referenced by URL and pinned commit. Source copies of external projects are **not** committed to this repository, and are not kept inside this working tree at all — local clones used for reading or reference live outside it, and `.gitignore` additionally blocks the usual paths (`reference/`, `vendor/`, `third_party/`, `external/`) so that an accidental copy cannot be staged.

This matters for a practical reason: license obligations travel with code. Keeping other projects' source physically outside this tree means the provenance of everything committed here is unambiguous, both for this repository and for any other project developed alongside it.

**When a dependency must be modified**, it is forked into its own repository and referenced here by URL and exact commit — never copied in and edited in place. What this repository commits is a reference, so provenance stays trivially answerable, and the fork's own commit history serves as the record of modification that GPL-3.0 requires. Record any such fork in the dependency table above, with its license and the reason it exists.

**If you are contributing:** do not paste code in from another project. Import it as a dependency, fork it and pin it, or write it yourself.

## Data handling

Collected logs are the point of this repository, but not all of them belong in it. Before committing a run:

- Confirm the test location is not private property whose coordinates you would rather not publish
- Strip or round coordinates where precision is not needed for the analysis
- Keep raw captures and processed results clearly separated

## License

GPL-3.0. See [LICENSE](LICENSE).
