# Packet Logger Carrier Board — v1

A single 2-layer PCB that replaces the hand-wired 7 × 9 cm protoboard node.
Drop in the **RAK19003**, the **XIAO ESP32-C6** and the **microSD breakout**,
add a button and a power switch, and every connection in the build record is
made in copper instead of wire.

**Board: 86 × 58 mm, 2 layers, 1.6 mm FR4.**
64 solder points total. 91 track segments, 9 vias, full ground plane underneath.

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
9.2 – 10.3 mm is covered. If it is outside that, tell me and I will re-cut the
footprint.

---

## Pin order — verified against the datasheet, not guessed

Looking at the board with the RAK's body pointing away from you (its USB-C,
battery, solar and reset are all on the far edge), left to right:

```
J6:  VDD   GND   SCL   SDA        [ 9.41 mm gap ]        J7:  BOOT  GND  TX0  RX0
```

This is confirmed two independent ways: it is what you read off your own
board, and it is what RAK's Figure 3 shows once you rotate the board 90° to
match how you have it mounted. The Rev E silkscreen says **TX0 / RX0** (the
older datasheet table calls the same pins TX1 / RX1 — same physical pins).

Every pad on the PCB is labelled in silkscreen with the name printed on the
module it mates with.

---

## What's on the board

| Ref | What | Pins |
|---|---|---|
| J1 / J2 | RAK19003 J6 and J7 | 4 + 4 |
| J3 | XIAO ESP32-C6, 2×7, rows 15.24 mm apart, **USB-C faces east** | 14 |
| J4 | microSD breakout, 1×6 | 6 |
| J5 | **Lid cable** — GND, 3V3, SCL, SDA, BTN | 5 |
| SW1 | User button, 6 mm tact, on the board | 4 |
| SW2 | Power switch — centre pin is the input | 3 |
| J12 / J13 | Battery in — bare wires or JST-PH 2.0, wired in parallel | 2 + 2 |
| J14 | Switched battery out → the RAK's own battery socket | 2 |
| J10 | RAK spare: BOOT, SCL, SDA, GND | 4 |
| J11 | ESP spare: 5V, D1, D2, GND | 4 |
| JP1 | 3V3 link — **fit a shunt** (see below) | 2 |
| C1–C4 | Decoupling, all optional, all 2.54 mm lead pitch | 8 |

**Your one ribbon cable is J5** — five conductors to the lid, in the same
order as the cable you already made for the protoboard: GND, 3V3, BTN, SCL,
SDA. The button is on the board *and* on J5 pin 5 in parallel, so you can use
either or both.

### The 3V3 link (JP1)

The RAK's 3.3 V comes in on JP1's "RAK" pin and leaves on "SYS" to feed the
XIAO, the card and the OLED. Fit a jumper shunt for normal use.

Pull the shunt when you want to program the XIAO over USB with the RAK
powered — it stops the RAK's regulator and the XIAO's regulator fighting over
the same rail. With the shunt out, USB still powers the XIAO, the card and
the screen; only the RAK is separated.

If you'd rather never think about it, bridge the two pads with solder.

---

## Ordering

JLCPCB or PCBWay, default everything:

* 2 layers, 1.6 mm, HASL or ENIG, any colour
* **86 × 58 mm** — inside the cheap 100 × 100 mm tier
* Upload `packet-logger-carrier-gerbers.zip` as-is
* Minimum order is 5; you need 4, so you get a spare
* Expect roughly $2–5 for the boards plus shipping, about 1–2 weeks

The zip contains top and bottom copper, both soldermasks, top silkscreen,
board outline, and separate plated / non-plated drill files. J7's oval slots
are in the plated drill file as routed slots (G85) — both houses handle these
as standard.

---

## Assembly order

1. **C1–C4 first** if you're fitting them (lowest parts first). They're optional.
2. **JP1**, then the shunt.
3. **SW1** the tact switch, **SW2** the slide switch (or wires to a panel switch).
4. **J12/J13** battery in, **J14** battery out.
5. **J5, J10, J11** male headers.
6. **Female headers last**: J1, J2 (RAK), J3 (XIAO), J4 (card).
7. Plug the modules in. Wire a JST-PH pigtail from **J14** to the RAK's own
   battery socket, and run the 5-way cable from **J5** to the lid.

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

I could not install KiCad on this machine (its installer wanted an admin
password), so instead of leaning on KiCad's DRC I wrote independent checks and
ran them against the finished files:

| Check | Result |
|---|---|
| Copper clearance, every pair of objects on a shared layer | **pass** — minimum 0.25 mm designed, 0.20 mm required |
| Net connectivity, by flood-fill over both layers | **pass** — every pad on every net reachable |
| Netlist vs. the proven protoboard wiring | **pass** — identical, pin for pin |
| Drill-to-drill spacing | **pass** — minimum 0.45 mm |
| Annular ring | **pass** — minimum 0.15 mm |
| Copper and drills inside the board edge | **pass** |
| Ground pour reaches every GND pad through its thermal spokes | **pass** — all 15 |
| Silkscreen collisions (text over text, text over pads) | **pass** — none |
| **Gerber round-trip**: re-read the emitted Gerbers with a separate parser and compared to the model | **pass** — 0.0000 mm² difference on both copper layers |

The last one is the important one: the files that go to the fab were read back
independently and render exactly the intended copper.

`fab_top.png` and `fab_bottom.png` are rendered *from the Gerbers themselves*,
not from the design — what you see there is what will be manufactured.

---

## Assumptions worth knowing

1. **microSD module size.** Yours is a 6-pin 3.3 V board with pins reading
   3V3, CS, MOSI, CLK, MISO, GND. I reserved a 24 × 22 mm box for its body
   (dashed on the silkscreen). If your module is bigger it will overhang the
   dashed box — harmless, but check it doesn't foul the XIAO. The six pads
   and their order are certain; only the body outline is an estimate.
2. **XIAO row spacing** is 15.24 mm (0.6"), the standard for every XIAO. This
   matches your protoboard, where the two columns were six holes apart.
3. **The RAK gap**, as above — the one thing to measure.
4. There is no schematic file, only the PCB. `netlist.csv` is the full record
   of what connects to what.

## Files

```
packet-logger-carrier.kicad_pcb      open this in KiCad (7, 8 or 9)
packet-logger-carrier.kicad_pro      project file
packet-logger-carrier-gerbers.zip    <- upload this to JLCPCB / PCBWay
gerbers/                             the same files, unzipped
netlist.csv                          every pad, its net and its position
bom.csv                              what to buy
fab_top.png / fab_bottom.png         rendered from the Gerbers
board.png                            routing view (top = red, bottom = blue)
src/                                 the generator + all the verification code
```

To open in KiCad: `File → Open`, pick `packet-logger-carrier.kicad_pcb`.
The ground pour is defined as a zone; press **B** to fill it on screen.
KiCad's own DRC should also come up clean — if it flags anything, tell me.
