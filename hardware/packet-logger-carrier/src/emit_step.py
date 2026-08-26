# -*- coding: utf-8 -*-
"""Mechanical model of the carrier board, for designing an enclosure around it.

Writes two STEP files into ../mechanical:

  packet-logger-carrier-board.step
      The bare plate only - 86 x 58 x 1.6 mm, every drilled hole, both routed
      slots, the four M3 mounting holes.  Use this if all you want is the
      outline and the screw pattern.

  packet-logger-carrier.step
      The same plate plus a named solid for every part that stands above it.
      This is the one to open when designing the box.  Each part is its own
      named component in the STEP tree, so any CAD tool can hide them one at
      a time.

Where the numbers come from
---------------------------
Everything in the XY plane - outline, holes, slots, and where each part sits -
is read straight out of design.py, the same source the Gerbers were generated
from.  The model therefore cannot drift from the board that was ordered, and
nothing in this file writes to the fabrication outputs.

Heights are a different matter.  The footprints carry no 3D models, so no
height here comes from KiCad.  They are nominal part envelopes.  Each one is
labelled below with where it came from, and the ones worth putting calipers
on before cutting an enclosure are marked MEASURE.

Run:  cd src && python3 emit_step.py --check
"""
import os, re, sys
import cadquery as cq
import design as D

TH   = 1.6      # nominal finished board thickness, what the fab ships
CORE = 1.51     # dielectric core alone - what KiCad's own STEP export gives.
                # Only used by the cross-check at the bottom of this file.
HDR  = 8.5      # a module socketed on 2.54 mm female headers stands this far
                # off the board.  README.md: "socket the module on female
                # headers (easy to swap, ~8.5 mm tall)".
P    = D.P

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.normpath(os.path.join(HERE, '..', 'mechanical'))
PCB  = os.path.normpath(os.path.join(HERE, '..', 'packet-logger-carrier.kicad_pcb'))


# ------------------------------------------------------------------ helpers
def box(x0, y0, x1, y1, z0, z1):
    """Block in board coordinates.  z is measured from the top of the board."""
    return (cq.Workplane('XY')
            .box(x1 - x0, y1 - y0, z1 - z0, centered=(True, True, False))
            .translate(((x0 + x1) / 2.0, (y0 + y1) / 2.0, TH + z0)))


def cyl(x, y, d, z0, z1):
    return (cq.Workplane('XY').circle(d / 2.0).extrude(z1 - z0)
            .translate((x, y, TH + z0)))


def header(x0, y, n, z0=0.0, z1=HDR, pitch=P):
    """Body of a 1xN 2.54 mm header, centred on its pins."""
    return box(x0 - pitch / 2.0, y - pitch / 2.0,
               x0 + (n - 1) * pitch + pitch / 2.0, y + pitch / 2.0, z0, z1)


# ------------------------------------------------------------------ the board
def vias():
    """Via drills, read back out of the board file that was actually ordered."""
    txt = open(PCB).read()
    pat = re.compile(r'\(via\b.*?\(at\s+([-\d.]+)\s+([-\d.]+)\).*?'
                     r'\(drill\s+([\d.]+)\)', re.S)
    out = []
    for m in pat.finditer(txt):
        kx, ky, drl = float(m.group(1)), float(m.group(2)), float(m.group(3))
        # emit_kicad.py: KX(x)=x+20, KY(y)=(BH-y)+20.  Invert both.
        out.append((kx - 20.0, D.BH - (ky - 20.0), drl))
    return out


