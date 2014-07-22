from PyQt4.QtGui import *
from PyQt4.QtCore import *
import utils
import os

IOCNAME = 0
ENABLE  = 1
HOST    = 2
PORT    = 3
VERSION = 4
STATUS  = 5
EXTRA   = 6

class MyModel(QAbstractTableModel): 
    def __init__(self, hutch, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self.hutch = hutch
        (self.dlist, self.hosts) = utils.getAllStatus(hutch)
        self.headerdata = ["IOC Name", "En", "Host", "Port", "Version", "Status", "Information"]
        self.field      = [None, None, 'host', 'port', 'dir', None, None]
        self.newfield   = [None, None, 'newhost', 'newport', 'newdir', None, None]
        self.lastsort   = (0, Qt.DescendingOrder)

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
        (id, cfg, cur) = self.dlist[index.row()]
        if cfg == None:
            return False
        c = index.column()
        if c == ENABLE:
            (val, ok) = value.toInt()
            if not ok:
                return False
            cfg['disable'] = (val == Qt.Unchecked)
            self.dataChanged.emit(index, index)
            return True
        else:
            val = value.toString()
            cfg[self.newfield[c]] = val
            if cfg[self.newfield[c]] == cfg[self.field[c]]:
                del cfg[self.newfield[c]]
            self.dataChanged.emit(index, index)
            return True
 
    def rowCount(self, parent): 
        return len(self.dlist)
 
    def columnCount(self, parent): 
        return len(self.headerdata)

    def value(self, rowtuple, c):
        (id, cfg, cur) = rowtuple
        if c == IOCNAME:
            return id
        elif c == STATUS:
            try:
                return cur['status']
            except:
                return "NOCONNECT"
        elif c == EXTRA:
            if cfg == None or cur == None:
                return None
            v = ""
            if cfg['dir'] != cur['dir']:
                v = cur['dir'] + " "
            if cfg['host'] != cur['host'] or cfg['port'] != cur['port']:
                v += "on " + cur['host'] + ":" + cur['port']
            return v
        elif c == ENABLE:
            return ""
        else:
            if cfg == None:
                return cur[self.field[c]]
            try:
                return cfg[self.newfield[c]]
            except:
                return cfg[self.field[c]]
        return None
 
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): 
            return QVariant() 
        elif role == Qt.DisplayRole or role == Qt.EditRole:
            return QVariant(self.value(self.dlist[index.row()], index.column()))
        elif role == Qt.ForegroundRole:
            c = index.column()
            (id, cfg, cur) = self.dlist[index.row()]
            if cfg == None:
                return QVariant(QBrush(Qt.red))
            try:
                v = cfg[self.newfield[c]]
                return QVariant(QBrush(Qt.blue))
            except:
                return QVariant()
        elif role == Qt.BackgroundRole:
            c = index.column()
            if c == STATUS:
                (id, cfg, cur) = self.dlist[index.row()]
                if cur == None:
                    return QVariant(QBrush(Qt.red))
                if cfg == None:
                    return QVariant()
                if (cfg['host'] != cur['host'] or cfg['port'] != cur['port'] or
                    cfg['dir'] != cur['dir']):
                    return QVariant(QBrush(Qt.yellow))
                return QVariant(QBrush(Qt.green))
            elif c == PORT:
                r = index.row()
                h = self.value(self.dlist[r], HOST)
                p = self.value(self.dlist[r], PORT)
                for i in range(len(self.dlist)):
                    if i == r:
                        continue
                    h2 = self.value(self.dlist[i], HOST)
                    p2 = self.value(self.dlist[i], PORT)
                    if (h == h2 and p == p2):
                        return QVariant(QBrush(Qt.red))
                return QVariant()
            else:
                return QVariant()
        elif role == Qt.CheckStateRole:
            if index.column() == ENABLE:
                (id, cfg, cur) = self.dlist[index.row()]
                if cfg['disable']:
                    return QVariant(Qt.Unchecked)
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
            self.dlist = sorted(self.dlist, key=lambda rowtuple: int(self.value(rowtuple, Ncol)))
        else:
            self.dlist = sorted(self.dlist, key=lambda rowtuple: self.value(rowtuple, Ncol))
        if order == Qt.DescendingOrder:
            self.dlist.reverse()
        self.emit(SIGNAL("layoutChanged()"))

    def doApply(self):
        self.doSave()
        utils.applyConfig(self.hutch)
        (self.dlist, self.hosts) = utils.getAllStatus(self.hutch)
        self.sort(self.lastsort[0], self.lastsort[1])

    def doSave(self):
        f = open(utils.CONFIG_DIR + self.hutch, "w")
        f.write("hosts = [\n")
        for h in self.hosts:
            f.write("   '%s',\n" % h)
        f.write("]\n\n");
        f.write("procmgr_config = [\n")
        for (id, cfg, cur) in self.dlist:
            if cfg == None:
                continue
            try:
                host = cfg['newhost']
            except:
                host = cfg['host']
            try:
                port = cfg['newport']
            except:
                port = cfg['port']
            try:
                dir = cfg['newdir']
            except:
                dir = cfg['dir']
            if cfg['disable']:
                dis = ", disable : True"
            else:
                dis = ""
            try:
                h = cfg['history']
                his = ",\n  history : [" + ", ".join(["'"+l+"'" for l in h]) + "]"
            except:
                his = ""
            f.write(" {id:'%s', host: '%s', port: %s, dir: '%s'%s%s},\n" %
                    (id, host, port, dir, dis, his))
        f.write("]\n");
        f.close()
        (self.dlist, self.hosts) = utils.getAllStatus(self.hutch)
        self.sort(self.lastsort[0], self.lastsort[1])
        
    def doRevert(self):
        for (id, cfg, cur) in self.dlist:
            for f in self.newfield:
                try:
                    if f != None:
                        del cfg[f]
                except:
                    pass
        self.dataChanged.emit(self.index(0,0), self.index(len(self.dlist),len(self.headerdata)))

    def inConfig(self, index):
        (id, cfg, cur) = self.dlist[index.row()]
        return cfg != None
        pass

    def notSynched(self, index):
        (id, cfg, cur) = self.dlist[index.row()]
        if cfg == None or cur == None:
            return False
        return (cfg['dir'] != cur['dir'] or cfg['host'] != cur['host'] or
                cfg['port'] != cur['port'])

    def isChanged(self, index):
        (id, cfg, cur) = self.dlist[index.row()]
        if cfg == None:
            return False
        keys = cfg.keys()
        return 'newhost' in keys or 'newport' in keys or 'newdir' in keys

    def revertIOC(self, index):
        (id, cfg, cur) = self.dlist[index.row()]
        for f in self.newfield:
            try:
                if f != None:
                    del cfg[f]
            except:
                pass
        self.dataChanged.emit(self.index(index.row(),0),
                              self.index(index.row(),len(self.headerdata)))

    def deleteIOC(self, index):
        (id, cfg, cur) = self.dlist[index.row()]
        if cur != None:
            self.dlist[index.row()] = (id, None, cur)
            self.dataChanged.emit(self.index(index.row(),0),
                                  self.index(index.row(),len(self.headerdata)))
        else:
            self.dlist = self.dlist[0:index.row()]+self.dlist[index.row()+1:]
            self.sort(self.lastsort[0], self.lastsort[1])

    def setFromRunning(self, index):
        (id, cfg, cur) = self.dlist[index.row()]
        for f in ['dir', 'host', 'port']:
            if cfg[f] != cur[f]:
                cfg['new'+f] = cur[f]
        self.dataChanged.emit(self.index(index.row(),0),
                              self.index(index.row(),len(self.headerdata)))

    def addExisting(self, index):
        (id, cfg, cur) = self.dlist[index.row()]
        cfg = {'id': id, 'host': cur['host'], 'port': cur['port'], 'dir': cur['dir']}
        self.dlist[index.row()] = (id, cfg, cur)
        self.dataChanged.emit(self.index(index.row(),0),
                              self.index(index.row(),len(self.headerdata)))
        

    def addIOC(self, id, host, port, dir):
        cfg = {'id': id, 'host': host, 'port': port, 'dir': dir}
        cur = utils.getCurrentStatus(host, port)
        self.dlist.append((id, cfg, cur))
        self.sort(self.lastsort[0], self.lastsort[1])

    def connectIOC(self, index):
        if isinstance(index, QModelIndex):
            (id, cfg, cur) = self.dlist[index.row()]
        else:
            x = [l for l in self.dlist if l[0] == index]
            (id, cfg, cur) = x[0]
        if cfg != None:
            cur = cfg
        os.system("gnome-terminal -t %s -x telnet %s %s &" % (cfg['id'], cfg['host'], cfg['port']))

    def viewlogIOC(self, index):
        if isinstance(index, QModelIndex):
            (id, cfg, cur) = self.dlist[index.row()]
        else:
            id = str(index)
        os.system("gnome-terminal -t " + id + " --geometry=128x30 -x tail -1000lf `ls -t " + (utils.LOGBASE % id) + "|head -1` &")

    def doSaveVersions(self):
        for i in range(len(self.dlist)):
            self.saveVersion(i)

    def saveVersion(self, index):
        if isinstance(index, QModelIndex):
            (id, cfg, cur) = self.dlist[index.row()]
        else:
            (id, cfg, cur) = self.dlist[index]
        if cfg == None:
            return
        try:
            dir = cfg[self.newfield[VERSION]]
        except:
            dir = cfg[self.field[VERSION]]
        try:
            h = cfg['history']
            if not dir in h:
                h[:0] = [dir]
            if len(h) > 5:
                h = h[0:5]
        except:
            h = [dir]
        cfg['history'] = h

    #
    # Generate a history list.  In order:
    #    New configuration setting
    #    Current configuration setting
    #    Current running setting
    #    Others in the history list.
    # 
    def history(self, row):
        (id, cfg, cur) = self.dlist[row]
        x = [cfg['dir']]
        try:
            x[:0] = [cfg['newdir']]
        except:
            pass
        try:
            i = cur['dir']
            if not i in x:
                x[len(x):] = [i]
        except:
            pass
        try:
            h = cfg['history']
            for i in h:
                if not i in x:
                    x[len(x):] = [i]
        except:
            pass
        return x

    def getID(self, row):
        (id, cfg, cur) = self.dlist[row]
        return id
