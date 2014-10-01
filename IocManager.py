#!/usr/bin/env python
from PyQt4 import QtGui
from options import Options
from ioc_impl import GraphicUserInterface
import sys
        
if __name__ == "__main__":
    options = Options(['hutch'], [], [])
    try:
        options.parse()
    except Exception, msg:
        options.usage(str(msg))
        sys.exit(1)
    app = QtGui.QApplication([''])
    gui = GraphicUserInterface(app, options.hutch.lower())
    try:
        gui.show()
        retval = app.exec_()
    except KeyboardInterrupt:
        app.exit(1)
    sys.exit(0)
