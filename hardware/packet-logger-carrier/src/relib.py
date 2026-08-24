# -*- coding: utf-8 -*-
"""Regenerate packetlogger.pretty from the KiCad-saved board, so every library
footprint is byte-for-byte what the board actually contains (no
lib_footprint_mismatch warnings)."""
import os, re, sys

def tokenize(src):
    return re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()]+', src)

def parse(toks, pos=0):
    t = toks[pos]; pos += 1
    if t == '(':
        lst = []
        while toks[pos] != ')':
            node, pos = parse(toks, pos)
            lst.append(node)
        return lst, pos + 1
    return t, pos

def ser(node, ind=0):
    pad = '\t' * ind
    if isinstance(node, str):
        return node
    if not node:
        return '()'
    head = node[0]
    simple = all(isinstance(c, str) for c in node[1:])
    if simple:
        return pad + '(' + ' '.join([head] + list(node[1:])) + ')'
    out = [pad + '(' + (head if isinstance(head, str) else '')]
    for c in node[1:]:
        if isinstance(c, str):
            out[-1] += ' ' + c
        else:
            out.append(ser(c, ind + 1))
    out.append(pad + ')')
    return '\n'.join(out)

def name_of(n):
    return n[0] if isinstance(n, list) and n and isinstance(n[0], str) else None

def strip(node, drop_uuid=True):
    """remove uuids, nets, and the footprint-level placement"""
    if isinstance(node, str):
        return node
    h = name_of(node)
    if drop_uuid and h in ('uuid', 'net', 'tstamp'):
        return None
    out = [node[0]]
    for c in node[1:]:
        r = strip(c, drop_uuid)
        if r is not None:
            out.append(r)
    return out

def main(board, outdir):
    src = open(board).read()
    toks = tokenize(src)
    tree, _ = parse(toks)
    lib = os.path.join(outdir, 'packetlogger.pretty')
    os.makedirs(lib, exist_ok=True)
    seen = {}
    for node in tree[1:]:
        if name_of(node) != 'footprint':
            continue
        libname = node[1].strip('"')
        short = libname.split(':')[-1]
        if short in seen:
            continue
        fp = strip(node)
        body = []
        for c in fp[2:]:
            h = name_of(c)
            if h == 'at':                       # placement belongs to the board
                continue
            if h == 'property' and len(c) > 2 and c[1].strip('"') == 'Reference':
                c = [c[0], c[1], '"REF**"'] + list(c[3:])
            if h == 'property' and len(c) > 2 and c[1].strip('"') == 'Footprint':
                continue
            body.append(c)
        new = ['footprint', '"%s"' % short] + body
        txt = ser(new)
        open(os.path.join(lib, '%s.kicad_mod' % short), 'w').write(txt + '\n')
        seen[short] = True
    open(os.path.join(outdir, 'fp-lib-table'), 'w').write(
        '(fp_lib_table\n  (version 7)\n'
        '  (lib (name "packetlogger")(type "KiCad")'
        '(uri "${KIPRJMOD}/packetlogger.pretty")(options "")'
        '(descr "Packet Logger carrier footprints"))\n)\n')
    print('regenerated %d footprints in %s' % (len(seen), lib))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
