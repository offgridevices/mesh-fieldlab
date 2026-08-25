# -*- coding: utf-8 -*-
"""Closest approach of any foreign copper to the named pads."""
# routed.pkl is our own build output.
import pickle, sys
import design as D
import drc


def main(want):
    d = pickle.load(open('routed.pkl', 'rb'))
    objs = drc.build_objs(d['tracks'], d['vias'])
    for ref, pin in want:
        p = [q for q in D.pads if q['ref'] == ref and q['pin'] == pin][0]
        po = drc.pad_obj(p)
        rows = []
        for o in objs:
            if o.net == p['net'] and p['net'] is not None:
                continue
            if not (set(o.layers) & set(po.layers)):
                continue
            g = drc.gap(po, o)
            if g < 1.5:
                rows.append((g, o.net, o.tag))
        rows.sort()
        lbl = {'13': 'XIAO D1', '14': 'XIAO D0/BTN', '12': 'XIAO D2',
               '10': 'XIAO D3', '9': 'XIAO D4'}.get(pin, '')
        print('%s.%s  %-12s net %-9s' % (ref, pin, lbl, p['net']))
        if not rows:
            print('    nothing within 1.5 mm')
        for g, net, tag in rows[:4]:
            print('    %.3f mm to %-9s (%s)' % (g, net, tag))
        print()


if __name__ == '__main__':
    main([('J3', '13'), ('J3', '14'), ('J3', '12'), ('J3', '10'), ('J3', '9')])
