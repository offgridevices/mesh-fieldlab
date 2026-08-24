# -*- coding: utf-8 -*-
"""Print the routing of one or more nets, layer by layer."""
# routed.pkl is written by our own build.py in this same directory - it is
# build output, not external input, so unpickling it is safe here.
import pickle, sys


def main(nets):
    d = pickle.load(open('routed.pkl', 'rb'))
    for net in nets:
        print('===', net)
        for (n, l, x0, y0, x1, y1, w) in d['tracks']:
            if n != net:
                continue
            print('   %-6s (%6.2f,%6.2f) -> (%6.2f,%6.2f)  w=%.2f'
                  % ('TOP' if l == 0 else 'BOTTOM', x0, y0, x1, y1, w))
        for (n, x, y) in d['vias']:
            if n == net:
                print('   VIA    (%6.2f,%6.2f)   crosses top <-> bottom' % (x, y))
        print()


if __name__ == '__main__':
    main(sys.argv[1:])
