# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'details.ui'
#
# Created: Tue Sep 30 16:25:43 2014
#      by: PyQt4 UI code generator 4.9.1
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    _fromUtf8 = lambda s: s

class Ui_Dialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName(_fromUtf8("Dialog"))
        Dialog.resize(417, 171)
        self.gridLayout = QtGui.QGridLayout(Dialog)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label_3 = QtGui.QLabel(Dialog)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout.addWidget(self.label_3, 0, 0, 1, 1)
        self.aliasEdit = QtGui.QLineEdit(Dialog)
        self.aliasEdit.setObjectName(_fromUtf8("aliasEdit"))
        self.gridLayout.addWidget(self.aliasEdit, 0, 1, 1, 1)
        self.label = QtGui.QLabel(Dialog)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 1, 0, 1, 1)
        self.cmdEdit = QtGui.QLineEdit(Dialog)
        self.cmdEdit.setObjectName(_fromUtf8("cmdEdit"))
        self.gridLayout.addWidget(self.cmdEdit, 1, 1, 1, 1)
        self.flagCheckBox = QtGui.QCheckBox(Dialog)
        self.flagCheckBox.setObjectName(_fromUtf8("flagCheckBox"))
        self.gridLayout.addWidget(self.flagCheckBox, 2, 0, 1, 2)
        self.label_2 = QtGui.QLabel(Dialog)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 3, 0, 1, 1)
        self.delayEdit = QtGui.QLineEdit(Dialog)
        self.delayEdit.setObjectName(_fromUtf8("delayEdit"))
        self.gridLayout.addWidget(self.delayEdit, 3, 1, 1, 1)
        self.buttonBox = QtGui.QDialogButtonBox(Dialog)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Cancel|QtGui.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName(_fromUtf8("buttonBox"))
        self.gridLayout.addWidget(self.buttonBox, 4, 0, 1, 2)

        self.retranslateUi(Dialog)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL(_fromUtf8("accepted()")), Dialog.accept)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL(_fromUtf8("rejected()")), Dialog.reject)
        QtCore.QMetaObject.connectSlotsByName(Dialog)

    def retranslateUi(self, Dialog):
        Dialog.setWindowTitle(QtGui.QApplication.translate("Dialog", "Dialog", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("Dialog", "IOC Alias:", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Dialog", "Command:", None, QtGui.QApplication.UnicodeUTF8))
        self.flagCheckBox.setText(QtGui.QApplication.translate("Dialog", "Append IOC Name to Command", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Dialog", "Delay after Start (sec):", None, QtGui.QApplication.UnicodeUTF8))

