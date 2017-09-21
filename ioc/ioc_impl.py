from PyQt4 import QtCore, QtGui, Qt
import MyModel
from MyDelegate import MyDelegate
from ioc_ui import Ui_MainWindow
import auth_ui
from psp.Pv import Pv
import pyca
import utils
import os
import sys
import pty
import time
import pwd

class authdialog(QtGui.QDialog):
    def __init__(self, parent=None):
      QtGui.QWidget.__init__(self, parent)
      self.ui = auth_ui.Ui_Dialog()
      self.ui.setupUi(self)

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

######################################################################
 
class GraphicUserInterface(QtGui.QMainWindow):
    def __init__(self, app, hutch):
        QtGui.QMainWindow.__init__(self)
        self.__app = app
        self.myuid = pwd.getpwuid(os.getuid())[0]
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # Not sure how to do this in designer, so we put it randomly and move it now.
        self.ui.statusbar.addWidget(self.ui.userLabel)

        d = sys.path[0]
        while os.path.islink(d):
            l = os.readlink(d)
            if l[0] != '/':
                l = os.path.join(os.path.dirname(d), l)
            d = l
        version = os.path.basename(d)
        if len(version) > 1 and version[0] == 'R':
            version = " %s" % version
        else:
            version = ""
        self.setWindowTitle("%s IocManager%s" % (hutch.upper(), version))
        self.hutch = hutch
        self.authdialog = authdialog(self)
        self.model = MyModel.MyModel(hutch)
        self.utimer = QtCore.QTimer()
        self.delegate = MyDelegate(None, hutch)
        self.connect(self.ui.actionApply,    QtCore.SIGNAL("triggered()"), self.doApply)
        self.connect(self.ui.actionSave,     QtCore.SIGNAL("triggered()"), self.doSave)
        self.connect(self.ui.actionRevert,   QtCore.SIGNAL("triggered()"), self.model.doRevert)
        self.connect(self.ui.actionReboot,   QtCore.SIGNAL("triggered()"), self.doReboot)
        self.connect(self.ui.actionHard_Reboot, QtCore.SIGNAL("triggered()"), self.doHardReboot)
        self.connect(self.ui.actionReboot_Server, QtCore.SIGNAL("triggered()"), self.doServerReboot)
        self.connect(self.ui.actionLog,      QtCore.SIGNAL("triggered()"), self.doLog)
        self.connect(self.ui.actionConsole,  QtCore.SIGNAL("triggered()"), self.doConsole)
        self.connect(self.ui.actionRemember, QtCore.SIGNAL("triggered()"), self.model.doSaveVersions)
        self.connect(self.ui.actionAuth,     QtCore.SIGNAL("triggered()"), self.doAuthenticate)
        self.connect(self.ui.actionQuit,     QtCore.SIGNAL("triggered()"), self.doQuit)
        self.connect(self.ui.actionHelp,     QtCore.SIGNAL("triggered()"), self.doHelp)
        self.connect(self.utimer, QtCore.SIGNAL("timeout()"), self.unauthenticate)
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
        self.model.startPoll()
        self.unauthenticate()

    def closeEvent(self, event):
        self.disconnectPVs()
        self.model.cleanupChildren()
        QtGui.QMainWindow.closeEvent(self, event)

    def disconnectPVs(self):
        for pv in self.pvlist:
            try:
                pv.disconnect()
            except:
                pass
        self.pvlist = []

    def displayPV(self, pv, e=None):
        try:
            if e is None:
                pv.gui.setText(pv.format % pv.value)
        except:
            pass

    def doApply(self):
        if not self.authorize_action():
            return
        self.model.doApply()

    def doHelp(self):
        d = QtGui.QDialog();
        d.setWindowTitle("IocManager Help")
        d.layout = QtGui.QVBoxLayout(d)
        d.label1 = QtGui.QLabel(d)
        d.label1.setText("Documentation for the IocManager can be found on confluence:")
        d.layout.addWidget(d.label1)
        d.label2 = QtGui.QLabel(d)
        d.label2.setText("https://confluence.slac.stanford.edu/display/PCDS/IOC+Manager+User+Guide")
        d.layout.addWidget(d.label2)
        d.buttonBox = QtGui.QDialogButtonBox(d)
        d.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        d.buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Ok)
        d.layout.addWidget(d.buttonBox)
        d.connect(d.buttonBox, QtCore.SIGNAL("accepted()"), d.accept)
        d.exec_()
                             
    def doQuit(self):
        self.close()
        
    def doSave(self):
        if not self.authorize_action():
            return
        self.model.doSave()

    def doReboot(self):
        if self.currentBase:
            caput(self.currentBase + ":SYSRESET", 1)

    def doHardReboot(self):
        if self.currentIOC:
            self.model.rebootIOC(self.currentIOC)

    def doServerReboot(self):
        if self.currentIOC:
            if not self.authorize_action():
                return
            self.model.rebootServer(self.currentIOC)
    
    def doLog(self):
        if self.currentIOC:
            self.model.viewlogIOC(self.currentIOC)
    
    def doConsole(self):
        if self.currentIOC and (self.model.getVar('allow_console') or self.authorize_action()):
            self.model.connectIOC(self.currentIOC)
    
    def dopv(self, name, gui, format):
        pv = Pv(name, initialize=True)
        if pv != None:
            gui.setText("")
            pv.gui = gui
            pv.format = format
            self.pvlist.append(pv)
            pv.add_monitor_callback(lambda e: self.displayPV(pv, e))
            pv.wait_ready()
            pv.monitor()

    def getSelection(self, selected, deselected):
        try:
            row = selected.indexes()[0].row()
            ioc = self.model.data(self.model.index(row, MyModel.IOCNAME), QtCore.Qt.EditRole).toString()
            host = self.model.data(self.model.index(row, MyModel.HOST), QtCore.Qt.EditRole).toString()
            if ioc == self.currentIOC:
                return
            self.disconnectPVs()
            self.currentIOC = ioc
            self.ui.IOCname.setText(ioc)
            base = utils.getBaseName(ioc)
            self.currentBase = base
            if base != None:
                self.dopv(base + ":HEARTBEAT", self.ui.heartbeat, "%d")
                self.dopv(base + ":TOD",       self.ui.tod,       "%s")
                self.dopv(base + ":STARTTOD",  self.ui.boottime,  "%s")
                pyca.flush_io()
            d = utils.netconfig(host)
            try:
                self.ui.location.setText(d['location'])
            except:
                self.ui.location.setText("")
            try:
                self.ui.description.setText(d['description'])
            except:
                self.ui.description.setText("")
        except:
            pass
    
    def showContextMenu(self, pos):
        index = self.ui.tableView.indexAt(pos)
        menu = QtGui.QMenu()
        menu.addAction("Add New IOC")
        if index.row() != -1:
            menu.addAction("Delete IOC")
            if not self.model.inConfig(index):
                menu.addAction("Add Running to Config")
            if self.model.notSynched(index):
                menu.addAction("Set from Running")
            if self.model.isChanged(index):
                menu.addAction("Revert IOC")
            if self.model.needsApply(index):
                menu.addAction("Apply Configuration")
            menu.addAction("Remember Version")
            menu.addAction("Edit Details")
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
            elif txt == "Edit Details":
                self.model.editDetails(index)
            elif txt == "Apply Configuration":
                self.model.applyOne(index)

    def setParent(self, gui, iocfn, dir):
        if dir != "":
            gui.setText(utils.findParent(iocfn(), dir))

    def addIOC(self, index):
        d=QtGui.QFileDialog(self, "Add New IOC", utils.EPICS_SITE_TOP + "ioc/" + self.hutch)
        d.setFileMode(Qt.QFileDialog.Directory)
        d.setOptions(Qt.QFileDialog.ShowDirsOnly|Qt.QFileDialog.DontUseNativeDialog)
        d.setSidebarUrls([QtCore.QUrl("file://" + os.getenv("HOME")),
                          QtCore.QUrl("file://" + utils.EPICS_SITE_TOP + "ioc/" + self.hutch),
                          QtCore.QUrl("file://" + utils.EPICS_SITE_TOP + "ioc/common"),
                          QtCore.QUrl("file://" + utils.EPICS_DEV_TOP )])
        l=d.layout()

        tmp=QtGui.QLabel()
        tmp.setText("IOC Name *")
        l.addWidget(tmp, 4, 0)
        namegui=QtGui.QLineEdit()
        l.addWidget(namegui, 4, 1)

        tmp=QtGui.QLabel()
        tmp.setText("Alias")
        l.addWidget(tmp, 5, 0)
        aliasgui=QtGui.QLineEdit()
        l.addWidget(aliasgui, 5, 1)

        tmp=QtGui.QLabel()
        tmp.setText("Host *")
        l.addWidget(tmp, 6, 0)
        hostgui=QtGui.QLineEdit()
        l.addWidget(hostgui, 6, 1)

        tmp=QtGui.QLabel()
        tmp.setText("Port *")
        l.addWidget(tmp, 7, 0)
        portgui=QtGui.QLineEdit()
        l.addWidget(portgui, 7, 1)

        tmp=QtGui.QLabel()
        tmp.setText("Parent")
        l.addWidget(tmp, 8, 0)
        parentgui=QtGui.QLineEdit()
        parentgui.setReadOnly(True)
        l.addWidget(parentgui, 8, 1)

        tmp=QtGui.QLabel()
        tmp.setText("* = Required Fields")
        l.addWidget(tmp, 9, 0)

        fn = lambda dir : self.setParent(parentgui, namegui.text, dir)
        self.connect(d, QtCore.SIGNAL("directoryEntered(const QString &)"), fn)
        self.connect(d, QtCore.SIGNAL("currentChanged(const QString &)"), fn)

        while True:
            if d.exec_() == Qt.QDialog.Rejected:
                return
            name  = str(namegui.text())
            alias = str(aliasgui.text())
            host  = str(hostgui.text())
            port  = str(portgui.text())
            try:
                dir = str(d.selectedFiles()[0])
            except:
                dir = ""
            if name == "" or host == "" or port == "" or dir == "":
                QtGui.QMessageBox.critical(None,
                                           "Error",
                                           "Failed to set required parameters for new IOC!",
                                           QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok)
                continue
            try:
                n = int(port)
            except:
                QtGui.QMessageBox.critical(None,
                                           "Error",
                                           "Port is not an integer!",
                                           QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok)
                continue
            self.model.addIOC(name, alias, host, port, dir)
            return

    def authenticate_user(self, user, password):
        if user == "":
            user = self.myuid
        need_su = self.myuid != user
        #
        # Try to use su to become the user.  If this fails, one of the
        # I/O operations below will raise an exception, because the su
        # will exit.
        #
        (pid, fd) = pty.fork()
        if pid == 0:
            try:
                if need_su:
                    os.execv("/usr/bin/ssh", ["ssh", user + "@" + utils.COMMITHOST, "/bin/tcsh", "-if"])
                else:
                    os.execv("/usr/bin/ssh", ["ssh", utils.COMMITHOST, "/bin/tcsh", "-if"])
            except:
                pass
            print "Say what?  execv failed?"
            sys.exit(0)
        l = utils.read_until(fd, "(assword:|> )").group(1)
        if l != "> ":
            os.write(fd, password + "\n")
            l = utils.read_until(fd, "> ")
        if utils.KINIT != None and password != "":
            os.write(fd, utils.KINIT + "\n")
            l = utils.read_until(fd, ": ")
            os.write(fd, password + "\n")
            l = utils.read_until(fd, "> ")
        self.model.user = user
        if self.model.userIO != None:
            try:
                os.close(self.model.userIO)
            except:
                pass
        self.model.userIO = fd
        if need_su:
            self.utimer.start(10 * 60000)  # Let's go for 10 minutes.
        self.ui.userLabel.setText("User: " + user)

    def doAuthenticate(self):
        result = self.authdialog.exec_()
        user = self.authdialog.ui.nameEdit.text()
        password = str(self.authdialog.ui.passEdit.text())
        self.authdialog.ui.passEdit.setText("")
        if result == QtGui.QDialog.Accepted:
            try:
                self.authenticate_user(user, password)
            except:
                print "Authentication as %s failed!" % user
                self.unauthenticate()

    def unauthenticate(self):
        self.utimer.stop()
        self.authenticate_user(self.myuid, "")

    def authorize_action(self):
        # The user might be OK.
        if utils.check_auth(self.model.user, self.hutch):
            return True
        # If the user isn't OK, give him or her a chance to authenticate.
        if self.model.user == self.myuid:
            self.doAuthenticate()
        if utils.check_auth(self.model.user, self.hutch):
            return True
        QtGui.QMessageBox.critical(None,
                                   "Error", "Action not authorized for user %s" % self.model.user,
                                   QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok)
        return False
