# -*- coding: utf-8 -*-
import pickle, json, collections, os, uuid
import design as D

OX, OY = 20.0, 20.0
def KX(x): return round(x+OX,4)
def KY(y): return round((D.BH-y)+OY,4)
def U(): return str(uuid.uuid4())

LAYERS = [(0,'F.Cu','signal',None),(31,'B.Cu','signal',None),
 (32,'B.Adhes','user','B.Adhesive'),(33,'F.Adhes','user','F.Adhesive'),
 (34,'B.Paste','user',None),(35,'F.Paste','user',None),
 (36,'B.SilkS','user','B.Silkscreen'),(37,'F.SilkS','user','F.Silkscreen'),
 (38,'B.Mask','user',None),(39,'F.Mask','user',None),
 (40,'Dwgs.User','user','User.Drawings'),(41,'Cmts.User','user','User.Comments'),
 (42,'Eco1.User','user','User.Eco1'),(43,'Eco2.User','user','User.Eco2'),
 (44,'Edge.Cuts','user',None),(45,'Margin','user',None),
 (46,'B.CrtYd','user','B.Courtyard'),(47,'F.CrtYd','user','F.Courtyard'),
 (48,'B.Fab','user',None),(49,'F.Fab','user',None)]

VALUE = {'J1':'RAK19003 J6','J2':'RAK19003 J7','J3':'XIAO ESP32-C6','J4':'microSD',
         'J5':'LID CABLE','J10':'RAK SPARE','J11':'ESP SPARE','J12':'BATT IN',
         'J13':'BATT JST-PH','J14':'BATT TO RAK','SW1':'USER BUTTON',
         'SW2':'POWER SWITCH','JP1':'3V3 LINK','C1':'100u','C2':'10u',
         'C3':'100n','C4':'100n'}