def plate(th):
    """Board outline with every hole and slot cut through it."""
    b = (cq.Workplane('XY')
         .box(D.BW, D.BH, th, centered=(True, True, False))
         .translate((D.BW / 2.0, D.BH / 2.0, 0)))

    round_holes = [(x, y, d) for (x, y, d) in D.holes]                # M3, NPTH
    round_holes += [(p['x'], p['y'], p['drill'])
                    for p in D.pads if not p['dslot']]
    round_holes += [(x, y, d) for (x, y, d) in vias()]

    cut = cq.Workplane('XY')
    for (x, y, d) in round_holes:
        cut = cut.moveTo(x, y).circle(d / 2.0)
    cut = cut.extrude(th + 2.0).translate((0, 0, -1.0))
    b = b.cut(cut)

    slots = [p for p in D.pads if p['dslot']]
    if slots:
        sc = cq.Workplane('XY')
        for p in slots:
            w, h = p['dslot']                   # 1.0 wide x 2.0 long, vertical
            sc = sc.moveTo(p['x'], p['y']).slot2D(h, w, 90)
        sc = sc.extrude(th + 2.0).translate((0, 0, -1.0))
        b = b.cut(sc)

    return b, len(round_holes), len(slots)


# ------------------------------------------------------------------ the parts
#  name, solid, colour, note.  z is always measured up from the board surface.
def parts():
    RAK = D.RAK_BODY
    XI  = D.XI_BODY
    SD  = D.SD_BODY
    grey = (0.25, 0.25, 0.27)
    blue = (0.16, 0.34, 0.60)
    red  = (0.62, 0.20, 0.18)
    tan  = (0.55, 0.50, 0.42)
    p = []

    # --- RAK19003 on two 1x4 sockets.  USB-C / battery / solar / reset all sit
    #     on its NORTH edge (y = 55), 3 mm in from the board edge.
    p.append(('J1_socket_RAK_J6', header(D.RAK_X0, D.RAK_PY, 4), grey,
              'female header'))
    p.append(('J2_socket_RAK_J7', header(D.J7X0, D.RAK_PY, 4), grey,
              'female header, oval slots'))
    p.append(('RAK19003_module',
              box(RAK[0], RAK[1], RAK[2], RAK[3], HDR, HDR + 7.5), blue,
              'MEASURE - 30.4 x 35 body from silk; 7.5 mm allows the base '
              'board, the core module on top of it and the USB-C shell'))

    # --- XIAO on a 2x7 socket.  USB-C points EAST (x = 85), 1 mm from the edge.
    p.append(('J3_socket_XIAO_bottom', header(D.XI_X0, D.XI_YB, 7), grey,
              'female header'))
    p.append(('J3_socket_XIAO_top', header(D.XI_X0, D.XI_YT, 7), grey,
              'female header'))
    p.append(('XIAO_ESP32C6_module',
              box(XI[0], XI[1], XI[2], XI[3], HDR, HDR + 3.5), blue,
              'MEASURE - 21 x 17.8 body from silk; 3.5 mm is PCB plus the '
              'shield and USB-C shell'))

    # --- microSD breakout, body hanging SOUTH so the card slot reaches the edge
    p.append(('J4_socket_microSD', header(D.SD_X0, D.SD_Y, 6), grey,
              'female header'))
    p.append(('microSD_breakout',
              box(SD[0], SD[1], SD[2], SD[3], HDR, HDR + 3.5), blue,
              'MEASURE - 24 x 21.4 reserved box; module may overhang the '
              'south edge, which is fine.  3.5 mm is PCB plus card socket'))

    # --- switches
    p.append(('SW1_user_button_body',
              box(D.BTX - 3.0, D.BTY - 3.0, D.BTX + 3.0, D.BTY + 3.0, 0, 3.5),
              red, '6 x 6 mm through-hole tact switch'))
    p.append(('SW1_user_button_plunger', cyl(D.BTX, D.BTY, 3.5, 3.5, 5.0), red,
              'MEASURE - plunger height varies by part (4.3 / 5 / 7 / 9.5 mm)'))
    p.append(('SW2_power_slide_body',
              box(22.54 - 4.0, 6.0 - 2.0, 22.54 + 4.0, 6.0 + 2.0, 0, 4.0),
              red, 'SS-12D00 body, 8.0 x 4.0 mm, from design.py'))
    p.append(('SW2_power_slide_actuator',
              box(22.54 - 1.5, 6.0 - 1.0, 22.54 + 1.5, 6.0 + 1.0, 4.0, 7.0),
              red, 'MEASURE - actuator height varies by SS-12D00 suffix'))

    # --- battery in
    p.append(('J13_JST_PH', box(11.05, 3.6, 16.95, 8.4, 0, 6.0), tan,
              'S2B-PH-K-S, silk outline from design.py'))
    p.append(('J12_batt_wires', header(6.0, 6.0, 2), grey, '1x2 header'))
    p.append(('J14_batt_to_RAK', header(30.0, 6.0, 2), grey, '1x2 header'))

    # --- the rest of the headers
    p.append(('JP1_3V3_link', header(36.0, D.JPY, 2, 0, 9.0), grey,
              '1x2 header with a shunt fitted on top'))
    p.append(('J10_RAK_spare', header(43.0, D.JPY, 4), grey, '1x4 header'))
    p.append(('J5_lid_cable_OLED', header(54.0, D.NY, 4), grey,
              'male header - the display lives in the LID, on a cable'))
    p.append(('J15_ext_button', header(65.0, D.NY, 2), grey, '1x2 header'))
    p.append(('J11_ESP_spare', header(71.0, D.NY, 4), grey, '1x4 header'))

    # --- optional decoupling.  Not fitted by default, but if you fit them the
    #     box has to clear them, so they are in the model.
    p.append(('C1_100uF_OPTIONAL', cyl(73.27, 12.5, 6.3, 0, 11.0), tan,
              'OPTIONAL - 6.3 mm dia electrolytic on 2.54 lead pitch'))
    p.append(('C2_10uF_OPTIONAL', cyl(40.77, 26.5, 5.0, 0, 11.0), tan,
              'OPTIONAL - 5 mm dia electrolytic'))
    p.append(('C3_100nF_OPTIONAL',
              box(40.77 - 2.5, 30.5 - 1.5, 40.77 + 2.5, 30.5 + 1.5, 0, 5.0),
              tan, 'OPTIONAL - ceramic'))
    p.append(('C4_100nF_OPTIONAL',
              box(49.27 - 2.5, 53.0 - 1.5, 49.27 + 2.5, 53.0 + 1.5, 0, 5.0),
              tan, 'OPTIONAL - ceramic'))
    return p


