from PyQt4.QtGui import *
from PyQt4.QtCore import *
import utils
import details_ui
import commit_ui
import os
import time
import fcntl
import threading
import subprocess
import tempfile
import stat

#
# Column definitions.
#
IOCNAME = 0
ENABLE  = 1
STATUS  = 2
HOST    = 3
PORT    = 4
VERSION = 5
PARENT  = 6
EXTRA   = 7

class StatusPoll(threading.Thread):
    def __init__(self, model, interval):
        threading.Thread.__init__(self)
        self.model = model
        self.hutch = model.hutch
        self.mtime = None
        self.interval = interval
        self.rmtime = {}
        self.daemon = True

    def run(self):
        last = 0
        while True:
            now = time.time()
            looptime = now - last
            if looptime < self.interval:
                time.sleep(self.interval + 1 - looptime)
                last = time.time()
            else:
                last = now

            result = utils.readConfig(self.hutch, self.mtime)
            if result != None:
                (self.mtime, cfglist, hosts) = result
                self.rmtime = {}      # Force a re-read!
                self.model.configuration(cfglist, hosts)

            result = utils.readStatusDir(self.hutch, self.readStatusFile)
            for l in result:
                rdir = l['rdir']
                l.update(utils.check_status(l['rhost'], l['rport'], l['rid']))
                l['stattime'] = time.time()
                if l['rdir'] == '/tmp':
                    l['rdir'] = rdir
                else:
                    l['newstyle'] = False
                self.model.running(l)

            for l in self.model.cfglist:
                if l['stattime'] + self.interval > time.time():
                    continue;
                s = utils.check_status(l['host'], l['port'], l['id'])
                s['stattime'] = time.time()
                s['rhost'] = l['host']
                s['rport'] = l['port']
                if l['newstyle']:
                    if s['rdir'] == '/tmp':
                        del s['rdir']
                    else:
                        s['newstyle'] = False  # We've switched from new to old?!?
                self.model.running(s)

            for p in self.model.children:
                if p.poll() != None:
                    self.model.children.remove(p)

    def readStatusFile(self, fn, ioc):
        try:
            # NFS weirdness.  If we don't open it, file status doesn't update!
            f = open(fn)
            mtime = os.stat(fn).st_mtime
            if not ioc in self.rmtime.keys() or mtime > self.rmtime[ioc]:
                l = f.readlines()
                if l != []:
                    self.rmtime[ioc] = mtime
                return l
            else:
                return []
        except:
            return []

class detailsdialog(QDialog):
    def __init__(self, parent=None):
      QWidget.__init__(self, parent)
      self.ui = details_ui.Ui_Dialog()
      self.ui.setupUi(self)

class commitdialog(QDialog):
    def doYes(self):
        self.result = QDialogButtonBox.Yes

    def doNo(self):
        self.result = QDialogButtonBox.No

    def doCancel(self):
        self.result = QDialogButtonBox.Cancel
        
    def __init__(self, parent=None):
      self.result = QDialogButtonBox.Cancel
      QWidget.__init__(self, parent)
      self.ui = commit_ui.Ui_Dialog()
      self.ui.setupUi(self)
      self.ui.buttonBox.button(QDialogButtonBox.Yes).clicked.connect(self.doYes)
      self.ui.buttonBox.button(QDialogButtonBox.No).clicked.connect(self.doNo)
      self.ui.buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.doCancel)

