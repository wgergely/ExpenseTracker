"""Actions Module.

"""

from PySide6 import QtCore, QtWidgets

from . import ui
from .signals import signals

class SwitchViewAction(QtWidgets.QToolButton):
    """
    Button to toggle between graph and pie-chart views.
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setText('Switch View')
        self.setToolTip('Switch View')
        self.setIcon(ui.get_category_icon('btn_switch'))
        self.clicked.connect(self.on_clicked)

    @QtCore.Slot()
    def on_clicked(self):
        signals.switchViewToggled.emit()


class AuthenticateAction(QtWidgets.QToolButton):
    """
    Button to authenticate with Google.

    Supports "force" mode if shift, alt, or control is pressed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText('Authenticate')
        self.setToolTip('Authenticate with Google')
        self.setIcon(ui.get_category_icon('btn_authenticate'))

        self.clicked.connect(self.on_clicked)

    @QtCore.Slot()
    def on_clicked(self, checked=False):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        force = bool(modifiers & (QtCore.Qt.ShiftModifier |
                                  QtCore.Qt.AltModifier |
                                  QtCore.Qt.ControlModifier))
        signals.authenticateRequested.emit(force)



class ReloadAction(QtWidgets.QToolButton):
    """
    Button to reload data from Google.

    Supports "force" mode if shift, alt, or control is pressed.
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setText('Reload')
        self.setToolTip('Reload data from Google')
        self.setIcon(ui.get_category_icon('btn_reload'))
        self.clicked.connect(self.on_clicked)

    @QtCore.Slot()
    def on_clicked(self, checked=False):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        force = bool(modifiers & (QtCore.Qt.ShiftModifier |
                                  QtCore.Qt.AltModifier |
                                  QtCore.Qt.ControlModifier))
        signals.reloadRequested.emit(force)


class ShowLedgerAction(QtWidgets.QToolButton):
    """
    Button to open the Google spreadsheet (ledger) in the default browser.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("Show Ledger")
        self.setToolTip("Show Ledger")
        self.setIcon(ui.get_category_icon('btn_ledger'))
        self.clicked.connect(self.on_clicked)

    @QtCore.Slot()
    def on_clicked(self):
        signals.showLedgerRequested.emit()