def write(path):
    d=pickle.load(open('routed.pkl','rb')); tracks,vias=d['tracks'],d['vias']
    nets=['']+sorted({p['net'] for p in D.pads if p['net']})
    nid={n:i for i,n in enumerate(nets)}
    o=[]
    o.append('(kicad_pcb (version 20221018) (generator "packet-logger-carrier")')
    o.append('  (general (thickness 1.6))')
    o.append('  (paper "A4")')
    o.append('  (title_block (title "Packet Logger Carrier") (rev "v1")')
    o.append('    (comment 1 "2 layer - 86 x 58 mm - 1.6 mm FR4")')
    o.append('    (comment 2 "Modules: RAK19003 + XIAO ESP32-C6 + microSD"))')
    o.append('  (layers')
    for (n,nm,ty,us) in LAYERS:
        o.append('    (%d "%s" %s%s)'%(n,nm,ty,(' "%s"'%us) if us else ''))
    o.append('  )')
    o.append('  (setup')
    # Physical stackup, so KiCad's 3D view shows the board in the colours it
    # will actually be ordered in - and so the fab sees the intent too.
    #   OffGrid: Pitch mask / Bone silkscreen / ENIG gold for the Ember accent
    o.append('    (stackup')
    o.append('      (layer "F.SilkS" (type "Top Silk Screen") (color "White"))')
    o.append('      (layer "F.Paste" (type "Top Solder Paste"))')
    o.append('      (layer "F.Mask" (type "Top Solder Mask") (color "Black") (thickness 0.01))')
    o.append('      (layer "F.Cu" (type "copper") (thickness 0.035))')
    o.append('      (layer "dielectric 1" (type "core") (thickness 1.51) '
             '(material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))')
    o.append('      (layer "B.Cu" (type "copper") (thickness 0.035))')
    o.append('      (layer "B.Mask" (type "Bottom Solder Mask") (color "Black") (thickness 0.01))')
    o.append('      (layer "B.Paste" (type "Bottom Solder Paste"))')
    o.append('      (layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))')
    o.append('      (copper_finish "ENIG")')
    o.append('      (dielectric_constraints no)')
    o.append('    )')
    o.append('    (pad_to_mask_clearance 0.05)')
    o.append('    (allow_soldermask_bridges_in_footprints no)')
    o.append('  )')
    for i,n in enumerate(nets):
        o.append('  (net %d "%s")'%(i,n))

    # ---------------- footprints
    groups=collections.OrderedDict()
    for p in D.pads: groups.setdefault(p['ref'],[]).append(p)
    for ref,pl in groups.items():
        cx=sum(q['x'] for q in pl)/len(pl); cy=sum(q['y'] for q in pl)/len(pl)
        o.append('  (footprint "packetlogger:%s" (layer "F.Cu")'%ref)
        o.append('    (uuid "%s")'%U())
        o.append('    (at %s %s)'%(KX(cx),KY(cy)))
        o.append('    (attr through_hole)')
        o.append('    (fp_text reference "%s" (at 0 -4.2) (layer "F.Fab") (uuid "%s")'%(ref,U()))
        o.append('      (effects (font (size 0.8 0.8) (thickness 0.12))))')
        o.append('    (fp_text value "%s" (at 0 4.2) (layer "F.Fab") hide (uuid "%s")'%(VALUE.get(ref,ref),U()))
        o.append('      (effects (font (size 0.8 0.8) (thickness 0.12))))')
        for q in pl:
            dx=round(q['x']-cx,4); dy=round(-(q['y']-cy),4)
            shp={'rect':'rect','oval':'oval','circle':'circle'}[q['shape']]
            if q['dslot']:
                dw,dh=q['dslot']; drill='(drill oval %s %s)'%(dw,dh)
            else:
                drill='(drill %s)'%q['drill']
            net='' if not q['net'] else ' (net %d "%s")'%(nid[q['net']],q['net'])
            o.append('    (pad "%s" thru_hole %s (at %s %s) (size %s %s) %s '
                     '(layers "*.Cu" "*.Mask")%s (uuid "%s"))'
                     %(q['pin'],shp,dx,dy,q['w'],q['h'],drill,net,U()))
        o.append('  )')
    # mounting holes
    for k,(hx,hy,hd) in enumerate(D.holes):
        o.append('  (footprint "packetlogger:MountingHole" (layer "F.Cu")')
        o.append('    (uuid "%s")'%U())
        o.append('    (at %s %s)'%(KX(hx),KY(hy)))
        o.append('    (attr exclude_from_pos_files exclude_from_bom)')
        o.append('    (fp_text reference "H%d" (at 0 -2.6) (layer "F.Fab") (uuid "%s")'%(k+1,U()))
        o.append('      (effects (font (size 0.7 0.7) (thickness 0.1))))')
        o.append('    (fp_text value "M3" (at 0 2.6) (layer "F.Fab") hide (uuid "%s")'%U())
        o.append('      (effects (font (size 0.7 0.7) (thickness 0.1))))')
        o.append('    (pad "" np_thru_hole circle (at 0 0) (size %s %s) (drill %s) '
                 '(layers "F&B.Cu" "*.Mask") (uuid "%s"))'%(hd,hd,hd,U()))
        o.append('  )')

    # ---------------- silkscreen
    for it in D.silk:
        if it[0]=='poly':
            pts=' '.join('(xy %s %s)'%(KX(a),KY(b)) for (a,b) in it[1])
            o.append('  (gr_poly (pts %s) (stroke (width 0) (type solid)) '
                     '(fill solid) (layer "F.SilkS") (uuid "%s"))'%(pts,U()))
        elif it[0]=='disc':
            _,dx,dy,dr,_l = it
            o.append('  (gr_circle (center %s %s) (end %s %s) '
                     '(stroke (width 0.05) (type solid)) (fill solid) '
                     '(layer "F.SilkS") (uuid "%s"))'
                     %(KX(dx),KY(dy),KX(dx+dr),KY(dy),U()))
        elif it[0]=='line':
            _,x1,y1,x2,y2,w,layer=it
            o.append('  (gr_line (start %s %s) (end %s %s) (stroke (width %s) (type solid)) '
                     '(layer "F.SilkS") (uuid "%s"))'%(KX(x1),KY(y1),KX(x2),KY(y2),w,U()))
        else:
            _,x,y,s,size,just,angle,layer,th=it
            j='' if just=='center' else ' (justify %s)'%just
            o.append('  (gr_text "%s" (at %s %s %d) (layer "F.SilkS") (uuid "%s")'
                     %(s.replace('"','\''),KX(x),KY(y),angle,U()))
            o.append('    (effects (font (size %s %s) (thickness %s))%s))'%(size,size,round(th,3),j))
    # ---------------- brand accent: exposed copper (F.Cu) + mask opening
    for it in getattr(D,'accent',[]):
        for lay in ('F.Cu','F.Mask'):
            if it[0]=='line':
                _,x1,y1,x2,y2,w,_l = it
                o.append('  (gr_line (start %s %s) (end %s %s) '
                         '(stroke (width %s) (type solid)) (layer "%s") (uuid "%s"))'
                         %(KX(x1),KY(y1),KX(x2),KY(y2),round(w,4),lay,U()))
            else:
                _,x,y,rr,_l = it
                o.append('  (gr_circle (center %s %s) (end %s %s) '
                         '(stroke (width 0.05) (type solid)) (fill solid) '
                         '(layer "%s") (uuid "%s"))'
                         %(KX(x),KY(y),KX(x+rr),KY(y),lay,U()))

    # ---------------- outline
    pts=D.outline+[D.outline[0]]
    for k in range(len(pts)-1):
        o.append('  (gr_line (start %s %s) (end %s %s) (stroke (width 0.1) (type solid)) '
                 '(layer "Edge.Cuts") (uuid "%s"))'
                 %(KX(pts[k][0]),KY(pts[k][1]),KX(pts[k+1][0]),KY(pts[k+1][1]),U()))
    # ---------------- copper
    for (n,l,x0,y0,x1,y1,w) in tracks:
        o.append('  (segment (start %s %s) (end %s %s) (width %s) (layer "%s") '
                 '(net %d) (uuid "%s"))'
                 %(KX(x0),KY(y0),KX(x1),KY(y1),w,'F.Cu' if l==0 else 'B.Cu',nid[n],U()))
    for (n,x,y) in vias:
        o.append('  (via (at %s %s) (size %s) (drill %s) (layers "F.Cu" "B.Cu") '
                 '(net %d) (uuid "%s"))'%(KX(x),KY(y),D.VIA_D,D.VIA_DRL,nid[n],U()))
    # ---------------- ground zone
    import pour as PR
    e=PR.EDGE_CU
    zp=[(e,e),(D.BW-e,e),(D.BW-e,D.BH-e),(e,D.BH-e)]
    for lay in ('F.Cu','B.Cu'):
        o.append('  (zone (net %d) (net_name "GND") (layers "%s") (uuid "%s") (name "GND-%s")'
                 %(nid['GND'], lay, U(), lay.replace('.','')))
        o.append('    (hatch edge 0.5)')
        o.append('    (connect_pads (clearance %s))'%PR.POUR_CLR)
        o.append('    (min_thickness %s) (filled_areas_thickness no)'%PR.MIN_W)
        o.append('    (fill yes (thermal_gap %s) (thermal_bridge_width %s) '
                 '(island_removal_mode 0))'
                 %(PR.TGAP, PR.SPOKE))
        o.append('    (polygon (pts %s))'%' '.join('(xy %s %s)'%(KX(a),KY(b)) for (a,b) in zp))
        o.append('  )')
    o.append(')')
    open(path,'w').write('\n'.join(o)+'\n')
    print('wrote', path, os.path.getsize(path), 'bytes;', len(tracks),'segments,',len(vias),'vias')

