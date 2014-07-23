from PyQt4 import QtCore, QtGui, Qt
from MyModel import MyModel
from MyDelegate import MyDelegate
from ioc_ui import Ui_MainWindow
from Pv import Pv
import pyca
import utils

def caput(pvname,value,timeout=1.0):
    try:
        pv = Pv(pvname)
        pv.connect(timeout)
        pv.get(ctrl=False, timeout=timeout)
        pv.put(value, timeout)
        pv.disconnect()
    except pyca.pyexc, e:
        print 'pyca exception: %s' %(e)
    except pyca.caexc, e:
        print 'channel access exception: %s' %(e)

def connectPv(name, timeout=-1.0):
    try:
        pv = Pv(name)
        if timeout < 0:
            pv.connect_cb = lambda isconn: __connect_callback(pv, isconn)
            pv.connect(timeout)
        else:
            pv.connect(timeout)
            pv.get(False, timeout)
        return pv
    except:
      return None

def __connect_callback(pv, isconn):
    if (isconn):
        pv.connect_cb = pv.connection_handler
        pv.get(False, -1.0)

def __getevt_callback(pv, e=None):
    if e is None:
        pv.getevt_cb = None
        pv.monitor(pyca.DBE_VALUE)
        pyca.flush_io()

def monitorPv(name,handler):
    try:
        pv = connectPv(name)
        pv.getevt_cb = lambda  e=None: __getevt_callback(pv, e)
        pv.monitor_cb = lambda e=None: handler(pv, e)
        return pv
    except:
        return None

######################################################################
 