class MyModel(QAbstractTableModel): 
    def __init__(self, hutch, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self.detailsdialog = detailsdialog(parent)
        self.commitdialog = commitdialog(parent)
        self.hutch = hutch
        self.user = ""
        self.userIO = None
        self.poll = StatusPoll(self, 5)
        self.children = []
        (self.poll.mtime, self.cfglist, self.hosts) = utils.readConfig(hutch)
        self.addUsedHosts()
        
        for l in self.cfglist:
            l['status'] = utils.STATUS_INIT
            l['stattime'] = 0
        self.headerdata = ["IOC Name", "En", "Status", "Host", "Port", "Version", "Parent", "Information"]
        self.field      = ['id', None, None, 'host', 'port', 'dir', 'pdir', None]
        self.newfield   = ['newid', None, None, 'newhost', 'newport', 'newdir', None, None]
        self.lastsort   = (0, Qt.DescendingOrder)

    def addUsedHosts(self):
        hosts = [l['host'] for l in self.cfglist]
        hosts[-1:] = self.hosts
        hosts = list(set(hosts))
        hosts.sort()
        self.hosts = hosts

    def startPoll(self):
        self.poll.start()

    def findid(self, id, l):
        for i in range(len(l)):
            if id == l[i]['id']:
                return i
        return None

    def findhostport(self, h, p, l):
        for i in range(len(l)):
            if h == l[i]['host'] and p == l[i]['port']:
                return i
        return None

    def configuration(self, cfglist, hostlist):
        # Process a new configuration file!
        cfgonly = []
        ouronly = []
        both    = []
        for i in range(len(cfglist)):
            j = self.findid(cfglist[i]['id'], self.cfglist)
            if j != None:
                both.append((i,j))
            else:
                cfgonly.append(i)
        for i in range(len(self.cfglist)):
            j = self.findid(self.cfglist[i]['id'], cfglist)
            if j == None:
                ouronly[:0] = [i]
                
        for (i,j) in both:
            del cfglist[i]['newstyle']
            self.cfglist[j].update(cfglist[i])

        for i in cfgonly:
            cfglist[i]['status'] = utils.STATUS_INIT
            cfglist[i]['stattime'] = 0
            self.cfglist.append(cfglist[i])

        # Note: this list is reverse sorted by construction!
        for i in ouronly:
            if self.cfglist[i]['cfgstat'] != utils.CONFIG_ADDED:
                self.cfglist = self.cfglist[0:i]+self.cfglist[i+1:]
        
        self.sort(self.lastsort[0], self.lastsort[1])

        # Just append the new hostlist, duplicates and all, then go fix it up!
        self.hosts[-1:] = hostlist
        self.addUsedHosts()

    def running(self, d):
        # Process a new status dictionary!
        i = self.findid(d['rid'], self.cfglist)
        if i == None:
            i = self.findhostport(d['rhost'], d['rport'], self.cfglist)
        if i != None:
            if self.cfglist[i]['dir'] == utils.CAMRECORDER:
                d['rdir'] = utils.CAMRECORDER
            if d['status'] == utils.STATUS_RUNNING or self.cfglist[i]['cfgstat'] != utils.CONFIG_DELETED:
                # Sigh.  If we just emit dataChanged for the row, editing the port number becomes
                # nearly impossible, because we keep writing it over.  Therefore, we need to avoid
                # it... except, of course, sometimes it *does* change!
                oldport = self.cfglist[i]['rport']
                self.cfglist[i].update(d);
                if oldport != self.cfglist[i]['rport']:
                    self.dataChanged.emit(self.index(i,0), self.index(i,len(self.headerdata)-1))
                else:
                    if PORT > 0:
                        self.dataChanged.emit(self.index(i,0), self.index(i,PORT-1))
                    if PORT < len(self.headerdata)-1:
                        self.dataChanged.emit(self.index(i,PORT+1), self.index(i,len(self.headerdata)-1))
            else:
                self.cfglist = self.cfglist[0:i]+self.cfglist[i+1:]
                self.sort(self.lastsort[0], self.lastsort[1])
            return
        elif d['status'] == utils.STATUS_RUNNING:
            d['id']      = d['rid']
            d['host']    = d['rhost']
            d['port']    = d['rport']
            d['dir']     = d['rdir']
            d['pdir']    = ""
            d['disable'] = False
            d['cfgstat'] = utils.CONFIG_DELETED
            d['alias']   = ""
            self.cfglist.append(d)
            self.sort(self.lastsort[0], self.lastsort[1])

    #
    # IOCNAME can be selected.
    # ENABLE can be selected and checked.
    # HOST, PORT, and VERSION can be edited.
    # STATUS and EXTRA are only enabled.
    #
    def flags(self, index):
        c = index.column()
        if c == IOCNAME:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        elif c == ENABLE:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
        elif c == STATUS or c == EXTRA:
            return Qt.ItemIsEnabled
        else:
            return Qt.ItemIsEnabled | Qt.ItemIsEditable

    def setData(self, index, value, role=Qt.EditRole):
        try:
            entry = self.cfglist[index.row()]
        except:
            return False
        c = index.column()
        if c == ENABLE:
            (val, ok) = value.toInt()
            if not ok:
                return False
            entry['disable'] = (val == Qt.Unchecked)
            self.dataChanged.emit(index, index)
            return True
        elif c == PORT:
            (val, ok) = value.toInt()
            if not ok:
                return False
            entry['newport'] = val
            self.dataChanged.emit(index, index)
            return True
        else:
            val = value.toString()
            entry[self.newfield[c]] = val
            if entry[self.newfield[c]] == entry[self.field[c]]:
                del entry[self.newfield[c]]
            self.dataChanged.emit(index, index)
            return True
 
    def rowCount(self, parent): 
        return len(self.cfglist)
 
    def columnCount(self, parent): 
        return len(self.headerdata)

    def value(self, entry, c, display=True):
        if c == STATUS:
            return entry['status']
        elif c == EXTRA:
            v = ""
            if entry['dir'] != entry['rdir'] and entry['rdir'] != "/tmp":
                v = entry['rdir'] + " "
            if entry['host'] != entry['rhost'] or entry['port'] != entry['rport']:
                v += "on " + entry['rhost'] + ":" + str(entry['rport'])
            if entry['id'] != entry['rid']:
                v += "as " + entry['rid']
            return v
        elif c == ENABLE:
            return ""
        if c == IOCNAME and display == True:
            # First try to find an alias!
            try:
                if entry['newalias'] != "":
                    return entry['newalias']
            except:
                if entry['alias'] != "":
                    return entry['alias']
        try:
            return entry[self.newfield[c]]
        except:
            try:
                return entry[self.field[c]]
            except:
                print "No %s in entry:" % self.field[c]
                print entry
                return ""
 
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.cfglist):
            return QVariant()
        elif role == Qt.DisplayRole or role == Qt.EditRole:
            return QVariant(self.value(self.cfglist[index.row()], index.column(),
                                       role == Qt.DisplayRole))
        elif role == Qt.ForegroundRole:
            c = index.column()
            entry = self.cfglist[index.row()]
            if entry['cfgstat'] == utils.CONFIG_DELETED:
                return QVariant(QBrush(Qt.red))
            try:
                if c == IOCNAME and entry['newalias'] != entry['alias']:
                    return QVariant(QBrush(Qt.blue))
            except:
                pass
            try:
                if entry[self.newfield[c]] != entry[self.field[c]]:
                    return QVariant(QBrush(Qt.blue))
                else:
                    del entry[self.newfield[c]]
                    return QVariant()
            except:
                return QVariant()
        elif role == Qt.BackgroundRole:
            c = index.column()
            if c == STATUS:
                entry = self.cfglist[index.row()]
                if entry['disable']:
                    if entry['status'] == utils.STATUS_RUNNING:
                        if (entry['host'] != entry['rhost'] or
                            entry['port'] != entry['rport'] or
                            entry['dir'] != entry['rdir'] or
                            entry['id'] != entry['rid']):
                            return QVariant(QBrush(Qt.yellow))
                        else:
                            return QVariant(QBrush(Qt.red))
                    else:
                        return QVariant(QBrush(Qt.green))
                else:
                    if entry['status'] != utils.STATUS_RUNNING:
                        return QVariant(QBrush(Qt.red))
                    if (entry['host'] != entry['rhost'] or
                        entry['port'] != entry['rport'] or
                        entry['dir'] != entry['rdir'] or
                        entry['id'] != entry['rid']):
                        return QVariant(QBrush(Qt.yellow))
                    else:
                        return QVariant(QBrush(Qt.green))
            elif c == PORT:
                r = index.row()
                h = self.value(self.cfglist[r], HOST)
                p = self.value(self.cfglist[r], PORT)
                for i in range(len(self.cfglist)):
                    if i == r:
                        continue
                    h2 = self.value(self.cfglist[i], HOST)
                    p2 = self.value(self.cfglist[i], PORT)
                    if (h == h2 and p == p2):
                        return QVariant(QBrush(Qt.red))
                return QVariant()
            else:
                return QVariant()
        elif role == Qt.CheckStateRole:
            if index.column() == ENABLE:
                entry = self.cfglist[index.row()]
                if entry['disable']:
                    return QVariant(Qt.Unchecked)
                else:
                    return QVariant(Qt.Checked)
            else:
                return QVariant()
        else:
            return QVariant()

    def headerData(self, col, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return QVariant(self.headerdata[col])
        return QVariant()

    def sort(self, Ncol, order):
        self.lastsort = (Ncol, order)
        self.emit(SIGNAL("layoutAboutToBeChanged()"))
        if Ncol == PORT:
            self.cfglist = sorted(self.cfglist, key=lambda d: int(self.value(d, Ncol)))
        else:
            self.cfglist = sorted(self.cfglist, key=lambda d: self.value(d, Ncol))
        if order == Qt.DescendingOrder:
            self.cfglist.reverse()
        self.emit(SIGNAL("layoutChanged()"))

    def applyAddList(self, i, config, current, pfix, d, lst, verb):
        for l in lst:
            try:
                a = config[l]['alias']
                if a == "":
                    a = config[l]['id']
                else:
                    a += ' (%s)' % config[l]['id']
            except:
                a = config[l]['id']
            check = QCheckBox(d)
            check.setChecked(True)
            check.setText("%s %s on %s:%d" % (verb, a, current[l][pfix + 'host'],
                                              current[l][pfix + 'port']))
            d.layout.addWidget(check)
            i = i + 1
            d.checks.append(check)
        return i

    def applyVerify(self, current, config, kill, start, restart):
        d = QDialog();
        d.setWindowTitle("Apply Confirmation")
        d.layout = QVBoxLayout(d)
        d.mlabel = QLabel(d)
        d.mlabel.setText("Apply will take the following actions:")
        d.layout.addWidget(d.mlabel)
        d.checks = []
        kill_only    = [k for k in kill if not k in start]
        kill_restart = [k for k in kill if k in start]
        start_only   = [s for s in start if not s in kill]
        k  = self.applyAddList(0,  config, current, 'r', d, kill_only,    "KILL")
        k2 = self.applyAddList(k,  config, current, 'r', d, kill_restart, "KILL and RESTART")
        s  = self.applyAddList(k2, config, config,  '',  d, start_only,   "START")
        r  = self.applyAddList(s,  config, current, 'r', d, restart,      "RESTART")

        d.buttonBox = QDialogButtonBox(d)
        d.buttonBox.setOrientation(Qt.Horizontal)
        d.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        d.layout.addWidget(d.buttonBox)
        d.connect(d.buttonBox, SIGNAL("accepted()"), d.accept)
        d.connect(d.buttonBox, SIGNAL("rejected()"), d.reject)

        if d.exec_() == QDialog.Accepted:
            checks =  [c.isChecked() for c in d.checks]
            kill_only    = [kill_only[i]    for i in range(len(kill_only))    if checks[i]]
            kill_restart = [kill_restart[i] for i in range(len(kill_restart)) if checks[k+i]]
            start_only   = [start_only[i]   for i in range(len(start_only))   if checks[k2+i]]
            restart      = [restart[i]      for i in range(len(restart))      if checks[s+i]]
            kill = kill_only + kill_restart
            start = start_only + kill_restart
            return (kill, start, restart)
        else:
            return ([], [], [])

    def doApply(self):
        if not self.validateConfig():
            QMessageBox.critical(None,
                                 "Error", "Configuration has errors, not applied!",
                                 QMessageBox.Ok, QMessageBox.Ok)
            return
        if self.doSave():
            utils.applyConfig(self.hutch, self.applyVerify)

    def doSave(self):
        if not self.validateConfig():
            QMessageBox.critical(None,
                                 "Error", "Configuration has errors, not saved!",
                                 QMessageBox.Ok, QMessageBox.Ok)
            return False
        # Do we want to SVN it?!?
        d = self.commitdialog
        d.setWindowTitle("SVN Commit %s" % self.hutch)
        d.ui.commentEdit.setPlainText("")
        while True:
            d.exec_()
            if d.result == QDialogButtonBox.Cancel:
                return False
            if d.result == QDialogButtonBox.No:
                comment = None
                break
            comment = str(d.ui.commentEdit.toPlainText())
            if comment != "":
                break
            QMessageBox.critical(None,
                                 "Error", "Must have a comment for SVN commit for %s" % self.hutch,
                                 QMessageBox.Ok, QMessageBox.Ok)
        try:
            file = tempfile.NamedTemporaryFile(delete=False)
            utils.writeConfig(self.hutch, self.hosts, self.cfglist, file)
            file.close()
            os.chmod(file.name, stat.S_IRUSR | stat.S_IRGRP |stat.S_IROTH)
            utils.installConfig(self.hutch, file.name, self.userIO)
            try:
                os.remove(file.name)
            except:
                pass
        except:
            QMessageBox.critical(None,
                                 "Error", "Failed to lock configuration for %s" % self.hutch,
                                 QMessageBox.Ok, QMessageBox.Ok)
            return False
        for entry in self.cfglist:
            #
            # IOC names are special.  If we just reprocess the file, we will have both the
            # old *and* the new names!  So we have to change the names here.
            #
            try:
                entry['id'] = entry['newid'].strip()
                del entry['newid']
            except:
                pass
            try:
                del entry['details']
            except:
                pass
        if comment != None:
            try:
                utils.commit_config(self.hutch, comment, self.userIO)
            except:
                pass
        return True

    def doRevert(self):
        for entry in self.cfglist:
            for f in self.newfield:
                try:
                    if f != None:
                        del entry[f]
                except:
                    pass
        self.poll.mtime = None     # Force a re-read!
        self.dataChanged.emit(self.index(0,0), self.index(len(self.cfglist),len(self.headerdata)-1))

    def inConfig(self, index):
        entry = self.cfglist[index.row()]
        return entry['cfgstat'] != utils.CONFIG_DELETED

    def notSynched(self, index):
        entry = self.cfglist[index.row()]
        return (entry['dir'] != entry['rdir'] or entry['host'] != entry['rhost'] or
                entry['port'] != entry['rport'] or entry['id'] != entry['rid'])

    def isChanged(self, index):
        entry = self.cfglist[index.row()]
        keys = entry.keys()
        return 'newhost' in keys or 'newport' in keys or 'newdir' in keys or 'newid' in keys

    def revertIOC(self, index):
        entry = self.cfglist[index.row()]
        for f in self.newfield:
            try:
                if f != None:
                    del cfg[f]
            except:
                pass
        self.dataChanged.emit(self.index(index.row(),0),
                              self.index(index.row(),len(self.headerdata)-1))

    def deleteIOC(self, index):
        entry = self.cfglist[index.row()]
        entry['cfgstat'] = utils.CONFIG_DELETED
        if entry['status'] == utils.STATUS_RUNNING:
            self.dataChanged.emit(self.index(index.row(),0),
                                  self.index(index.row(),len(self.headerdata)-1))
        else:
            self.cfglist = self.cfglist[0:index.row()]+self.cfglist[index.row()+1:]
            self.sort(self.lastsort[0], self.lastsort[1])

    def setFromRunning(self, index):
        entry = self.cfglist[index.row()]
        for f in ['id', 'dir', 'host', 'port']:
            if entry[f] != entry['r'+f]:
                entry['new'+f] = entry['r'+f]
        entry['cfgstat'] = utils.CONFIG_ADDED
        self.dataChanged.emit(self.index(index.row(),0),
                              self.index(index.row(),len(self.headerdata)-1))

    def addExisting(self, index):
        entry = self.cfglist[index.row()]
        entry['cfgstat'] = utils.CONFIG_ADDED
        self.dataChanged.emit(self.index(index.row(),0),
                              self.index(index.row(),len(self.headerdata)-1))
        
    def editDetails(self, index):
        entry = self.cfglist[index.row()]
        try:
            details = entry['details']
        except:
            # Remember what was in the configuration file!
            details = ["", 0, ""]
            try:
                details[0] = entry['cmd']
            except:
                pass
            try:
                details[1] = entry['delay']
            except:
                pass
            try:
                details[2] = entry['flags']
            except:
                pass
            entry['details'] = details
        self.detailsdialog.setWindowTitle("Edit Details - %s" % entry['id'])
        try:
            self.detailsdialog.ui.aliasEdit.setText(entry['newalias'])
        except:
            self.detailsdialog.ui.aliasEdit.setText(entry['alias'])
        try:
            self.detailsdialog.ui.cmdEdit.setText(entry['cmd'])
        except:
            self.detailsdialog.ui.cmdEdit.setText("")
        try:
            self.detailsdialog.ui.delayEdit.setText(str(entry['delay']))
        except:
            self.detailsdialog.ui.delayEdit.setText("")
        try:
            self.detailsdialog.ui.flagCheckBox.setChecked('u' in entry['flags'])
        except:
            self.detailsdialog.ui.flagCheckBox.setChecked(False)
        if self.detailsdialog.exec_() == QDialog.Accepted:
            newcmd = str(self.detailsdialog.ui.cmdEdit.text())
            if newcmd == "":
                try:
                    del entry['cmd']
                except:
                    pass
            else:
                entry['cmd'] = newcmd
                
            if 'cmd' in entry.keys() and self.detailsdialog.ui.flagCheckBox.isChecked():
                newflags = 'u'
                entry['flags'] = 'u'
            else:
                newflags = ""
                try:
                    del entry['flags']
                except:
                    pass
                
            try:
                newdelay = int(self.detailsdialog.ui.delayEdit.text())
            except:
                newdelay = 0
            if newdelay == 0:
                try:
                    del entry['delay']
                except:
                    pass
            else:
                entry['delay'] = newdelay

            alias = str(self.detailsdialog.ui.aliasEdit.text())
            if alias != entry['alias']:
                entry['newalias'] = alias
            else:
                try:
                    del entry['newalias']
                except:
                    pass

            if details != [newcmd, newdelay, newflags]:
                # We're changed, so flag this with a fake ID change!
                if not 'newid' in entry.keys():
                    entry['newid'] = entry['id'] + ' '
            else:
                # We're not changed, so remove any fake ID change!
                if 'newid' in entry.keys() and entry['newid'] == entry['id'] + ' ':
                    del entry['newid']

    def addIOC(self, id, alias, host, port, dir):
        dir = utils.fixdir(dir, id)
        cfg = {'id': id, 'host': host, 'port': int(port), 'dir': dir, 'status' : utils.STATUS_INIT,
               'stattime': 0, 'cfgstat' : utils.CONFIG_ADDED, 'disable' : False,
               'history' : [], 'rid': id, 'rhost': host, 'rport': int(port), 'rdir': dir,
               'pdir' : utils.findParent(id, dir), 'newstyle' : True, 'alias' : alias }
        if not host in self.hosts:
            self.hosts.append(host)
            self.hosts.sort()
        self.cfglist.append(cfg)
        self.sort(self.lastsort[0], self.lastsort[1])

    # index is either an IOC name or an index!
    def connectIOC(self, index):
        if isinstance(index, QModelIndex):
            entry = self.cfglist[index.row()]
        else:
            entry = None
            for l in self.cfglist:
                if l['id'] == index:
                    entry = l
                    break
            if entry == None:
                return
        #
        # Sigh.  Because we want to do authentication, we have a version of kerberos on our path,
        # but unfortunately it doesn't play nice with the library that telnet uses!  Therefore,
        # we have to get rid of LD_LIBRARY_PATH here.
        #
        try:
            x = subprocess.Popen(["gnome-terminal", "--disable-factory", "-t", entry['id'], "-x",
                                 "/bin/csh", "-c",
                                 "unsetenv LD_LIBRARY_PATH ; telnet %s %s" % (entry['host'], entry['port'])])
            self.children.append(x)
        except:
            pass

    def viewlogIOC(self, index):
        if isinstance(index, QModelIndex):
            id = self.cfglist[index.row()]['id']
        else:
            id = str(index)
        try:
            x = subprocess.Popen(["gnome-terminal", "--disable-factory", "-t", id,
                                  "--geometry=128x30", "-x", "/bin/csh", "-c",
                                  "tail -1000lf `ls -t " + (utils.LOGBASE % id) + "* |head -1`"])
            self.children.append(x)
        except:
            pass

    def cleanupChildren(self):
        for p in self.children:
            p.kill()

    def doSaveVersions(self):
        for i in range(len(self.cfglist)):
            self.saveVersion(i)

    # index is either an integer or an index!
    def saveVersion(self, index):
        if isinstance(index, QModelIndex):
            entry = self.cfglist[index.row()]
        else:
            entry = self.cfglist[index]
        try:
            dir = entry[self.newfield[VERSION]]
        except:
            dir = entry[self.field[VERSION]]
        try:
            h = entry['history']
            if dir in h:
                h.remove(dir)
            h[:0] = [dir]
            if len(h) > 5:
                h = h[0:5]
        except:
            h = [dir]
        entry['history'] = h

    #
    # Generate a history list.  In order:
    #    New configuration setting
    #    Current configuration setting
    #    Current running setting
    #    Others in the history list.
    # 
    def history(self, row):
        entry = self.cfglist[row]
        x = [entry['dir']]
        try:
            x[:0] = [entry['newdir']]
        except:
            pass
        try:
            i = entry['rdir']
            if not i in x:
                x[len(x):] = [i]
        except:
            pass
        try:
            h = entry['history']
            for i in h:
                if not i in x:
                    x[len(x):] = [i]
        except:
            pass
        return x

    def getID(self, row):
        return self.cfglist[row]['id']

    def validateConfig(self):
        for i in range(len(self.cfglist)):
            h = self.value(self.cfglist[i], HOST)
            p = self.value(self.cfglist[i], PORT)
            for j in range(i+1, len(self.cfglist)):
                h2 = self.value(self.cfglist[j], HOST)
                p2 = self.value(self.cfglist[j], PORT)
                if (h == h2 and p == p2):
                    return False
        #
        # Anything else we want to check here?!?
        #
        return True
