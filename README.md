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
- **Logger:** Raspberry Pi Zero 2 W tethered to a node over USB, writing to local storage
- Anything else that speaks the Meshtastic serial protocol should work

## Dependencies and licensing

This project depends on the official [Meshtastic Python library](https://github.com/meshtastic/Meshtastic-python), which is licensed **GPL-3.0**. Because a Python import of a GPL-3.0 library creates a derivative work, **this repository is also licensed GPL-3.0**. That is a deliberate choice rather than a default: it keeps the licensing honest and unambiguous.

Expected dependency set:

| Dependency | Purpose | License |
|---|---|---|
| `meshtastic` | Node communication | GPL-3.0 |
| `pyserial` | Serial transport | BSD-3-Clause |
| `pandas` | Log analysis | BSD-3-Clause |
| `matplotlib` | Plots | PSF-based |

If you add a dependency, record its license in this table in the same commit.

## Third-party source is never vendored here

Dependencies are installed from package managers. Source copies of external projects are **not** committed to this repository, and are not kept inside this working tree at all — local clones used for reading or reference live outside it, and `.gitignore` additionally blocks the usual paths (`reference/`, `vendor/`, `third_party/`, `external/`) so that an accidental copy cannot be staged.

This matters for a practical reason: license obligations travel with code. Keeping other projects' source physically outside this tree means the provenance of everything committed here is unambiguous, both for this repository and for any other project developed alongside it.

**If you are contributing:** do not paste code in from another project. Import it as a dependency, or write it yourself.

## Data handling

Collected logs are the point of this repository, but not all of them belong in it. Before committing a run:

- Confirm the test location is not private property whose coordinates you would rather not publish
- Strip or round coordinates where precision is not needed for the analysis
- Keep raw captures and processed results clearly separated

## License

GPL-3.0. See [LICENSE](LICENSE).