# ------------------------------------------------------------------ build
def main():
    os.makedirs(OUT, exist_ok=True)

    b, nround, nslot = plate(TH)
    print('board  %.1f x %.1f x %.2f mm, %d round holes, %d routed slots'
          % (D.BW, D.BH, TH, nround, nslot))

    board_only = os.path.join(OUT, 'packet-logger-carrier-board.step')
    cq.exporters.export(b, board_only)
    print('wrote', os.path.relpath(board_only, HERE))

    pl = parts()
    assy = cq.Assembly(name='packet-logger-carrier')
    assy.add(b, name='PCB_86x58x1.6', color=cq.Color(0.10, 0.10, 0.11, 1.0))
    for (name, solid, col, note) in pl:
        assy.add(solid, name=name, color=cq.Color(col[0], col[1], col[2], 1.0))

    full = os.path.join(OUT, 'packet-logger-carrier.step')
    (assy.export if hasattr(assy, 'export') else assy.save)(full)
    print('wrote', os.path.relpath(full, HERE), '- %d parts' % len(pl))

    ordered = sorted(pl, key=lambda t: -t[1].val().BoundingBox().zmax)
    top = ordered[0]
    print('\ntallest part: %s, %.1f mm above the board top (%.1f mm overall)'
          % (top[0], top[1].val().BoundingBox().zmax - TH,
             top[1].val().BoundingBox().zmax))
    print('\nparts and their nominal heights above the board:')
    for (name, solid, col, note) in ordered:
        print('  %-26s %5.1f  %s'
              % (name, solid.val().BoundingBox().zmax - TH, note))
    return 0


