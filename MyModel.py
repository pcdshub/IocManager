from PyQt4.QtGui import *
from PyQt4.QtCore import *
import utils
import os
import time
import fcntl
import threading

#
# Column definitions.
#
IOCNAME = 0
ENABLE  = 1
HOST    = 2
PORT    = 3
VERSION = 4
STATUS  = 5
EXTRA   = 6

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
                self.model.configuration(cfglist, hosts)

            result = utils.readStatusDir(self.hutch, self.readStatusFile)
            for l in result:
                rdir = l['rdir']
                l.update(utils.check_status(l['rhost'], l['rport'], l['id']))
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
                if l['newstyle']:
                    if s['rdir'] == '/tmp':
                        del s['rdir']
                    else:
                        s['newstyle'] = False  # We've switched from new to old?!?
                self.model.running(s)

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

class MyModel(QAbstractTableModel): 
    def __init__(self, hutch, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self.hutch = hutch
        self.user = "Guest"
        self.poll = StatusPoll(self, 5)
        (self.poll.mtime, self.cfglist, self.hosts) = utils.readConfig(hutch)
        self.addUsedHosts()
        
        for l in self.cfglist:
            l['status'] = utils.STATUS_INIT
            l['stattime'] = 0
        self.headerdata = ["IOC Name", "En", "Host", "Port", "Version", "Status", "Information"]
        self.field      = [None, None, 'host', 'port', 'dir', None, None]
        self.newfield   = [None, None, 'newhost', 'newport', 'newdir', None, None]
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
        i = self.findid(d['id'], self.cfglist)
        if i != None:
            if d['status'] == utils.STATUS_RUNNING or self.cfglist[i]['cfgstat'] != utils.CONFIG_DELETED:
                self.cfglist[i].update(d);
                self.dataChanged.emit(self.index(i,0), self.index(i,len(self.headerdata)))
            else:
                self.cfglist = self.cfglist[0:i]+self.cfglist[i+1:]
                self.sort(self.lastsort[0], self.lastsort[1])
            return
        else:
            d['host']    = d['rhost']
            d['port']    = d['rport']
            d['dir']     = d['rdir']
            d['disable'] = False
            d['cfgstat'] = utils.CONFIG_DELETED
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

    def value(self, entry, c):
        if c == IOCNAME:
            return entry['id']
        elif c == STATUS:
            return entry['status']
        elif c == EXTRA:
            v = ""
            if entry['dir'] != entry['rdir']:
                v = entry['rdir'] + " "
            if entry['host'] != entry['rhost'] or entry['port'] != entry['rport']:
                v += "on " + entry['rhost'] + ":" + entry['rport']
            return v
        elif c == ENABLE:
            return ""
        else:
            try:
                return entry[self.newfield[c]]
            except:
                return entry[self.field[c]]
        return None
 
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.cfglist):
            return QVariant()
        elif role == Qt.DisplayRole or role == Qt.EditRole:
            return QVariant(self.value(self.cfglist[index.row()], index.column()))
        elif role == Qt.ForegroundRole:
            c = index.column()
            entry = self.cfglist[index.row()]
            if entry['cfgstat'] == utils.CONFIG_DELETED:
                return QVariant(QBrush(Qt.red))
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
                if entry['status'] != utils.STATUS_RUNNING:
                    return QVariant(QBrush(Qt.red))
                if (entry['host'] != entry['rhost'] or
                    entry['port'] != entry['rport'] or
                    entry['dir'] != entry['rdir']):
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

    def doApply(self):
        if not self.validateConfig():
            QMessageBox.critical(None,
                                 "Error", "Configuration has errors, not applied!",
                                 QMessageBox.Ok, QMessageBox.Ok)
            return
        self.doSave()
        utils.applyConfig(self.hutch)

    def doSave(self):
        if not self.validateConfig():
            QMessageBox.critical(None,
                                 "Error", "Configuration has errors, not saved!",
                                 QMessageBox.Ok, QMessageBox.Ok)
            return
        f = open(utils.CONFIG_FILE % self.hutch, "r+")
        try:
            fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except:
            QMessageBox.critical(None,
                                 "Error", "Failed to lock configuration for %s" % self.hutch,
                                 QMessageBox.Ok, QMessageBox.Ok)
            return
        f.truncate()
        f.write("hosts = [\n")
        for h in self.hosts:
            f.write("   '%s',\n" % h)
        f.write("]\n\n");
        f.write("procmgr_config = [\n")
        for entry in self.cfglist:
            try:
                host = entry['newhost']
            except:
                host = entry['host']
            try:
                port = entry['newport']
            except:
                port = entry['port']
            try:
                dir = entry['newdir']
            except:
                dir = entry['dir']
            if entry['disable']:
                dis = ", disable : True"
            else:
                dis = ""
            try:
                h = entry['history']
                if h != []:
                    his = ",\n  history : [" + ", ".join(["'"+l+"'" for l in h]) + "]"
                else:
                    his = ""
            except:
                his = ""
            f.write(" {id:'%s', host: '%s', port: %s, dir: '%s'%s%s},\n" %
                    (entry['id'], host, port, dir, dis, his))
        f.write("]\n");
        fcntl.lockf(f, fcntl.LOCK_UN)
        f.close()
        
    def doRevert(self):
        for entry in self.cfglist:
            for f in self.newfield:
                try:
                    if f != None:
                        del entry[f]
                except:
                    pass
        self.poll.mtime = None     # Force a re-read!
        self.dataChanged.emit(self.index(0,0), self.index(len(self.cfglist),len(self.headerdata)))

    def inConfig(self, index):
        entry = self.cfglist[index.row()]
        return entry['cfgstat'] != utils.CONFIG_DELETED

    def notSynched(self, index):
        entry = self.cfglist[index.row()]
        return (entry['dir'] != entry['rdir'] or entry['host'] != entry['rhost'] or
                entry['port'] != entry['rport'])

    def isChanged(self, index):
        entry = self.cfglist[index.row()]
        keys = entry.keys()
        return 'newhost' in keys or 'newport' in keys or 'newdir' in keys

    def revertIOC(self, index):
        entry = self.cfglist[index.row()]
        for f in self.newfield:
            try:
                if f != None:
                    del cfg[f]
            except:
                pass
        self.dataChanged.emit(self.index(index.row(),0),
                              self.index(index.row(),len(self.headerdata)))

    def deleteIOC(self, index):
        entry = self.cfglist[index.row()]
        entry['cfgstat'] = utils.CONFIG_DELETED
        if entry['status'] == utils.STATUS_RUNNING:
            self.dataChanged.emit(self.index(index.row(),0),
                                  self.index(index.row(),len(self.headerdata)))
        else:
            self.cfglist = self.cfglist[0:index.row()]+self.cfglist[index.row()+1:]
            self.sort(self.lastsort[0], self.lastsort[1])

    def setFromRunning(self, index):
        entry = self.cfglist[index.row()]
        for f in ['dir', 'host', 'port']:
            if entry[f] != entry['r'+f]:
                entry['new'+f] = entry['r'+f]
        entry['cfgstat'] = utils.CONFIG_ADDED
        self.dataChanged.emit(self.index(index.row(),0),
                              self.index(index.row(),len(self.headerdata)))

    def addExisting(self, index):
        entry = self.cfglist[index.row()]
        entry['cfgstat'] = utils.CONFIG_ADDED
        self.dataChanged.emit(self.index(index.row(),0),
                              self.index(index.row(),len(self.headerdata)))
        

    def addIOC(self, id, host, port, dir):
        cfg = {'id': id, 'host': host, 'port': port, 'dir': dir, 'status' : utils.STATUS_INIT,
               'stattime': 0, 'cfgstat' : utils.CONFIG_ADDED}
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
        os.system("gnome-terminal -t %s -x /bin/csh -c 'unsetenv LD_LIBRARY_PATH ; telnet %s %s' &" %
                  (entry['id'], entry['host'], entry['port']))

    def viewlogIOC(self, index):
        if isinstance(index, QModelIndex):
            id = self.cfglist[index.row()]['id']
        else:
            id = str(index)
        os.system("gnome-terminal -t " + id + " --geometry=128x30 -x tail -1000lf `ls -t " + (utils.LOGBASE % id) + "|head -1` &")

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
