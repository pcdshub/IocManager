from PyQt4.QtGui import *
from PyQt4.QtCore import *
import MyModel
import hostname_ui

class hostnamedialog(QDialog):
    def __init__(self, parent=None):
      QWidget.__init__(self, parent)
      self.ui = hostname_ui.Ui_Dialog()
      self.ui.setupUi(self)

class MyDelegate(QStyledItemDelegate):
    def __init__(self, parent):
        QStyledItemDelegate.__init__(self, parent)
        self.boxsize = None
        self.hostdialog = hostnamedialog(parent)

    def createEditor(self, parent, option, index):
        col = index.column()
        if col == MyModel.HOST:
            editor = QComboBox(parent)
            editor.setAutoFillBackground(True)
            self.connect(editor, SIGNAL("currentIndexChanged(int)"), lambda n: self.do_commit(n, editor))
            items = index.model().hosts
            for item in items:
                editor.addItem(item)
            editor.lastitem = editor.count()
            editor.addItem("New Host")
            if self.boxsize == None:
                self.boxsize = QSize(150, 25)
            return editor
        return QStyledItemDelegate.createEditor(self, parent, option, index)

    def setEditorData(self, editor, index):
        col = index.column()
        if col == MyModel.HOST:
            value = index.model().data(index, Qt.EditRole).toString()
            try:
                idx = index.model().hosts.index(value)
                editor.setCurrentIndex(idx)
            except:
                editor.setCurrentIndex(editor.lastitem)
        else:
            QStyledItemDelegate.setEditorData(self, editor, index)

    def setModelData(self, editor, model, index):
        col = index.column()
        if col == MyModel.HOST:
            idx = editor.currentIndex()
            if idx == editor.lastitem:
                # Pick a new hostname!
                if self.hostdialog.exec_() == QDialog.Accepted:
                    value = self.hostdialog.ui.hostname.text()
                    if not value in model.hosts:
                        model.hosts.append(value)
                        model.hosts.sort()
                        for i in range(len(model.hosts)):
                            editor.setItemText(i, model.hosts[i])
                        editor.lastitem = editor.count()
                        editor.addItem("New Host")
                    editor.setCurrentIndex(model.hosts.index(value))
                    model.setData(index, QVariant(value), Qt.EditRole)
                else:
                    self.setEditorData(editor, index)  # Restore the original value!
            else:
                model.setData(index, QVariant(index.model().hosts[idx]), Qt.EditRole)
        else:
            QStyledItemDelegate.setModelData(self, editor, model, index)

    def sizeHint(self, option, index):
        col = index.column()
        if col == MyModel.HOST:
            if self.boxsize == None:
                result = QSize(150, 25)
            else:
                result = self.boxsize
        else:
            result = QStyledItemDelegate.sizeHint(self, option, index)
        return result

    def do_commit(self, n, editor):
        self.emit(SIGNAL("commitData(QWidget*)"), editor)
    
