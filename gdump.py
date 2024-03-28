import math
import re
import time
import numpy as np
from scipy import signal
import matplotlib.pyplot as plt

import glib
import gcom
import glogging
import logging

logger = logging.getLogger(__name__)

class gDump():
    def __init__(self, vcom):
        super().__init__()
        self.com = vcom
        dump_8820 = \
            (('sdmadc', '31:28, 15:12'),
             ('saradc', '31:20, 15:4'),
             ('saradc_btrf', ''),
             ('agc_din', '31:18, 15:2'),
             ('rxdfe_pre_odat', '31:18, 15:2'),
             ('rxdfe_pst_idat', '31:18, 15:2'),
             ('dac_150', '31:20, 15:4'),
             ('txdfe_52m', '31:17, 15:1'),
             ('gdb', ''))
        dump_8822 = \
            (('saradc', '31:20, 15:4'),
             ('saradc_btrf', ''),
             ('agc_din', '31:18, 15:2'),
             ('rxdfe_pre_odat', '31:18, 15:2'),
             ('rxdfe_pst_idat', '31:18, 15:2'),
             ('dac_150', '31:20, 15:4'),
             ('txdfe_52m', '31:17, 15:1'),
             ('gdb', ''))
        self.dumps = {'aic8820': dump_8820,
                      'aic8822': dump_8822}
        self.dlen = 0

    def send(self, str):
        return self.com.send(str)

    def recv(self, vstr='', maxt=5):
        return self.com.recv(vstr, maxt)

    def write(self, addr, data):
        return self.com.write(addr, data)

    def read(self, addr):
        return self.com.read(addr)

    def mskset(self, addr, mask, data):
        vold = self.read(addr)
        if vold:
            vnew = (vold & ~mask) | (data & mask)
            return self.write(addr, vnew)
        else:
            return vold
    def set_rx(self, vprj='aic8820', chidx=0, gidx=3, rx='on'):
        if '8820' in vprj:
            return self.set_rx_8820(chidx, gidx, rx)
        else:
            return self.set_rx_8822(chidx, gidx, rx)

    def set_rx_8820(self, chidx=0, gidx=3, rx='on'):
        if 'of' in rx.lower():
            self.mskset(0x40620020, 3, 0)
            return True
        else:
            # fix rx pwr
            self.mskset(0x40620508, 0xf1, (int(gidx)<<4)|1)
            self.mskset(0x40620000, 0x0c, 0x08)    # dm_sync_fix
            # fix channel
            val = self.read(0x40620020)
            val = val & ~(0x7f<<16) | (int(chidx)<<16)
            self.write(0x40620020, val)
            val = val & ~(0x01<<23) | (1<<23)
            self.write(0x40620020, val)
            # fix rxon
            val = val & ~0x0e | 0x0a
            self.write(0x40620020, val)
            val = val & ~0x0f | 0x0b
            self.write(0x40620020, val)
            # dpll lock & mdm rxon
            time.sleep(1e-3)
            if not ((self.read(0x406208a8) >> 23) & 1):
                logger.error('set_rx: dpll not lock')
                return False
            if not ((self.read(0x406218b4) >> 22) & 1):
                logger.error('set_rx: mdm not rxon')
                return False
            return True

    def set_rx_8822(self, chidx=0, gidx=3, rx='on'):
        if 'of' in rx.lower():
            self.mskset(0x40620020, 3, 0)
            return True
        else:
            # fix rx pwr
            self.mskset(0x40620508, 0xf1, (int(gidx)<<4)|1)
            self.mskset(0x40620000, 0x0c, 0x08)    # dm_sync_fix
            # fix channel
            val = self.read(0x40620020)
            val = val & ~(0x7f<<16) | (int(chidx)<<16)
            self.write(0x40620020, val)
            val = val & ~(0x01<<23) | (1<<23)
            self.write(0x40620020, val)
            # fix rxon
            val = val & ~0x0e | 0x0a
            self.write(0x40620020, val)
            val = val & ~0x0f | 0x0b
            self.write(0x40620020, val)
            #  pll lock & mdm rxon
            time.sleep(1e-3)
            #if not ((self.read(0x406208a0) >> 29) & 1):
            if not ((self.read(0x4062203c) >> 12) & 1):
                logger.error('set_rx:  pll not lock')
                return False
            if not ((self.read(0x406218b4) >> 22) & 1):
                logger.error('set_rx: mdm not rxon')
                return False
            return True

    def dump(self, vprj='aic8820', vsel='', vsize=32, vstop='man'):
        if '8820' in vprj:
            return self.dump_8820(vsel, vsize, vstop)
        else:
            return self.dump_8822(vsel, vsize, vstop)

    def dump_8820(self, vsel='sdmadc', vsize=32, vstop='man'):
        """ @vsel  sdmadc, saradc, saradc_btrf, rxdfe_pre_odat
            @vsize '16'/'32'/'48'/'64' [kw]
            @vstop 'man'/'crce'
            # agc_din = cic_dno: w 40620510 1466ff0a, fix agc/dgc gain
        """
        clksel = {'rxdfe_pst_2x' : 0b00000, # 64m
                  'rxdfe_pst_1x' : 0b00001, # 32m
                  'rxdfe_pre_adc': 0b00100,
                  'rxdfe_pre_2x' : 0b00110,
                  'txdfe_pre_52m': 0b10000,
                  'txdfe_pst_150': 0b11000}
        ramen  = {16: 0b0001,
                  32: 0b0011,
                  48: 0b0111,
                  64: 0b1111}
        dumpsz = {16: 0b01,
                  32: 0b00,
                  48: 0b11,
                  64: 0b10}
        stopdly = 4
        #                           datasel clksel                  ratesel
        dumpsel ={'saradc'          : (0x4, clksel['rxdfe_pre_adc'], 0),
                  'sdmadc'          : (0x5, clksel['rxdfe_pre_adc'], 0),
                  'rxdfe_pst_idat'  : (0x6, clksel['rxdfe_pst_1x' ], 0),
                  'rxdfe_pre_odat'  : (0x7, clksel['rxdfe_pre_2x' ], 1),
                  'agc_din'         : (0xc, clksel['rxdfe_pre_2x' ], 1),
                  'gdb'             : (0x2, clksel['rxdfe_pre_2x' ], 1),
                  'saradc_btrf'     : (0x2, clksel['rxdfe_pre_adc'], 1),
                  'dac_150'         : (0xa, clksel['txdfe_pst_150'], 0),
                  'txdfe_32m'       : (0xb, clksel['rxdfe_pst_1x' ], 0),
                  'txdfe_52m'       : (0x9, clksel['txdfe_pre_52m'], 0)}
        stopsel = {'crce': 4,
                   'man' : 7,
                   'auto': 2,   # rxon pos
                   'rxon': 0,   # rxon neg
                   'txon': 1}   # txon neg

        #mdict = {0: 'sdmadc',
        #         1: 'saradc',
        #         2: 'saradc_btrf',
        #         3: 'agc_din',
        #         4: 'rxdfe_pre_odat',
        #         5: 'rxdfe_pst_idat',
        #         6: 'dac_150',
        #         7: 'txdfe_52m',
        #         9: 'gdb'}
        #mode = mdict[int(vsel)]

        if vstop == 'man':
            # dump start/stop same time, stopdly control
            stopdly = int(math.floor(vsize*1024/80)-4)

        data = dumpsel[vsel]
        r0814 = (data[1]        <<12) | \
                (ramen[vsize]   << 8) | \
                (data[2]        << 6) | \
                (             1 << 1)
        r0810 = (data[0]        <<16) | \
                (dumpsz[vsize]  <<10) | \
                (stopdly            )
        stop0 =               7 <<20
        stop1 = stopsel[vstop]  <<20

        self.write(0x40620814, 0x0000)
        self.write(0x40100034, 1)               # dump_sel:bt
        self.write(0x40620814, r0814)
        self.write(0x40620810, r0810|stop1)     # stop=man, free run
        self.write(0x40620814, r0814|9)         # dumpen = 1, stopreg=1
        while(self.read(0x40620880)>>31):       # wait dump done
            time.sleep(0.001)
        # write(0x40620810, r0810|stop0)     # stop=man, free run
        # write(0x40620814, r0814|1)         # dumpen = 1
        # time.sleep(0.01)                    # wait dumping
        # write(0x40620810, r0810|stop1)     # stop=set
        # time.sleep(0.01)
        # write(0x40620814, r0814|9)         # man_stop = 1
        # time.sleep(0.01)
        self.write(0x40620814, r0814&0xfff0f2)  # ramen = 0, dumpen = 0
        addr = self.read(0x40620880)            # end addr
        self.write(0x40620814, 0x0000)
        if addr != 0x80000000:
            rcnt = vsize*1024
            logger.info('dump success, rcnt = {}'.format(rcnt))
            self.send('r 00100000 {0}'.format(rcnt))
            rend = '{:08X}'.format(int('100000', 16) + rcnt*4 - 16)
            wait = rend[0:4] + '-' + rend[4:]
            logger.info('dump done, read data, wait {}'.format(wait))
            data = self.recv(wait)
        return addr, data

    def dump_8822(self, vsel='saradc', vsize=32, vstop='man'):
        """ @vsel  saradc, saradc_btrf, rxdfe_pre_odat
            @vsize '16'/'32'/'48'/'64' [kw]
            @vstop 'man'/'crce'
            # agc_din = cic_dno: w 40620510 1466ff0a, fix agc/dgc gain
        """
        clksel = {'rxdfe_pst_2x' : 0b00000, # 64m
                  'txmdm_32m'    : 0b00001, # 32m
                  'rxdfe_pre_adc': 0b00100,
                  'rxdfe_pre_2x' : 0b00110,
                  'txdfe_pre_52m': 0b10000,
                  'txdfe_pst_150': 0b11000}
        ramen  = {16: 0b0001,
                  32: 0b0011,
                  48: 0b0111,
                  64: 0b1111}
        dumpsz = {16: 0b01,
                  32: 0b00,
                  48: 0b11,
                  64: 0b10}
        stopdly = 4
        #                           datasel clksel                  ratesel
        dumpsel ={'saradc'          : (0x4, clksel['rxdfe_pre_adc'], 0),
                  'rxdfe_pst_idat'  : (0x6, clksel['rxdfe_pst_2x' ], 1),
                  'rxdfe_pre_odat'  : (0x7, clksel['rxdfe_pre_2x' ], 1),
                  'agc_din'         : (0xc, clksel['rxdfe_pre_2x' ], 1),
                  'gdb'             : (0x2, clksel['rxdfe_pre_2x' ], 1),
                  'saradc_btrf'     : (0x2, clksel['rxdfe_pre_adc'], 1),
                  'dac_150'         : (0xa, clksel['txdfe_pst_150'], 0),
                  'txdfe_32m'       : (0xb, clksel['rxdfe_pst_2x' ], 1),
                  'txdfe_52m'       : (0x9, clksel['txdfe_pre_52m'], 0)}
        stopsel = {'crce': 4,
                   'man' : 8,
                   'auto': 2,   # rxon pos
                   'rxon': 0,   # rxon neg
                   'txon': 1}   # txon neg

        #mdict = {1: 'saradc',
        #         2: 'saradc_btrf',
        #         3: 'agc_din',
        #         4: 'rxdfe_pre_odat',
        #         5: 'rxdfe_pst_idat',
        #         6: 'dac_150',
        #         7: 'txdfe_52m',
        #         9: 'gdb'}
        #mode = mdict[int(vsel)]

        #if vstop == 'man':
        #    # dump start/stop triggered at the same time, <stopdly> control actual stop time
        #    stopdly = int(math.floor(vsize*1024/80)-4)
        #    self.dlen = stopdly*80
        #else:
        #    self.dlen = 0
        stopdly = 1

        data = dumpsel[vsel]
        # aic8822: 0814[19] = clkinv
        clkinv= self.read(0x40620814) & 0xffff0000
        r0814 = (data[1]        <<12) | \
                (ramen[vsize]   << 8) | \
                (data[2]        << 6) | \
                (             1 << 1)
        r0810 = (data[0]        <<16) | \
                (dumpsz[vsize]  <<10) | \
                (stopdly            )
        stop0 =               7 <<20
        stop1 = stopsel[vstop]  <<20

        self.write(0x40620814, clkinv)
        self.write(0x40100034, 1)         # dump_sel:bt
        self.write(0x40620814, clkinv|r0814)
        self.write(0x40620810, r0810|stop1)    # stop=man, free run
        self.write(0x40620814, clkinv|r0814|1) # dumpen = 1
        time.sleep(0.01)
        self.write(0x40620814, clkinv|r0814|9) # stopreg= 1
        cnt = 0
        while((self.read(0x40620880)>>31) and (cnt < 10)):           # wait dump done
            time.sleep(0.01)
            cnt += 1
        if cnt >= 10:
            return None, None
        self.write(0x40620814, (clkinv|r0814)&0xfffff0f2)  # ramen = 0, dumpen = 0
        addr = self.read(0x40620880)            # end addr
        self.write(0x40620814, clkinv)
        if addr != 0x80000000:
            rcnt = vsize*1024
            logger.info('dump success, rcnt = {}'.format(rcnt))
            self.send('r 00100000 {0}'.format(rcnt))
            rend = '{:08X}'.format(int('100000', 16) + rcnt*4 - 16)
            wait = rend[0:4] + '-' + rend[4:]
            logger.info('dump done, read data, wait {}'.format(wait))
            data = self.recv(wait)
        return addr, data

    def pre_proc(self, addr, data):
        # i: gcom.read plain text
        # o: <int> array from dump_t0 to dump_end
        mcho = re.findall(r'(\w{4}-\w{4}): ((?:\s?\w{8}){4})', data)
        lsta = [(int(re.sub('-', '', x[0]), 16)-0x100000) for x in mcho]
        lstd = [x[1] for x in mcho]
        # test addr sequence
        if lsta == list(range(0, lsta[-1]+1, 16)):
            x0 = ' '.join(lstd)
            x1 = re.split(r'\s+', x0.strip())
            xseq = [int(x, 16) for x in x1]
            #if self.dlen > 0:
            #    if self.dlen <= addr:
            #        return list(xseq[(addr-self.dlen+1):addr])
            #    else:
            #        return list(xseq[(len(xseq)-(self.dlen-addr)+1)]) + list(xseq[0:addr])
            #elif len(xseq) >= addr:
            #    return xseq[0:addr]
            #else:
            #    logger.error('pre_proc: dump read data lt end_addr')
            #    return None
            if addr == len(xseq)-1:
                return xseq
            elif addr == len(xseq)-2:
                return list(xseq[addr+1]) + xseq[0:addr+1]
            else:
                return xseq[addr+1:] + xseq[0:addr+1]
        else:
            logger.error('pre_proc: dump read addr not continuous')
            return None

    def pst_proc(self, x0, fmt='31:17, 15:1'):
        # i: <int>   unsigned array dump data, fmt=i&q bit location
        # o: <complex> signed array, i&q extracted from data
        msb = re.findall(r'(\d+(?=:))' , fmt)
        lsb = re.findall(r'((?<=:)\d+)', fmt)

        if (msb is None) or (lsb is None) or (len(msb) != len(lsb)) or (len(msb) != 2):
            logger.error('ERROR 0: input i&q bit location {}'.format(fmt))

        msb = [int(x) for x in msb]
        lsb = [int(x) for x in lsb]

        if (msb[0] < lsb[0]) or (msb[1] < lsb[1]) or (msb[0]-lsb[0] != msb[1]-lsb[1]):
            logger.error('ERROR 1: input i&q bit location {}'.format(fmt))

        width = msb[0] - lsb[0] - 1
        max   = 2**width
        msk   = max - 1
        mid   = max / 2

        x0 = np.array(x0)
        xi = (x0 >> lsb[0]) & msk
        xq = (x0 >> lsb[1]) & msk
        ii = (xi >= mid)
        xi[ii] = xi[ii] - max
        ii = (xq >= mid)
        xq[ii] = xq[ii] - max
        x1 = (xi + 1j*xq)/(2**(width-1))
        return x1

    def dcnf(self, x0, fs=160, ax=None):
        N  = len(x0)
        fx, px = signal.periodogram(x0, fs, window='boxcar', detrend=False, nfft=N, scaling='spectrum', return_onesided=False)
        fx = np.fft.fftshift(fx)
        dc = px[0]
        px = np.fft.fftshift(np.squeeze(px))
        fi = 0.75
        bw = 1.0
        fl = fi-bw/2
        fh = fi+bw/2
        isig = (fx>fl) & (fx<fh)
        pt = np.copy(px)
        pt[(fx<fl)|(fx>fh)] = 1e-20
        pavg = 10*np.log10(np.mean(px[isig]))
        iton = 10*np.log10(pt) > pavg+10
        psig = 10*np.log10( np.sum(px[ isig & ~iton]) )
        if np.sum(iton):
            pton = 10*np.log10( np.sum(px[         iton]) )
        else:
            pton = None
        logger.info('signal = {:0.1f}[dbfs], dc = {:0.1f}[dbfs]'.format(psig, 10*np.log10(dc)))
        if np.sum(iton) > 0:
            logger.info('tone in sig_bw: {} = {}'.format(fx[iton], px[iton]))
        if ax is not None:
            logger.info('plot')
            ax.clear()
            ax.plot(fx, 10*np.log10(px), '.-', linewidth=1, markersize=5)
            ax.plot(fx[isig], 10*np.log10(px[isig]), 'r.-', lw=1, ms=5)
            if np.sum(iton) > 0:
                ax.plot(fx[iton], 10*np.log10(px[iton]), 'y*-', lw=1, ms=5)
            ax.set_xlim(-fs/2, +fs/2)
            ax.set_ylabel('power/dbfs')
            ax.set_xlabel('freq/mhz')
            ax.grid(True)
        return psig, 10*np.log10(dc), pton
        #plt.plot(fx, 10*np.log10(px), '.-')
        #plt.plot(fx[isig], 10*np.log10(px[isig]), 'r.-')
        #if np.sum(iton) > 0:
        #    plt.plot(fx[iton], 10*np.log10(px[iton]), 'b*')
        #plt.xlim(-fs/2, +fs/2)
        #plt.grid(True)
        #plt.show()

if __name__ == '__main__':
    glogging.log2file(logger, logging.INFO, bhv='clr', name='tmp.log')
    gcom.logger = logger

    com = gcom.gCom()
    dut = gDump(com)
    com.detect()
    com.set(com.lst[0], 921600, 0.1)
    com.open()
    print('com open success')
    dut.set_rx()
    print('set rx done')
    addr,data = dut.dump(vsize=16)
    xseq = dut.pre_proc(addr, data)
    if xseq is not None:
        x0 = dut.pst_proc(xseq)
        dut.dcnf(x0)
    else:
        xseq = [0,]
    print('addr = {:0x}, data len = {:0x}, data num {}'.format(int(addr), len(data), len(xseq)))
    with open('com.log', 'w') as fw:
        fw.write('dump end addr = {}\n'.format(addr))
        fw.write('dump read out:\n')
        fw.write(data + '\n')
        for k in xseq:
            fw.write('{:08x}\n'.format(k))
        #for k in mo:
        #    fw.write(k + '\n')
        fw.write('\n')