def write_library(outdir):
    """Emit a real .pretty library so KiCad can resolve every footprint."""
    import collections
    lib=os.path.join(outdir,'packetlogger.pretty')
    os.makedirs(lib,exist_ok=True)
    groups=collections.OrderedDict()
    for p in D.pads: groups.setdefault(p['ref'],[]).append(p)
    n=0
    for ref,pl in groups.items():
        cx=sum(q['x'] for q in pl)/len(pl); cy=sum(q['y'] for q in pl)/len(pl)
        o=['(footprint "%s"'%ref,
           '  (version 20221018)',
           '  (generator "packet-logger-carrier")',
           '  (layer "F.Cu")',
           '  (descr "%s")'%VALUE.get(ref,ref),
           '  (attr through_hole)',
           '  (fp_text reference "REF**" (at 0 -4.2) (layer "F.Fab") (uuid "%s")'%U(),
           '    (effects (font (size 0.8 0.8) (thickness 0.12))))',
           '  (fp_text value "%s" (at 0 4.2) (layer "F.Fab") hide (uuid "%s")'%(VALUE.get(ref,ref),U()),
           '    (effects (font (size 0.8 0.8) (thickness 0.12))))']
        for q in pl:
            dx=round(q['x']-cx,4); dy=round(-(q['y']-cy),4)
            shp=q['shape']
            drill=('(drill oval %s %s)'%q['dslot']) if q['dslot'] else ('(drill %s)'%q['drill'])
            o.append('  (pad "%s" thru_hole %s (at %s %s) (size %s %s) %s '
                     '(layers "*.Cu" "*.Mask") (uuid "%s"))'
                     %(q['pin'],shp,dx,dy,q['w'],q['h'],drill,U()))
        o.append(')')
        open(os.path.join(lib,'%s.kicad_mod'%ref),'w').write('\n'.join(o)+'\n')
        n+=1
    # mounting hole footprint
    o=['(footprint "MountingHole")','  (version 20221018)',
       '  (generator "packet-logger-carrier")','  (layer "F.Cu")',
       '  (descr "M3 clearance hole, non-plated")',
       '  (attr exclude_from_pos_files exclude_from_bom)',
       '  (fp_text reference "REF**" (at 0 -2.6) (layer "F.Fab") (uuid "%s")'%U(),
       '    (effects (font (size 0.7 0.7) (thickness 0.1))))',
       '  (fp_text value "M3" (at 0 2.6) (layer "F.Fab") hide (uuid "%s")'%U(),
       '    (effects (font (size 0.7 0.7) (thickness 0.1))))',
       '  (pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) '
       '(layers "F&B.Cu" "*.Mask") (uuid "%s"))'%U(),
       ')']
    open(os.path.join(lib,'MountingHole.kicad_mod'),'w').write('\n'.join(o)+'\n')
    n+=1
    open(os.path.join(outdir,'fp-lib-table'),'w').write(
        '(fp_lib_table\n  (version 7)\n'
        '  (lib (name "packetlogger")(type "KiCad")'
        '(uri "${KIPRJMOD}/packetlogger.pretty")(options "")'
        '(descr "Packet Logger carrier footprints"))\n)\n')
    print('wrote %s (%d footprints) + fp-lib-table'%(lib,n))

