# Packet Logger Carrier Board — v1

A single 2-layer PCB that replaces the hand-wired 7 × 9 cm protoboard node.
Drop in the **RAK19003**, the **XIAO ESP32-C6** and the **microSD breakout**,
add a button and a power switch, and every connection in the build record is
made in copper instead of wire.

**Board: 86 × 58 mm, 2 layers, 1.6 mm FR4.**
65 solder points. 98 track segments, 8 vias, full ground plane underneath.

Opens in **KiCad 10** — the board file is saved in KiCad 10's own native
format and KiCad's DRC reports **0 errors, 0 warnings, 0 unconnected**.

---

## Brand colours — how to order it

**Colour is not in the Gerber files.** Soldermask and silkscreen colour are
options you pick in the fab's order form; the artwork is colour-blind. So
"on-brand" here means two things: choosing the right options, and designing
the artwork to suit them. Both are done.

| OffGrid token | On the board | Order setting |
|---|---|---|
| **Pitch** `#1B1813` | Soldermask | **Matte black** (JLCPCB "Matt Black", PCBWay "Matte Black") |
| **Bone** `#F1ECE0` | Silkscreen | **White** |
| **Ember** `#FF6A00` | The Beacon Ring, in bare metal | **ENIG** surface finish |

### The lockup

The mark and wordmark are placed at the ratios in
`handoff/logo/svg/offgrid-wordmark-horizontal.svg` — mark at `translate(20 12)`,
text anchored at `x=240 y=125`, size 92, letter-spacing −3 — scaled as one unit
so the spacing is the brand's, not an approximation. The wordmark is set in
**real Archivo weight 900 outlines**, pulled from the variable font and emitted
as filled polygons, rather than a stand-in stroke font. `src/verify_wordmark.py`
re-renders the same text through FreeType and compares shapes as a build gate.

Mark height 5.4 mm, lockup 21 mm wide, cap height 2.3 mm.

One deliberate departure: the brand SVG's own text baseline (`y=125`) leaves the
wordmark sitting about **12% of the mark height too high**, which reads as
misaligned at this size. The wordmark is dropped so its ink centre lands on the
mark's area centroid (ring + node) — the optical centre. Worth correcting in the
source asset too.

No board house offers orange soldermask, so Ember is expressed the only way a
PCB can: as **exposed copper**. The Beacon Ring is drawn on the copper layer
with a matching opening in the soldermask, so it comes out as bare gold metal
against the black — the same warm accent, in the only material the process
allows. The wordmark beside it stays white silkscreen, which keeps to the
brand's **one accent per surface** rule: the ring is the accent, everything
else is Bone on Pitch.

ENIG rather than HASL matters here — HASL would coat the mark in solder and it
would come out silver. ENIG also has a longer shelf life and a flatter finish.
It costs a little more than the default; it is the difference between a gold
mark and a grey one.

The board outline is a plain rectangle with square corners, per the brand's
right-angles-only geometry rule.

**Full order settings:** 2 layers · 1.6 mm · **Matte black** mask · **White**
silkscreen · **ENIG** finish · 86 × 58 mm · qty 5.

One practical note: matte black shows fingerprints and dust more than green,
and cosmetic consistency between batches is slightly looser. Nothing about it
affects how the board works — our traces are 0.25 mm against a 0.127 mm
process minimum, so there is a wide margin.

---

## ⚠ Read this before you order

**The RAK19003's two headers are NOT a whole number of protoboard holes apart.**

Measured from RAK's own mechanical drawings (both the Rev B dimensioned drawing
and the Rev E drawing, which agree to 0.03 mm):

| | |
|---|---|
| Pitch inside each 4-pin group | 2.54 mm |
| **Gap, J6 pin 4 (SDA) → J7 pin 1 (BOOT)** | **9.41 mm** |
| Which is | 3.70 × 2.54 — *not* 4 holes (10.16 mm) |
| Total span, pin 1 to pin 8 | 24.65 mm |

That is why the RAK was a squeeze on the protoboard: putting J6 in columns
A–D and J7 in H–K forces the pins about 0.75 mm out of place.

**How this board handles it:** J6's four pads are round holes on an exact
2.54 mm pitch. J7's four pads are **oval slots (1.0 × 2.0 mm)** centred at a
9.79 mm gap. That accepts anything from **9.24 mm to 10.34 mm**, so the board
solders up whether the true gap is the datasheet's 9.41 or a full 10.16.

**Still do this before ordering:** put a caliper across your actual RAK from
the centre of the SDA pin to the centre of the BOOT pin. Anything in
9.2 – 10.3 mm is covered.

---

## How each module sits

Hold the board with the text the right way up. Then:

**RAK19003** — pins along the bottom, body reaching up. Its USB-C, battery,
solar and reset are all on the **far (top) edge**, so they stay reachable.
Left to right the pins read:

