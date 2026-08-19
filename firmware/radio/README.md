# Radio firmware cache

The radio firmware, kept locally so flashing a node does not start with a trip
to a download page and a guess between similarly named files.

**Nothing in here is committed.** The images are large binaries belonging to the
Meshtastic project, they are reproducible from a version tag, and a binary in
git is a binary nobody can review. What is worth keeping under version control
is the record of *which* image belongs here, which is this file.

## The pinned image

```
firmware-rak4631-2.7.26.54e0d8d.uf2
```

Meshtastic `v2.7.26` (`54e0d8d`), the **vanilla `rak4631` build**. All four
radios run this one image — see §8.1 of `docs/packet-logger-design.md` for why
the version is pinned rather than merely current.

To fetch it again:

```sh
gh release download v2.7.26.54e0d8d --repo meshtastic/firmware \
  --pattern 'firmware-nrf52840-*.zip' --dir firmware/radio
cd firmware/radio
unzip -j firmware-nrf52840-2.7.26.54e0d8d.zip 'firmware-rak4631-2.7.26.54e0d8d.uf2'
rm firmware-nrf52840-2.7.26.54e0d8d.zip
```

The release ships one zip per processor architecture rather than loose `.uf2`
files. The RAK4631 is an nRF52840, so its image is inside the **nrf52840** zip.

## Two ways to pick the wrong file

Both produce a flash that appears to do nothing rather than an error.

**Wrong processor.** The `rak11310` is an RP2040 — a different processor on a
similarly named WisBlock core, listed beside the RAK4631 on the same download
page. Its image is in the `rp2040` zip. The bootloader silently declines a
mismatched image and leaves the file sitting on the mass-storage volume, which
looks exactly like a drag-and-drop that did not take.

**Wrong variant.** The nrf52840 zip contains four images whose names begin
`rak4631`: the plain build, `_eink`, `_eth_gw`, and `_nomadstar_meteor_pro`.
Only the plain one is pinned. The nomadstar variant is the vendor image unit one
*shipped* with and specifically is not what it should run — a variant image
flashes and boots perfectly, so nothing will tell you afterwards. Keep only the
pinned image in this directory so there is nothing to pick wrongly from.

## Check before flashing

The filename is a label. The family ID inside every 512-byte block is what the
bootloader actually matches on, so read that instead:

```sh
python3 firmware/radio/check_uf2.py firmware/radio/firmware-rak4631-2.7.26.54e0d8d.uf2
```

The right answer for a RAK4631:

```
family    : 0xADA52840  nRF52840 Adafruit (RAK4631, Adafruit bootloader)
flash addr: 0x00026000 .. 0x000DF500
```

An RP2040 image reports `0xE48BFF56` and loads at `0x10000000`. If you see that,
you have the RAK11310 build.

## Flashing

1. **Double-tap the RAK's reset button.** A volume named `RAK4631` appears.
2. Confirm it is the right board — `cat /Volumes/RAK4631/INFO_UF2.TXT` should say
   `Board-ID: WisBlock-RAK4631-Board`. The bootloader must be the Adafruit UF2
   one; a board marked `RAK4631-R` ships with RUI3 and has to be converted first.
3. Copy the image across:
   ```sh
   cp firmware/radio/firmware-rak4631-2.7.26.54e0d8d.uf2 /Volumes/RAK4631/
   ```
4. **`cp` will report an I/O error. That is success, not failure.** The
   bootloader takes the blocks, resets and unmounts the volume part-way through
   the copy, and the operating system reports the disappearing disk as an error.
   The flash has already happened.
5. Confirm the volume is gone and a serial port is back, then read the version
   off the device rather than trusting the copy:
   ```sh
   uv run --with meshtastic python -c "
   import meshtastic.serial_interface as si
   i = si.SerialInterface(devPath='/dev/cu.usbmodemXXXXX')
   print(i.metadata.firmware_version); i.close()"
   ```
   It should print `2.7.26.54e0d8d`.

Read the version this way rather than with `meshtastic --info`. The full dump
prints the node's PKI **private key**, which is what the `config/` rules in
`.gitignore` exist to keep out of the repository.