def write_pro(path):
    pro={"board":{"design_settings":{"defaults":{},
          "rules":{"min_clearance":0.25,"min_track_width":0.15,
                   "min_through_hole_diameter":0.3,"min_hole_to_hole":0.45,
                   "min_via_annular_width":0.13}},
          "layer_presets":[],"viewports":[]},
         "boards":[],"cvpcb":{"equivalence_files":[]},
         "libraries":{"pinned_footprint_libs":[],"pinned_symbol_libs":[]},
         "meta":{"filename":os.path.basename(path),"version":1},
         "net_settings":{"classes":[{"bus_width":12,"clearance":0.30,
            "diff_pair_gap":0.25,"diff_pair_width":0.2,"line_style":0,
            "microvia_diameter":0.3,"microvia_drill":0.1,"name":"Default",
            "pcb_color":"rgba(0,0,0,0.000)","schematic_color":"rgba(0,0,0,0.000)",
            "track_width":0.25,"via_diameter":0.8,"via_drill":0.4,
            "wire_width":6}],"meta":{"version":3},"net_colors":None},
         "pcbnew":{"last_paths":{},"page_layout_descr_file":""},
         "sheets":[],"text_variables":{}}
    open(path,'w').write(json.dumps(pro,indent=2))
    print('wrote', path)

if __name__=='__main__':
    os.makedirs('out',exist_ok=True)
    write('out/packet-logger-carrier.kicad_pcb')
    write_pro('out/packet-logger-carrier.kicad_pro')
    write_library('out')
