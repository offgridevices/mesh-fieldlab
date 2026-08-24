# -*- coding: utf-8 -*-
import sys, time
import design as D
import router as R

WIDTH = {'BAT+':D.TW_BAT, 'BAT_SW':D.TW_BAT, 'RAW_3V3':D.TW_PWR, '+3V3':D.TW_PWR}
ORDER = ['BAT+','BAT_SW','RAW_3V3','+3V3',
         'RAK_TX0','RAK_RX0',
         'SD_CLK','SD_MISO','SD_MOSI','SD_CS',
         'OLED_SCL','OLED_SDA','BTN',
         'XIAO_D2','XIAO_D1','XIAO_5V',
         'RAK_BOOT','RAK_SCL','RAK_SDA']

def run():
    rt = R.Router()
    allnets = sorted({p['net'] for p in D.pads if p['net']})
    todo = [n for n in ORDER if n in allnets]
    missing = [n for n in allnets if n not in todo and n!='GND']
    if missing: print('!! not in ORDER:', missing)
    fails=[]
    for n in todo:
        t0=time.time()
        w = WIDTH.get(n, D.TW_SIG)
        ok,nv = rt.route_net(n, w)
        print('%-10s %-5s vias=%d  %.1fs  %s' % (n, 'OK' if ok else 'FAIL', nv,
                                                 time.time()-t0, ''))
        if not ok: fails.append(n)
    print('tracks=%d vias=%d fails=%s' % (len(rt.tracks), len(rt.vias), fails))
    return rt, fails

if __name__=='__main__':
    rt, fails = run()
    import pickle
    pickle.dump({'tracks':rt.tracks,'vias':rt.vias}, open('routed.pkl','wb'))
    sys.exit(1 if fails else 0)