# ------------------------------------------------------------------ check
def check():
    """Cross-check the plate against KiCad's own STEP export of the same board.

    KiCad exports the dielectric core alone (1.51 mm) when asked for the board
    body, so rebuild at 1.51 and the two volumes have to agree.  If they do,
    every hole and slot in this model is in the right place - the two were
    derived independently, one from design.py and one from the .kicad_pcb.
    """
    import subprocess, tempfile
    kc = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
    if not os.path.exists(kc):
        print('kicad-cli not found - skipping cross-check')
        return 0
    # --cut-vias-in-body matters: without it KiCad leaves the 18 via holes
    # filled in when only the board body is exported, and the two volumes
    # then differ by exactly the via volume.
    tmp = os.path.join(tempfile.mkdtemp(), 'kicad-board.step')
    r = subprocess.run([kc, 'pcb', 'export', 'step', '--board-only',
                        '--cut-vias-in-body',
                        '--user-origin', '20x78mm', '--force', '-o', tmp, PCB],
                       capture_output=True, text=True)
    if not os.path.exists(tmp):
        print('kicad export failed:', r.stderr[-400:])
        return 1
    theirs = cq.importers.importStep(tmp).val()
    mine, _, _ = plate(CORE)
    mv, tv = mine.val().Volume(), theirs.Volume()
    bb, tb = mine.val().BoundingBox(), theirs.BoundingBox()
    print("\ncross-check against KiCad's own export of the ordered board")
    print('  volume   mine %.3f mm3   kicad %.3f mm3   diff %.4f%%'
          % (mv, tv, abs(mv - tv) / tv * 100.0))
    print('  bbox     mine %.2f x %.2f x %.2f   kicad %.2f x %.2f x %.2f'
          % (bb.xlen, bb.ylen, bb.zlen, tb.xlen, tb.ylen, tb.zlen))
    ok = (abs(mv - tv) / tv < 0.001
          and abs(bb.xlen - tb.xlen) < 1e-6
          and abs(bb.ylen - tb.ylen) < 1e-6)
    print('  ' + ('OK' if ok else '*** MISMATCH ***'))
    return 0 if ok else 1


def check_parts():
    """Every part must sit centred on its own pads.

    Each part above is placed from a constant in design.py; each pad was placed
    from the same constants, but by a different piece of code.  So if a header
    here has the wrong pin count, the wrong pitch, or the wrong origin, its
    centre stops agreeing with the centroid of the pads carrying its reference
    designator.  Expected deviation is zero.
    """
    pl = parts()
    refs = sorted({p['ref'] for p in D.pads})
    worst, bad = 0.0, []
    print('\npart placement against the pads of the same reference')
    for ref in refs:
        mine = [s for (n, s, c, note) in pl if n.split('_')[0] == ref]
        if not mine:
            bad.append('%s has no solid in the model' % ref)
            continue
        xs, ys = [], []
        for s in mine:
            bb = s.val().BoundingBox()
            xs += [bb.xmin, bb.xmax]
            ys += [bb.ymin, bb.ymax]
        cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
        pads = [p for p in D.pads if p['ref'] == ref]
        px = sum(p['x'] for p in pads) / len(pads)
        py = sum(p['y'] for p in pads) / len(pads)
        d = max(abs(cx - px), abs(cy - py))
        worst = max(worst, d)
        if d > 0.001:
            bad.append('%s off by %.3f mm' % (ref, d))
    print('  %d references checked, worst offset %.4f mm' % (len(refs), worst))
    for m in bad:
        print('  *** ' + m)
    print('  ' + ('OK' if not bad else '*** MISMATCH ***'))
    return 0 if not bad else 1


if __name__ == '__main__':
    rc = main()
    if '--check' in sys.argv or '-c' in sys.argv:
        rc |= check()
        rc |= check_parts()
    sys.exit(rc)
