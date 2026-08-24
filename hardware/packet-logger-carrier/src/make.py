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

def main():
    os.makedirs('out/gerbers', exist_ok=True)
    step('ROUTE',        lambda: sh(['build.py']))
    step('DRC',          lambda: sh(['drc.py']))
    step('NETLIST',      lambda: sh(['netcheck.py']))
    step('SILKSCREEN',   lambda: sh(['silkcheck.py']))
    step('KICAD',        lambda: sh(['emit_kicad.py']))
    step('GERBER',       lambda: sh(['emit_gerber.py']))
    step('GERBER VERIFY',lambda: sh(['verify_gerber.py']))
    step('RENDER',       lambda: sh(['render.py']) or sh(['gerber_render.py']))
    # zip for the fab house
    z='out/packet-logger-carrier-gerbers.zip'
    with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(os.listdir('out/gerbers')):
            zf.write(os.path.join('out/gerbers',f), f)
    print('\nwrote %s (%d bytes)'%(z, os.path.getsize(z)))
    print('\nALL GATES PASSED')

if __name__=='__main__': main()
