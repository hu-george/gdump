import re
import time
import traceback

import glib
import serial
from serial.tools import list_ports
import logging

logger = logging.getLogger(__name__)    # logger for inner thread message


class gCom:
    ''' serial operation for read/write
    '''
    def __init__(self):
        self.ser = serial.Serial()
        self.lst = []

    def detect(self):
        # detect the serial list plug in this computer
        # return list: of serial device name
        olst = list_ports.comports()
        if olst is not None:
            self.lst = [x.name for x in olst]
        self.lst = sorted(self.lst)
        return self.lst

    def set(self, vname='com1', vbaud=921600, vto=1):
        self.ser.port       = vname
        self.ser.baudrate   = vbaud
        self.ser.timeout    = vto
        logger.info('port:<{}> baud:<{}> to:<{}>'.format(self.ser.port, self.ser.baudrate, self.ser.timeout))

    def open(self):
        try:
            if self.ser.is_open:
                self.ser.close()
            self.ser.open()
            self.ser.reset_input_buffer()   # flush input buffer
            self.ser.reset_output_buffer()  # flush output buffer
            #self.ser.write(b'')
        except serial.SerialException:
            logger.error('ERROR: open <{}> failed'.format(self.ser.port))
        return self.ser.is_open

    def close(self):
        try:
            if self.ser.is_open:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                self.ser.close()
        except serial.SerialException:
            logger.error('ERROR: close <{}> failed'.format(self.ser.port))
        return self.ser.is_open

    def send(self, vstr):
        vstr += '\r\n'
        self.ser.write(vstr.encode())

    def readlines(self, maxt=1):
        # check com.rx_buffer per 0.01s, return when:
        # 1. already read out something and rx_buffer keep empty 0.01s
        # 2. read out nothing and maxt timeout
        tim0 = time.time()
        dtim = 0
        if True:
            bstr = b''
            rnum = self.ser.in_waiting
            k = 0
            # rnum > 0: com.rx_buffer is not empty
            # not bstr: received_buff is empty
            # dtim < maxt: this function not timeout
            while (rnum > 0) or (not bstr and (dtim < float(maxt))):
                if rnum:
                    rstr = self.ser.read(rnum)
                    bstr += rstr
                    logger.debug('readlines {}-{}: <{}>'.format(k, rnum, rstr.decode()))
                time.sleep(0.01)
                rnum = self.ser.in_waiting
                k += 1
                dtim = time.time() - tim0
            mstr = bstr.decode()
        else:
            blst = self.ser.readlines()
            slst = [x.decode() for x in blst]
            mstr = ''.join(slst)
            logger.debug('readlines: <{}>'.format(mstr))
        return mstr

    def recv(self, vstr='', maxt=3):
        # receive until [vstr] or only current recv-buffer
        # <readlines> not always end with \n: rx-ongoing when timeout
        tim0 = time.time()
        dtim = 0
        mstr = self.readlines()
        while((vstr not in mstr) and (dtim < float(maxt))):
            mstr += self.readlines()
            dtim = time.time() - tim0
        return mstr

    def write(self, addr, data):
        # write serial device: addr = data
        if type(addr) is str:
            addr = glib.str2int(addr, 10)
        if type(data) is str:
            data = glib.str2int(data, 10)
        assert type(addr) is int
        assert type(data) is int
        mstr = 'w {:x} {:x}'.format(addr, data)
        # write serial device
        if not self.ser.is_open:
            return False
        try:
            self.send(mstr)
            # wait [write] done
            #. rstr = self.wait('[0x{:08x}] = 0x'.format(addr)) # boot/aic diff
            rstr = self.wait(' = 0x{:08x}'.format(data), 3) # boot/aic diff
            logger.info('gcom.write: {}, {}'.format(mstr, 'ok' if rstr is not None else 'fail'))
            return rstr is not None
        except Exception as err:
            #. traceback.print_exc()
            logger.warning('Exception in gcom.write: {}'.format(repr(err), exc_info=True))
            return False

    def read(self, addr):
        if type(addr) is str:
            addr = glib.str2int(addr, 10)
        assert type(addr) is int
        mstr = 'r {:x}'.format(addr)
        # read serial device
        if not self.ser.is_open:
            return None
        try:
            self.send(mstr)
            # wait [read] done
            rstr = self.wait('[0x{:08x}] = 0x'.format(addr))
            if rstr is None:
                rstr = ''
            mch_obj = re.search(r' = 0x([a-f0-9]{8})', rstr)
            if (mch_obj is None) or (mch_obj.group(1) is None):
                logger.info('gcom.read: {} = {}'.format(mstr, 'fail'))
                return None
            else:
                logger.info('gcom.read: {} = {}'.format(mstr, mch_obj.group(1)))
                return int(mch_obj.group(1), 16)
        except Exception as err:
            #. traceback.print_exc()
            logger.warning('Exception in gcom.read: {}'.format(repr(err), exc_info=True))
            return None

    def wait(self, vstr='', vnum=10):
        # read serial line until:
        #  get @vstr or read @vnum times
        logger.debug('wait <{}> for <{}> times'.format(vstr, vnum))
        if not self.ser.is_open:
            return None
        try:
            mstr = ''
            for k in range(vnum):
                mstr += self.recv()
                if vstr in mstr.lower():
                    return mstr.lower()
            else:
                return None
            #n = 1
            #for k in range(100):
            #    mline = self.ser.readline().decode().lower().strip()
            #    logger.info('{}: {}'.format(k, mline))
            #    if n > vnum:
            #        break
            #    elif vstr in mline:
            #        mstr = mline
            #        break
            #    elif len(mline) < 2:
            #        n += 1
            #return mstr
        except Exception as err:
            #. traceback.print_exc()
            logger.warning('Exception in gcom.wait: {}'.format(repr(err), exc_info=True))
            return None


if __name__ == '__main__':
    mcom = gCom()
    mlst = mcom.detect()
    print(mlst)
    mcom.set(mlst[0])
    mcom.open()
    mcom.write(0x10000, 0xffffffff)
    print(format(mcom.read(0x10000), '08x'))
    mcom.write(0x10000, 0x00000000)
    print(format(mcom.read(0x10000), '08x'))
