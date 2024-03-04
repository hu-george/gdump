from PyQt5 import QtWidgets, QtGui
from PyQt5.QtCore import Qt
import ctypes
import inspect
from threading import Thread, Event
import re
import random
import logging
import time
import os

from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt

import gcom
import gdump

logger = logging.getLogger(__name__)

class gDumpUi(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        ## signals
        self.conn   = False
        self.com    = gcom.gCom()
        self.dut    = gdump.gDump(self.com)
        self.thd    = None
        self.fig    = None  # first assigned in slot_figon
        self.ax     = None  # last  assigned in slot_figon
        self.enext  = Event()

        ## UI uart
        self.uart_dtct = QtWidgets.QPushButton('Detect')
        self.uart_conn = QtWidgets.QPushButton('Connect')
        self.uart_list = QtWidgets.QComboBox()
        self.uart_list.setPlaceholderText('COM')
        self.uart_baud = QtWidgets.QLineEdit('921600')

        ## UI control
        self.lb0    = QtWidgets.QLabel('chidx')
        self.lb1    = QtWidgets.QLabel('Gidx')
        self.lb2    = QtWidgets.QLabel('Nrep')
        self.lb3    = QtWidgets.QLabel('Nmax')
        self.chidx  = QtWidgets.QLineEdit('0:4')
        self.Gidx   = QtWidgets.QLineEdit('2')
        self.hldon  = QtWidgets.QCheckBox('rx_hldon')
        self.figon  = QtWidgets.QCheckBox('figure')
        self.Nmax   = QtWidgets.QLineEdit('10')
        self.Nrep   = QtWidgets.QLineEdit('1')
        self.start      = QtWidgets.QPushButton('Start')
        self.next       = QtWidgets.QPushButton('Next')
        self.memsize    = QtWidgets.QComboBox()
        self.memsize.addItems(['mem=16k', 'mem=32k', 'mem=48k', 'mem=64k'])
        self.memsize.setCurrentIndex(1)

        self.k_proj = 0         # default proj
        self.k_dump = [0, 2]    # proj's default dump_sel
        self.proj_lst = list(self.dut.dumps.keys())
        x = self.dut.dumps[self.proj_lst[self.k_proj]]
        dump_lst = [y[0] for y in x]
        self.proj   = QtWidgets.QComboBox()
        self.proj.addItems(self.proj_lst)
        self.proj.setCurrentIndex(self.k_proj)
        self.dump   = QtWidgets.QComboBox()
        self.dump.addItems(dump_lst)
        self.dump.setCurrentIndex(self.k_dump[0])
        self.bits   = QtWidgets.QLineEdit(x[self.k_dump[0]][1])

        self.sv_txt  = QtWidgets.QCheckBox('RAW')
        self.sv_int  = QtWidgets.QCheckBox('DAT')
        self.sv_cpx  = QtWidgets.QCheckBox('CPX')
        self.state  = QtWidgets.QLineEdit('idle')
        self.state.setReadOnly(True)

        ## UI result
        self.result = QtWidgets.QTextBrowser()

        self.init_layout()
        self.init_action()

    def init_layout(self):
        self.lay0 = QtWidgets.QVBoxLayout()
        self.lay0.addWidget(self.uart_dtct)
        self.lay0.addWidget(self.uart_list)
        self.lay0.addWidget(self.uart_baud)
        self.lay0.addWidget(self.uart_conn)

        self.lay1 = QtWidgets.QGridLayout()
        self.lay1.addWidget(self.lb0        , 0, 0, Qt.AlignRight)
        self.lay1.addWidget(self.chidx      , 0, 1)
        self.lay1.addWidget(self.lb1        , 1, 0, Qt.AlignRight)
        self.lay1.addWidget(self.Gidx       , 1, 1)
        self.lay1.addWidget(self.lb2        , 2, 0, Qt.AlignRight)
        self.lay1.addWidget(self.Nrep       , 2, 1)
        self.lay1.addWidget(self.lb3        , 3, 0, Qt.AlignRight)
        self.lay1.addWidget(self.Nmax       , 3, 1)

        self.lay2 = QtWidgets.QVBoxLayout()
        self.lay2.addWidget(self.proj)
        self.lay2.addWidget(self.memsize)
        self.lay2.addWidget(self.dump)
        self.lay2.addWidget(self.bits)

        self.lay4 = QtWidgets.QVBoxLayout()
        self.lay4.addWidget(self.hldon)
        self.lay4.addWidget(self.figon)
        self.lay4.addWidget(self.next)
        self.lay4.addWidget(self.start)

        self.lay5 = QtWidgets.QHBoxLayout()
        self.lay5.addWidget(self.sv_txt)
        self.lay5.addWidget(self.sv_int)
        self.lay5.addWidget(self.sv_cpx)
        self.lay5.addWidget(self.state)

        self.lay6 = QtWidgets.QHBoxLayout()
        self.lay6.addLayout(self.lay0, 1)
        self.lay6.addLayout(self.lay1, 1)
        self.lay6.addLayout(self.lay2, 2)
        #self.lay6.addStretch(2)
        self.lay6.addLayout(self.lay4, 1)

        self.parm_lay = QtWidgets.QVBoxLayout()
        self.parm_lay.addLayout(self.lay6, 0)
        self.parm_lay.addLayout(self.lay5, 0)
        self.parm_lay.addWidget(self.result, 1)

        self.glbl_lay = QtWidgets.QGridLayout()
        self.fig_lay  = QtWidgets.QVBoxLayout()
        #self.space0 = QtWidgets.QSpacerItem(20, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.glbl_lay.addLayout(self.parm_lay, 0, 0, -1, 1)
        self.glbl_lay.addLayout(self.fig_lay , 0, 1, -1, -1)
        #self.glbl_lay.addItem  (self.space0   , 1, 0, -1, 1)
        self.glbl_lay.setColumnStretch(0, 1)
        self.glbl_lay.setColumnStretch(1, 8)
        self.setLayout(self.glbl_lay)

    def init_plot(self):
        try:
            self.fig = plt.figure()
            self.canvas = FigureCanvas(self.fig)
            self.toolbar = NavigationToolbar(self.canvas, self)
            self.fig_lay.addWidget(self.toolbar)
            self.fig_lay.addWidget(self.canvas )
            self.fig.clear()
            self.ax = self.fig.add_subplot(111)
            self.canvas.draw()
        except Exception as err:
            print('Exception in gdump_ui.init_plot: {}'.format(repr(err), exc_info=True))
            return False

    def init_action(self):
        self.uart_dtct.clicked.connect(self.slot_uart_detect)
        self.uart_conn.clicked.connect(self.slot_uart_connect)
        self.start.clicked.connect(self.slot_start)
        self.figon.stateChanged.connect(self.slot_figon)
        self.next.clicked.connect(self.slot_next)
        self.proj.currentIndexChanged.connect(self.slot_proj_chg)
        self.dump.currentIndexChanged.connect(self.slot_dump_chg)

    def slot_uart_detect(self):
        logger.info('slot_uart_detect')
        mlst = self.com.detect()
        if mlst is not None:
            self.uart_list.clear()
            self.uart_list.addItems(mlst)
            self.uart_list.setCurrentIndex(0)

    def slot_uart_connect(self):
        logger.info('slot_uart_connect')
        if self.conn:
            self.set_uart_conn(self.com.close())
        else:
            com_name = self.uart_list.currentText()
            com_baud = int(self.uart_baud.text())
            self.com.set(com_name, com_baud)
            self.set_uart_conn(self.com.open())

    def set_uart_conn(self, ok):
        if ok:
            self.conn = True
            logger.info('slot_uart_connect success')
            self.uart_conn.setStyleSheet('QPushButton:!hover { font: normal; color: black; background-color: #00c500 }')
            self.uart_conn.setText('Connected')
        else:
            self.conn = False
            logger.info('slot_uart_connect failed')
            self.uart_conn.setStyleSheet('QPushButton:!hover { font: italic; color: black; background-color: gray }')
            self.uart_conn.setText('Connect')

    def slot_start(self):
        logger.info('slot_start')
        if 'start' in self.start.text().lower():
            self.start.setText('STOP')
            self.start.setStyleSheet('QPushButton:!hover  { font: normal; color: black; background-color: #f08000 }')
            self.thd = Thread(target=gDumpUi.run, args=(self, ))
            self.thd.setDaemon(True)
            self.thd.start()
        elif 'stop' in self.start.text().lower():
            self.start.setText('START')
            self.start.setStyleSheet('QPushButton:!hover  { font: normal; color: black; background-color: #00f080 }')
            if self.thd.is_alive():
                self._async_raise(self.thd.ident, SystemExit)

    def slot_figon(self):
        logger.info('slot_figon, check = {}'.format(self.figon.isChecked()))
        if self.figon.isChecked():
            if self.fig is not None:
                self.toolbar.show()
                self.canvas.show()
            else:
                self.init_plot()
        else:
            if self.fig is not None:
                self.toolbar.hide()
                self.canvas.hide()

    def slot_next(self):
        self.state.clear()
        self.enext.set()

    def slot_proj_chg(self):
        k = self.proj.currentIndex()
        n = self.k_dump[k]
        x = self.dut.dumps[self.proj_lst[k]]
        dump_lst = [y[0] for y in x]
        self.dump.clear()
        self.dump.addItems(dump_lst)
        self.dump.setCurrentIndex(n)
        self.bits.setText(x[n][1])

    def slot_dump_chg(self):
        n  = self.dump.currentIndex()
        x = self.dut.dumps[self.proj.currentText()]
        self.bits.setText(x[n][1])

    def _async_raise(self, tid, exctype):
        tid = ctypes.c_long(tid)
        if not inspect.isclass(exctype):
            exctype = type(exctype)
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, ctypes.py_object(exctype))
        if res == 0:
            raise ValueError('invalid thread id')
        elif res != 1:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)
            raise SystemError('PyThreadState_SetAsyncExc failed')

    def parse_channel(self):
        # parse channel index
        maxn    = int(self.Nmax.text())
        mlst    = []
        mstr = self.chidx.text()
        try:
            if 'rand' in mstr.lower():
                mlst = [random.randint(0, 78) for k in range(maxn)]
            else:
                mobj = re.findall(r'[+-]?(\d+)', mstr)
                mval = [int(x) for x in mobj]
                if len(mval) == 1:
                    mlst = [mval[0]]
                elif len(mval) == 2:
                    mlst = list(range(mval[0], mval[1]+1))
                elif len(mval) >= 3:
                    mlst = list(range(mval[0], mval[1]+mval[2], mval[2]))

            logger.info('chidx: {}'.format(mlst))
            return mlst
        except Exception as err:
            print('Exception in gdump_ui.save_parm: {}'.format(repr(err), exc_info=True))
            return []

    def run(self):
        self.cnt = 0
        try:
            gidx = int(self.Gidx.text())
            repn = int(self.Nrep.text())
            clst = self.parse_channel()
            msel = [16, 32, 48, 64]
            msiz = msel[self.memsize.currentIndex()]
            if len(clst) < 1:   self.state.setText('ERROR: channel null')
            if repn < 1:        self.state.setText('ERROR: Nrep < 1')
            if gidx > 3:        self.state.setText('ERROR: Gidx > 3')
            if not self.conn:   self.state.setText('ERROR: com not connected')
            if (len(clst) < 1) or (repn < 1) or (gidx > 3) or (not self.conn):
                return

            mdir = os.path.join('dump', time.strftime('%Y%m%d_%H%M%S'))
            if self.sv_txt.isChecked() or self.sv_int.isChecked() or self.sv_cpx.isChecked():
                if os.path.exists(mdir):
                    logger.error('{} already exist'.format(mdir))
                else:
                    os.makedirs(mdir)

            self.dut.set_rx(rx='off')
            for chidx in clst:
                self.dut.set_rx(rx='off')
                for k in range(repn):
                    self.cnt += 1
                    for n in range(1):
                        logger.info('run: chidx = {}, gidx = {}'.format(chidx, gidx))
                        mfile = os.path.join(mdir, time.strftime('%Y%m%d_%H%M%S'))
                        if not self.dut.set_rx(chidx, gidx): continue
                        self.state.setText('rxon ok')
                        logger.info('run: rxon ok')
                        (addr, data) = self.dut.dump(self.proj.currentText(), self.dump.currentText(), vsize=msiz)
                        if data is None: continue
                        self.state.setText('dump end = {}'.format(addr))
                        logger.info('run: dump end_addr = {}, data_len = {}'.format(addr, len(data)))
                        if self.sv_txt.isChecked():
                            with open(mfile+'_txt.dat', 'w') as fw:
                                fw.writelines('end_addr = {}'.format(addr))
                                fw.write(data)
                        xseq = self.dut.pre_proc(addr, data)
                        if self.sv_int.isChecked():
                            with open(mfile+'_int.dat', 'w') as fw:
                                sw = [str(x) for x in xseq]
                                fw.write('\n'.join(sw))
                                #for x in xseq:
                                #    fw.writelines('{:d}\n'.format(x))
                        self.state.setText('dump end = {}, num = {}'.format(addr, len(xseq)))
                        if xseq is None: continue
                        x0 = self.dut.pst_proc(xseq, self.bits.text())
                        if self.sv_cpx.isChecked():
                            with open(mfile+'_cpx.dat', 'w') as fw:
                                sw = ['{:f} {:f}'.format(x.real, x.imag) for x in x0]
                                fw.write('\n'.join(sw))
                                #for x in x0:
                                #    fw.writelines('{:f}  {:f}\n'.format(x.real, x.imag))
                        if self.figon.isChecked() and (self.ax is not None):
                            psig, pdc, pton = self.dut.dcnf(x0, self.ax)
                            self.canvas.draw()
                        else:
                            psig, pdc, pton = self.dut.dcnf(x0, None)
                        mstr = '[{}] {}-{}: sig = {:.1f}, dc = {:.1f}'.format(self.cnt, 2402+chidx, gidx, psig, pdc)
                        if pton is not None:
                            mstr += ', tone = {:.1f}'.format(pton)
                        logger.info('result> ' + mstr)
                        self.add_result(mstr)
                        break
                    else:
                        logger.error('run: the same param failed 10 times, exit')
                        return -1
                    if not self.hldon.isChecked():
                        self.dut.set_rx(rx='off')
                    if self.figon.isChecked():
                        self.state.setText('Click Next to run-next')
                        self.enext.wait()
                        self.enext.clear()
            self.slot_start()
        except Exception as err:
            print('Exception in gdump_ui.run: {}'.format(repr(err), exc_info=True))
            self.state.setText('Error in run, stopped')
            return False

    def add_result(self, msg=''):
        try:
            vsb = self.result.verticalScrollBar()
            vsb_cur = vsb.sliderPosition()
            vsb_max = vsb.maximum()
            self.result.append(msg)
            if (vsb_cur > vsb_max - 10) and (vsb_max != 0):
                vsb.setSliderPosition(vsb.maximum())
        except Exception as err:
            logger.exception('Exception in add_result()', exc_info=True)
