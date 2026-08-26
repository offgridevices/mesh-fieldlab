# Mechanical model — packet logger carrier

STEP models of the carrier board, for designing an enclosure around it.

```
packet-logger-carrier.step         board + every part that stands above it
packet-logger-carrier-board.step   the bare plate on its own
```

Both are plain STEP (AP214) and open in FreeCAD, Fusion, Onshape, SolidWorks,
OpenSCAD (via import), or anything else that reads STEP.

Regenerate with:

```
cd src && python3 emit_step.py --check
```

---

## The numbers you need

| | |
|---|---|
| Board | **86.0 × 58.0 × 1.6 mm** |
| Overall envelope | **86.0 × 58.0 × 17.6 mm** (board + tallest part) |
| Clear height needed above the board | **16.0 mm** |
| Mounting holes | 4 × **⌀3.2 mm** (M3 clearance), non-plated |
| Hole centres | 3.5 mm in from each corner → **79.0 × 51.0 mm** rectangle |

Origin is the **bottom-left corner of the board**, X to the right, Y up,
Z up from the underside. So the board occupies X 0–86, Y 0–58, Z 0–1.6, and
everything else sits above Z 1.6. That is the same coordinate system the
design source uses, so any number in `src/design.py` drops straight in.

**Under the board:** nothing is mounted on the underside, but every part is
through-hole, so allow **1.5–2 mm** for clipped lead ends before the board
meets a standoff or a flat floor.

---

## Which faces need an opening

| Face | What | Where | Height above board |
|---|---|---|---|
| **North** (Y = 58) | RAK19003 USB-C, battery, solar, reset | X 3–33, edge sits 3 mm inboard | 8.5 – 16.0 mm |
| **East** (X = 86) | XIAO ESP32-C6 USB-C | Y 20–38, edge sits 1 mm inboard | 8.5 – 12.0 mm |
| **South** (Y = 0) | microSD card slot | X 38–62, may overhang the edge | 8.5 – 12.0 mm |
| **Top / lid** | SW1 user button plunger | (78.0, 44.5), ⌀3.5 mm | up to 5.0 mm |
| **Top or side** | SW2 power slide actuator | (22.54, 6.0), 8 × 4 mm body | 4.0 – 7.0 mm |
| **Lid, internal** | OLED on a cable to J5 | J5 pins at Y 53, X 54–62 | — |

The **display is not on this board.** J5 is a 4-pin header for a cable up to a
screen mounted in the lid, so the lid needs the display cut-out and standoffs,
and the cable needs somewhere to run.

The **battery** connects at J13 (JST-PH) around (14, 6), or at J12 as bare
wires — both live inside the box.

---

## Where the numbers come from

Everything in the XY plane — outline, holes, slots, and where each part sits —
is read straight out of `src/design.py`, the same source the Gerbers were
generated from. The model cannot drift from the board that was ordered.

**Heights are different.** The footprints carry no 3D models, so no height
here comes from KiCad. They are nominal part envelopes. The ones worth putting
calipers on before you cut an enclosure to them are marked **MEASURE**:

| Part | Height above board | Source |
|---|---|---|
| RAK19003 module | **16.0** | **MEASURE** — 8.5 socket + 7.5 for base board, core module and USB-C shell |
| XIAO ESP32-C6 | **12.0** | **MEASURE** — 8.5 socket + 3.5 for PCB, shield and USB-C shell |
| microSD breakout | **12.0** | **MEASURE** — 8.5 socket + 3.5 for PCB and card socket |
| C1 / C2 (optional) | 11.0 | electrolytics on 2.54 lead pitch |
| JP1 with shunt | 9.0 | header plus a fitted shunt |
| all 2.54 headers | 8.5 | `README.md`: socketed modules stand ~8.5 mm off |
| SW2 slide actuator | 7.0 | **MEASURE** — varies by SS-12D00 suffix |
| J13 JST-PH | 6.0 | S2B-PH-K-S |
| SW1 button plunger | 5.0 | **MEASURE** — 4.3 / 5 / 7 / 9.5 mm variants exist |
| C3 / C4 (optional) | 5.0 | ceramic |

The four optional decoupling capacitors are in the model even though they are
not fitted by default — if you do fit them, the box has to clear them.

If a measurement comes back different, change the one number in
`src/emit_step.py` and regenerate. Nothing else needs touching.

---

## How it is checked

`python3 emit_step.py --check` runs two gates, both of which must pass:

1. **Board geometry against KiCad.** The plate is rebuilt at the 1.51 mm core
   thickness KiCad exports and compared to KiCad's own STEP export of the
   ordered board. The two are derived independently — one from `design.py`,
   one from the `.kicad_pcb` — so agreement means every hole and both routed
   slots are in the right place. Currently **0.0000 % volume difference**.

2. **Part placement against the pads.** Each part's centre is compared to the
   centroid of the pads carrying its reference designator. A header with the
   wrong pin count, pitch or origin would show up immediately. Currently
   **18 references, worst offset 0.0000 mm**.
