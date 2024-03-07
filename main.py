import sys
from PyQt5 import QtWidgets, QtGui
import gicon
import base64
import logging
import glogging

import gdump_ui
import gdump
import gcom

logger = logging.getLogger(__name__)

try:
    # glogging.log2stdout(logger, logging.INFO)
    glogging.log2file(logger, logging.INFO)
    gdump_ui.logger = logger
    gdump.logger = logger
    gcom.logger = logger

    app = QtWidgets.QApplication(sys.argv)
    font = QtGui.QFont()
    font.setFamily('consolas')
    app.setFont(font)
    app.setStyleSheet('QPushButton:pressed { font: bold;   color: black; background-color: #ff4000 }')
    # app.setWindowIcon(QtGui.QIcon(os.path.join('.', 'gt.png')))  # need copy gt.png file to exe dir
    # with open(os.path.join(r'D:\download', 'gdc.png'), 'rb') as fr, open('gicon.py', 'w') as fw:
    #    fw.write('icon = {}'.format(base64.b64encode(fr.read())))
    pixm = QtGui.QPixmap()
    pixm.loadFromData(base64.b64decode(gicon.icon))
    icon = QtGui.QIcon()
    icon.addPixmap(pixm)
    app.setWindowIcon(icon)

    ui = gdump_ui.gDumpUi()
    ui.show()

    sys.exit(app.exec_())
except Exception as err:
    import traceback

    # . traceback.print_exc()
    print('Exception in main_ui: {}'.format(repr(err), exc_info=True))

# <run in Terminal> pyinstaller -Fw main.py -n gdump