```
J6:  VDD   GND   SCL   SDA        [ 9.41 mm gap ]        J7:  BOOT  GND  TX0  RX0
```

Confirmed two independent ways: it is what you read off your own board, and it
is what RAK's Figure 3 shows once you rotate the board 90° to match how you
have it mounted. The Rev E silkscreen says **TX0 / RX0** (the older datasheet
table calls the same pins TX1 / RX1 — same physical pins).

**XIAO ESP32-C6** — **USB-C points east**, out to the right-hand edge, so you
can plug in to reprogram it without taking anything apart. Reading the bottom
row from the USB end back: 5V, GND, 3V3, D10, D9, D8, D7 — the standard XIAO
order.

**microSD** — pins along the **top** of the module, body hanging **down toward
the bottom edge of the board**, so the card slot ends up at the edge and you
can pull the card without opening the box. Left to right the pins read:

```
3V3   CS   MOSI   CLK   MISO   GND
```

with **3V3 on the square pad** — matching the module you have.

---

## What's on the board

| Ref | What | Pins |
|---|---|---|
| J1 / J2 | RAK19003 J6 and J7 | 4 + 4 |
| J3 | XIAO ESP32-C6, 2×7, rows 15.24 mm apart | 14 |
| J4 | microSD breakout, 1×6 | 6 |
| **J5** | **OLED display — GND, 3V3, SCL, SDA. Nothing else on it.** | **4** |
| J15 | External button, if you want one off-board — BTN, GND | 2 |
| SW1 | User button, 6 mm tact, on the board | 4 |
| SW2 | **SS-12D00 / SS12D00G6 power slide switch, mounts on the board** | 3 |
| J12 / J13 | Battery in — bare wires or JST-PH 2.0, wired in parallel | 2 + 2 |
| J14 | Switched battery out → the RAK's own battery socket | 2 |
| J10 | RAK spare: BOOT, SCL, SDA, GND | 4 |
| J11 | ESP spare: 5V, D1, D2, GND | 4 |
| JP1 | 3V3 link — **fit a shunt** (see below) | 2 |
| C1–C4 | Decoupling, all optional, all 2.54 mm lead pitch | 8 |

### The power switch

**SW2 takes your SS12D00G6 directly** — three pins on 2.54 mm, which is
exactly what that switch has, so it drops in and solders. The body outline on
the silkscreen is the 8.0 × 4.0 mm footprint of the switch. The **centre pin
is the input** (battery +); the switched output leaves on the pin marked OUT.
The third pin is unconnected. If you would rather use a panel switch, wire it
to OUT and IN instead.

### The display

**J5 is the display and only the display** — four pins, GND, 3V3, SCL, SDA,
all together, labelled on the board. The button is a separate 2-pin header
(J15) right next to it, wired in parallel with the button on the board, so you
can use either, both, or neither.

### The 3V3 link (JP1)

The RAK's 3.3 V comes in on JP1's "RAK" pin and leaves on "SYS" to feed the
XIAO, the card and the OLED. Fit a jumper shunt for normal use.

Pull the shunt when you want to program the XIAO over USB with the RAK
powered — it stops the RAK's regulator and the XIAO's regulator fighting over
the same rail. With the shunt out, USB still powers the XIAO, the card and
the screen; only the RAK is separated. If you'd rather never think about it,
bridge the two pads with solder.

---

## Ordering

JLCPCB or PCBWay:

* 2 layers, 1.6 mm, **matte black mask, white silkscreen, ENIG finish** (see Brand colours above)
* **86 × 58 mm** — inside the cheap 100 × 100 mm tier
* Upload `packet-logger-carrier-gerbers.zip` as-is
* Minimum order is 5; you need 4, so you get a spare
* Expect roughly $2–5 for the bare boards; ENIG and the black mask add a
  few dollars. Plus shipping, about 1–2 weeks.

The zip contains top and bottom copper, both soldermasks, top silkscreen,
board outline, and separate plated / non-plated drill files. J7's oval slots
are in the plated drill file as routed slots (G85) — both houses handle these
as standard.

---

## Assembly order

1. **C1–C4 first** if you're fitting them (lowest parts first). They're optional.
2. **JP1**, then the shunt.
3. **SW1** the tact switch, **SW2** the slide switch.
4. **J12/J13** battery in, **J14** battery out.
5. **J5, J10, J11, J15** male headers.
6. **Female headers last**: J1, J2 (RAK), J3 (XIAO), J4 (card).
7. Plug the modules in. Wire a JST-PH pigtail from **J14** to the RAK's own
   battery socket, and a 4-way cable from **J5** to the display.

Every GND pin sits on a thermal relief, so they solder with a normal iron
instead of sinking all the heat into the ground plane.

