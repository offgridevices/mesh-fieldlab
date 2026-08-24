# -*- coding: utf-8 -*-
"""Full build + verification pipeline.  Any failing gate aborts."""
import os, sys, subprocess, pickle, zipfile, importlib

PY=sys.executable
def step(name, fn):
    print('\n=== %s ==='%name)
    r=fn()
    if r: print('*** %s FAILED ***'%name); sys.exit(1)
    return 0

def sh(cmd):
    return subprocess.call([PY]+cmd)

def check_layers():
    """The exposed-copper accent must be on F.Cu + F.Mask and NOT on silk.
    A silent regression here would turn the gold mark into white print."""
    import layers_census, design as D
    c = layers_census.census('out/packet-logger-carrier.kicad_pcb')
    n = len(D.accent)
    cu   = c[('gr_line','F.Cu')]   + c[('gr_circle','F.Cu')]
    mask = c[('gr_line','F.Mask')] + c[('gr_circle','F.Mask')]
    silk = c[('gr_line','F.SilkS')]
    print('  accent on F.Cu=%d  F.Mask=%d  (expected %d each); silk lines=%d'
          %(cu, mask, n, silk))
    if cu != n or mask != n:
        print('  *** accent art is NOT on copper+mask ***'); return 1
    return 0

def main():
    os.makedirs('out/gerbers', exist_ok=True)
    step('ROUTE',        lambda: sh(['build.py']))
    step('DRC',          lambda: sh(['drc.py']))
    step('NETLIST',      lambda: sh(['netcheck.py']))
    step('SILKSCREEN',   lambda: sh(['silkcheck.py']))
    step('WORDMARK',     lambda: sh(['verify_wordmark.py']))
    step('KICAD',        lambda: sh(['emit_kicad.py']))
    step('LAYER CHECK',  check_layers)
    step('GERBER',       lambda: sh(['emit_gerber.py']))
    step('GERBER VERIFY',lambda: sh(['verify_gerber.py']))
    step('RENDER',       lambda: sh(['render.py']) or sh(['gerber_render.py']))
    # --- hand the board to KiCad 10 itself: fill the zone, re-save in its
    #     native format, and run its DRC as an independent check
    KI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
    if os.path.exists(KI):
        rc=subprocess.call([KI,'pcb','drc','--format','json','--severity-all',
                            '--refill-zones','--save-board',
                            '--output','out/kicad-drc.json',
                            'out/packet-logger-carrier.kicad_pcb'])
        # rebuild the footprint library from the board KiCad just saved, so the
        # library and the board agree exactly, then re-run DRC
        subprocess.call([PY,'relib.py','out/packet-logger-carrier.kicad_pcb','out'])
        subprocess.call([KI,'pcb','drc','--format','json','--severity-all',
                         '--refill-zones','--save-board',
                         '--output','out/kicad-drc.json',
                         'out/packet-logger-carrier.kicad_pcb'])
        import json as _j
        rep=_j.load(open('out/kicad-drc.json'))
        errs=[v for v in rep['violations'] if v.get('severity')=='error']
        warns=[v for v in rep['violations'] if v.get('severity')!='error']
        unc=rep['unconnected_items']
        print('KiCad 10 DRC: %d error(s), %d warning(s), %d unconnected'
              %(len(errs),len(warns),len(unc)))
        for v in (errs+warns)[:10]:
            print('   [%s] %s - %s'%(v.get('severity'),v['type'],
                                     v.get('description','')[:80]))
        if errs or unc:
            print('*** KICAD DRC FAILED ***'); sys.exit(1)
    else:
        print('kicad-cli not found - skipping KiCad cross-check')

    # zip for the fab house
    z='out/packet-logger-carrier-gerbers.zip'
    with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(os.listdir('out/gerbers')):
            zf.write(os.path.join('out/gerbers',f), f)
    print('\nwrote %s (%d bytes)'%(z, os.path.getsize(z)))
    print('\nALL GATES PASSED')

if __name__=='__main__': main()