class GraphicUserInterface(QtGui.QMainWindow):
    def __init__(self, app, hutch):
        QtGui.QMainWindow.__init__(self)
        self.__app = app
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setWindowTitle("IocManager")
        self.hutch = hutch
        self.model = MyModel(hutch)
        self.delegate = MyDelegate(None, hutch)
        self.connect(self.ui.applyButton,    QtCore.SIGNAL("clicked()"), self.model.doApply)
        self.connect(self.ui.revertButton,   QtCore.SIGNAL("clicked()"), self.model.doRevert)
        self.connect(self.ui.quitButton,     QtCore.SIGNAL("clicked()"), self.doQuit)
        self.connect(self.ui.saveButton,     QtCore.SIGNAL("clicked()"), self.model.doSave)
        self.connect(self.ui.rebootButton,   QtCore.SIGNAL("clicked()"), self.doReboot)
        self.connect(self.ui.logButton,      QtCore.SIGNAL("clicked()"), self.doLog)
        self.connect(self.ui.consoleButton,  QtCore.SIGNAL("clicked()"), self.doConsole)
        self.connect(self.ui.rememberButton, QtCore.SIGNAL("clicked()"), self.model.doSaveVersions)
        self.ui.tableView.setModel(self.model)
        self.ui.tableView.setItemDelegate(self.delegate)
        self.ui.tableView.verticalHeader().setVisible(False)
        self.ui.tableView.horizontalHeader().setStretchLastSection(True)
        self.ui.tableView.resizeColumnsToContents()
        self.ui.tableView.resizeRowsToContents()
        self.ui.tableView.setSortingEnabled(True)
        self.ui.tableView.sortByColumn(0, QtCore.Qt.AscendingOrder)
        self.ui.tableView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.ui.tableView.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.connect(self.ui.tableView.selectionModel(),
                     QtCore.SIGNAL("selectionChanged(const QItemSelection&, const QItemSelection&)"),
                     self.getSelection)
        self.connect(self.ui.tableView, QtCore.SIGNAL("customContextMenuRequested(const QPoint&)"),
                     self.showContextMenu)
        self.currentIOC = None
        self.currentBase = None
        self.pvlist = []

    def closeEvent(self, event):
        self.disconnectPVs()
        QtGui.QMainWindow.closeEvent(self, event)

    def disconnectPVs(self):
        for pv in self.pvlist:
            pv.disconnect()
        self.pvlist = []

    def displayPV(self, pv, e=None):
        try:
            if e is None:
                pv.gui.setText(pv.format % pv.value)
        except:
            pass

    def doReboot(self):
        if self.currentBase:
            caput(self.currentBase + ":SYSRESET", 1)

    def doLog(self):
        if self.currentIOC:
            self.model.viewlogIOC(self.currentIOC)
    
    def doConsole(self):
        if self.currentIOC:
            self.model.connectIOC(self.currentIOC)
    
    def dopv(self, name, gui, format):
        pv = monitorPv(name, self.displayPV)
        if pv != None:
            gui.setText("")
            pv.gui = gui
            pv.format = format
            self.pvlist.append(pv)

    def getSelection(self, selected, deselected):
        try:
            row = selected.indexes()[0].row()
            ioc = self.model.data(self.model.index(row, 0)).toString()
            if ioc == self.currentIOC:
                return
            self.disconnectPVs()
            self.currentIOC = ioc
            self.ui.IOCname.setText(ioc)
            base = utils.getBaseName(ioc)
            self.currentBase = base
            self.dopv(base + ":HEARTBEAT", self.ui.heartbeat, "%d")
            self.dopv(base + ":TOD",       self.ui.tod,       "%s")
            self.dopv(base + ":STARTTOD",  self.ui.boottime,  "%s")
            pyca.flush_io()
        except:
            pass
                             
    def doQuit(self):
        self.close()
    
    def showContextMenu(self, pos):
        index = self.ui.tableView.indexAt(pos)
        menu = QtGui.QMenu()
        menu.addAction("Delete IOC")
        menu.addAction("Add New IOC")
        if not self.model.inConfig(index):
            menu.addAction("Add Running to Config")
        if self.model.notSynched(index):
            menu.addAction("Set from Running")
        if self.model.isChanged(index):
            menu.addAction("Revert IOC")
        menu.addAction("Remember Version")
        gpos = self.ui.tableView.viewport().mapToGlobal(pos)
        selectedItem = menu.exec_(gpos)
        if selectedItem != None:
            txt = selectedItem.text()
            if txt == "Revert IOC":
                self.model.revertIOC(index)
            elif txt == "Delete IOC":
                self.model.deleteIOC(index)
            elif txt == "Add New IOC":
                self.addIOC(index)
            elif txt == "Set from Running":
                self.model.setFromRunning(index)
            elif txt == "Add Running to Config":
                self.model.addExisting(index)
            elif txt == "Remember Version":
                self.model.saveVersion(index)

    def addIOC(self, index):
        d=QtGui.QFileDialog(self, "Add New IOC", utils.EPICS_SITE_TOP + "ioc/" + self.hutch)
        d.setFileMode(Qt.QFileDialog.Directory)
        d.setOptions(Qt.QFileDialog.ShowDirsOnly|Qt.QFileDialog.DontUseNativeDialog)
        l=d.layout()

        tmp=QtGui.QLabel()
        tmp.setText("IOC Name")
        l.addWidget(tmp, 4, 0)
        namegui=QtGui.QLineEdit()
        l.addWidget(namegui, 4, 1)

        tmp=QtGui.QLabel()
        tmp.setText("Host")
        l.addWidget(tmp, 5, 0)
        hostgui=QtGui.QLineEdit()
        l.addWidget(hostgui, 5, 1)

        tmp=QtGui.QLabel()
        tmp.setText("Port")
        l.addWidget(tmp, 6, 0)
        portgui=QtGui.QLineEdit()
        l.addWidget(portgui, 6, 1)
        if d.exec_() == Qt.QDialog.Rejected:
            return
        name = namegui.text()
        host = hostgui.text()
        port = portgui.text()
        try:
            dir = str(d.selectedFiles()[0])
        except:
            dir = ""
        if name == "" or host == "" or port == "" or dir == "":
            QMessageBox.critical(None,
                                 "Error", "Failed to set all parameters for new IOC!",
                                 QMessageBox.Ok, QMessageBox.Ok)
            return
        self.model.addIOC(name, host, port, dir)
