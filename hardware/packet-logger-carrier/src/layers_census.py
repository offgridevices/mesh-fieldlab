# -*- coding: utf-8 -*-
"""Proper s-expression census of board-level graphics per layer."""
import sys, collections
import relib


def census(path):
    toks = relib.tokenize(open(path).read())
    tree, _ = relib.parse(toks)
    out = collections.Counter()
    for node in tree[1:]:
        h = relib.name_of(node)
        if h not in ('gr_line', 'gr_circle', 'gr_poly', 'gr_rect', 'gr_arc', 'gr_text'):
            continue
        lay = None
        for c in node[1:]:
            if relib.name_of(c) == 'layer':
                lay = c[1].strip('"')
        out[(h, lay)] += 1
    return out


if __name__ == '__main__':
    for p in sys.argv[1:]:
        print('===', p)
        c = census(p)
        for (h, lay), n in sorted(c.items(), key=lambda kv: (kv[0][1] or '', kv[0][0])):
            print('   %-10s %-12s %d' % (h, lay, n))