### Mounting the modules

Every module interface is a plain 2.54 mm through-hole header, so you can
either socket the module on female headers (easy to swap, ~8.5 mm tall) or
solder wires straight into the same holes and mount the module elsewhere.
Both work.

If you solder a module down flat instead of on headers, note that signal
traces do run underneath it. They are covered by soldermask, so this is
fine — just don't scrape it.

---

## What was checked

Two independent sets of checks, plus KiCad's own:

| Check | Result |
|---|---|
| **KiCad 10 DRC** (the real thing, zones filled) | **0 errors, 0 warnings, 0 unconnected** |
| Copper clearance, every pair of objects on a shared layer | **pass** — 0.25 mm minimum |
| Net connectivity, by flood-fill over both layers | **pass** — every pad on every net reachable |
| Netlist vs. the proven protoboard wiring | **pass** — identical, pin for pin |
| Drill-to-drill spacing | **pass** — minimum 0.45 mm |
| Annular ring | **pass** — minimum 0.15 mm |
| Copper and drills inside the board edge | **pass** |
| Ground pour reaches every GND pad through its thermal spokes | **pass** — all 16 |
| Silkscreen collisions (text/text, text/pad, text/line) | **pass** — none |
| **Gerber round-trip**: emitted Gerbers re-read by a separate parser and compared to the model | **pass** — 0.0000 mm² difference on both copper layers |
| **Cross-check vs KiCad's own Gerber export** of the same board | **F.Cu 0.000 mm², Edge.Cuts 0.000 mm², masks 0.06 mm²** |
| Brand accent is on copper + mask, never silkscreen (regression gate) | **pass** — 37 items on each |
| Silkscreen over mounting holes | **pass** — none |
| Every region inspected visually at readable magnification, both sides | **done** |
| Wordmark outlines vs an independent FreeType rendering | **match** — IoU 0.94, aspect within 0.6% |

The strongest of these is the cross-check: KiCad was asked to export its own
Gerbers from the same board, and its top copper and board outline match ours
to **zero measurable difference**, logo included. The bottom copper differs by
about 1% — entirely at the pour's outer edge and around thermal spokes, where
two different pour algorithms are simply allowed to disagree. Both are valid.

`render3d_top.png` and `render3d_bottom.png` are KiCad's own 3D renders using
the board stackup, so they show the finished product in the colours it will be
built in.

`fab_top.png` and `fab_bottom.png` are rendered *from the Gerbers themselves*,
not from the design, and in the brand colours the board will actually be
ordered in - so what you see there is what will be manufactured.

---

## Assumptions worth knowing

1. **microSD module size.** The six pads and their order are certain (you read
   them off the board). I reserved a 24 × 21 mm box for the body, shown dashed
   on the silkscreen, with the card slot pointing at the board edge. If your
   module is longer it will simply overhang the edge, which is fine — better,
   even. If it is much shorter, the slot will sit a few mm inside the edge and
   the enclosure cut-out needs to allow for that.
2. **OLED pin order** is taken as GND, 3V3, SCL, SDA, the usual order on a
   0.91" I2C module and the same order as your existing lid cable. Worth a
   glance at your screen before you solder the header.
3. **XIAO row spacing** is 15.24 mm (0.6"), the standard for every XIAO. This
   matches your protoboard, where the two columns were six holes apart.
4. **The RAK gap**, as above — the one thing to measure.
5. There is no schematic file, only the PCB. `netlist.csv` is the full record
   of what connects to what.

## Files

```
packet-logger-carrier.kicad_pcb      open this in KiCad 10
packet-logger-carrier.kicad_pro      project file
packetlogger.pretty/                 footprint library (so nothing is unresolved)
fp-lib-table                         points KiCad at that library
packet-logger-carrier-gerbers.zip    <- upload this to JLCPCB / PCBWay
gerbers/                             the same files, unzipped
netlist.csv                          every pad, its net and its position
bom.csv                              what to buy
kicad-drc.json                       KiCad's own DRC report
fab_top.png / fab_bottom.png         rendered from the Gerbers
render3d_top.png / render3d_bottom.png   KiCad's 3D render, real colours
board.png                            routing view (top = red, bottom = blue)
mechanical/                          STEP models + sizes for enclosure design
src/                                 the generator and every verification script
```

For an enclosure, start at `mechanical/README.md`. It has the STEP files, the
overall envelope, the M3 pattern and which face each connector needs an
opening on.

To open: `File → Open`, pick `packet-logger-carrier.kicad_pcb`. The ground
pour is already filled, so it looks right immediately.

To rebuild everything from source: `cd src && python make.py` — it routes,
runs every check, writes the KiCad and Gerber files, hands the board to
KiCad 10 for a final DRC, and refuses to finish if anything fails.
