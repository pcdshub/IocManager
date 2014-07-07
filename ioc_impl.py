from PyQt4 import QtCore, QtGui, Qt
from MyModel import MyModel
from ioc_ui import Ui_MainWindow
import utils

######################################################################
 
class GraphicUserInterface(QtGui.QMainWindow):
    def __init__(self, app, hutch):
        QtGui.QMainWindow.__init__(self)
        self.__app = app
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.hutch = hutch
        self.model = MyModel(hutch)
        self.connect(self.ui.applyButton,  QtCore.SIGNAL("clicked()"), self.model.doApply)
        self.connect(self.ui.revertButton, QtCore.SIGNAL("clicked()"), self.model.doRevert)
        self.connect(self.ui.quitButton,   QtCore.SIGNAL("clicked()"), self.doQuit)
        self.ui.tableView.setModel(self.model)
        self.ui.tableView.verticalHeader().setVisible(False)
        self.ui.tableView.horizontalHeader().setStretchLastSection(True)
        self.ui.tableView.resizeColumnsToContents()
        self.ui.tableView.resizeRowsToContents()
        self.ui.tableView.setSortingEnabled(True)
        self.ui.tableView.sortByColumn(0, QtCore.Qt.AscendingOrder)
        self.ui.tableView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.connect(self.ui.tableView, QtCore.SIGNAL("customContextMenuRequested(const QPoint&)"),
                     self.showContextMenu)

        self.menus = []
        return
        menu = MyContextMenu(lambda table, index: index != None and index.row() == 0 and
                             index.column() >= param.params.firstdetidx)
        menu.addAction("Delete IOC", self.deleteIOC)
        menu.addAction("Add New IOC", self.addIOC)
        menu.addAction("Set from Running", self.setFromRunning)
        menu.addAction("Add Running to Configuration", self.addExisting)
        self.menus.append(menu)

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
        gpos = self.ui.tableView.viewport().mapToGlobal(pos)
        selectedItem = menu.exec_(gpos)
        if selectedItem != None:
            txt = selectedItem.text()
            if txt == "Revert IOC":
                self.model.revertIOC(index)
                return
            if txt == "Delete IOC":
                self.model.deleteIOC(index)
                return
            if txt == "Add New IOC":
                self.addIOC(index)
                return
            if txt == "Set from Running":
                self.model.setFromRunning(index)
                return
            if txt == "Add Running to Config":
                self.model.addExisting(index)
                return

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
        
            
