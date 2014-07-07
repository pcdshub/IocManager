from PyQt4.QtGui import *
from PyQt4.QtCore import *
import utils

IOCNAME = 0
HOST    = 1
PORT    = 2
VERSION = 3
STATUS  = 4
EXTRA   = 5

class MyModel(QAbstractTableModel): 
    def __init__(self, hutch, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self.hutch = hutch
        self.data = utils.getAllStatus(hutch)
        self.headerdata = ["IOC Name", "Host", "Port", "Version", "Status", "Information"]
        self.field      = [None, 'host', 'port', 'dir', None, None]
        self.newfield   = [None, 'newhost', 'newport', 'newdir', None, None]

    def flags(self, index):
        c = index.column()
        if c == IOCNAME or c == STATUS or c == EXTRA:
            return Qt.ItemIsEnabled
        else:
            return Qt.ItemIsEnabled | Qt.ItemIsEditable

    def setData(self, index, value, role=Qt.EditRole):
        (id, cfg, cur) = self.data[index.row()]
        if cfg == None:
            return False
        c = index.column()
        val = value.toString()
        cfg[self.newfield[c]] = val
        if cfg[self.newfield[c]] == cfg[self.field[c]]:
            del cfg[self.newfield[c]]
        self.dataChanged.emit(index, index)
        return True
 
    def rowCount(self, parent): 
        return len(self.data)
 
    def columnCount(self, parent): 
        return len(self.headerdata)

    def value(self, rowtuple, c):
        (id, cfg, cur) = rowtuple
        if c == IOCNAME:
            return QVariant(id)
        elif c == STATUS:
            try:
                return QVariant(cur['status'])
            except:
                return QVariant("NOCONNECT")
        elif c == EXTRA:
            if cfg == None or cur == None:
                return QVariant()
            v = ""
            if cfg['dir'] != cur['dir']:
                v = cur['dir'] + " "
            if cfg['host'] != cur['host'] or cfg['port'] != cur['port']:
                v += "on " + cur['host'] + ":" + cur['port']
            return QVariant(v)
        else:
            if cfg == None:
                return QVariant(cur[self.field[c]])
            try:
                return QVariant(cfg[self.newfield[c]])
            except:
                return QVariant(cfg[self.field[c]])
        return QVariant()
 
    def data(self, index, role): 
        if not index.isValid(): 
            return QVariant() 
        elif role == Qt.DisplayRole or role == Qt.EditRole:
            return self.value(self.data[index.row()], index.column())
        elif role == Qt.ForegroundRole:
            c = index.column()
            (id, cfg, cur) = self.data[index.row()]
            if cfg == None:
                return QVariant(QBrush(Qt.red))
            try:
                v = cfg[self.newfield[c]]
                return QVariant(QBrush(Qt.blue))
            except:
                return QVariant()
        elif role == Qt.BackgroundRole:
            c = index.column()
            if c != STATUS:
                return QVariant()
            (id, cfg, cur) = self.data[index.row()]
            if cur == None:
                return QVariant(QBrush(Qt.red))
            if cfg == None:
                return QVariant()
            if (cfg['host'] != cur['host'] or cfg['port'] != cur['port'] or
                cfg['dir'] != cur['dir']):
                return QVariant(QBrush(Qt.yellow))
            return QVariant(QBrush(Qt.green))
        else:
            return QVariant()

    def headerData(self, col, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return QVariant(self.headerdata[col])
        return QVariant()

    def sort(self, Ncol, order):
        self.emit(SIGNAL("layoutAboutToBeChanged()"))
        if Ncol == PORT:
            self.data = sorted(self.data, key=lambda rowtuple: int(self.value(rowtuple, Ncol).toString()))
        else:
            self.data = sorted(self.data, key=lambda rowtuple: self.value(rowtuple, Ncol).toString())
        if order == Qt.DescendingOrder:
            self.data.reverse()
        self.emit(SIGNAL("layoutChanged()"))

    def doApply(self):
        f = open(utils.CONFIG_DIR + self.hutch, "w")
        f.write("procmgr_config = [\n")
        for (id, cfg, cur) in self.data:
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
            f.write(" {id:'%s', host: '%s', port: '%s', dir: '%s'},\n" %
                    (id, host, port, dir))
        f.write("]\n");
        f.close()
        utils.applyConfig(self.hutch)
        self.emit(SIGNAL("layoutAboutToBeChanged()"))
        self.data = utils.getAllStatus(self.hutch)
        self.emit(SIGNAL("layoutChanged()"))
        
    def doRevert(self):
        for (id, cfg, cur) in self.data:
            for f in self.newfield:
                try:
                    if f != None:
                        del cfg[f]
                except:
                    pass
        self.dataChanged.emit(self.index(0,0), self.index(len(self.data),len(self.headerdata)))

    def inConfig(self, index):
        (id, cfg, cur) = self.data[index.row()]
        return cfg != None
        pass

    def notSynched(self, index):
        (id, cfg, cur) = self.data[index.row()]
        if cfg == None or cur == None:
            return False
        return (cfg['dir'] != cur['dir'] or cfg['host'] != cur['host'] or
                cfg['port'] != cur['port'])

    def isChanged(self, index):
        (id, cfg, cur) = self.data[index.row()]
        if cfg == None:
            return False
        keys = cfg.keys()
        return 'newhost' in keys or 'newport' in keys or 'newdir' in keys

    def revertIOC(self, index):
        (id, cfg, cur) = self.data[index.row()]
        for f in self.newfield:
            try:
                if f != None:
                    del cfg[f]
            except:
                pass
        self.dataChanged.emit(self.index(index.row(),0),
                              self.index(index.row(),len(self.headerdata)))

    def deleteIOC(self, index):
        (id, cfg, cur) = self.data[index.row()]
        if cur != None:
            self.data[index.row()] = (id, None, cur)
            self.dataChanged.emit(self.index(index.row(),0),
                                  self.index(index.row(),len(self.headerdata)))
        else:
            self.emit(SIGNAL("layoutAboutToBeChanged()"))
            self.data = self.data[0:index.row()]+self.data[index.row()+1:]
            self.emit(SIGNAL("layoutChanged()"))

    def setFromRunning(self, index):
        (id, cfg, cur) = self.data[index.row()]
        for f in ['dir', 'host', 'port']:
            if cfg[f] != cur[f]:
                cfg['new'+f] = cur[f]
        self.dataChanged.emit(self.index(index.row(),0),
                              self.index(index.row(),len(self.headerdata)))
        

    def addExisting(self, index):
        (id, cfg, cur) = self.data[index.row()]
        cfg = {'id': id, 'host': cur['host'], 'port': cur['port'], 'dir': cur['dir']}
        self.data[index.row()] = (id, cfg, cur)
        self.dataChanged.emit(self.index(index.row(),0),
                              self.index(index.row(),len(self.headerdata)))
        

    def addIOC(self, id, host, port, dir):
        self.emit(SIGNAL("layoutAboutToBeChanged()"))
        cfg = {'id': id, 'host': host, 'port': port, 'dir': dir}
        cur = utils.getCurrentStatus(host, port)
        self.data.append((id, cfg, cur))
        self.emit(SIGNAL("layoutChanged()"))
