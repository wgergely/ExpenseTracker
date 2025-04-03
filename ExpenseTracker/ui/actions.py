"""Actions Module.

"""

from PySide6 import QtCore, QtWidgets, QtGui

from . import ui


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
        from .signals import signals
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
        from .signals import signals

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
        from .signals import signals

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
        from .signals import signals
        signals.showLedgerRequested.emit()



def show_ledger():
    """
    Open the Google spreadsheet (ledger) in the default browser.
    """
    from ..database import database
    config = database.load_config()
    spreadsheet_id = config.get('id', None)
    if not spreadsheet_id:
        raise ValueError("No spreadsheet ID found in the configuration.")

    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))


def authenticate():
    """
    Authenticate with Google and load the data.
    """
    from ..auth import auth

    # Perform authentication
    # show prompt
    msg = 'Are you sure you want to authenticate with Google?'
    reply = QtWidgets.QMessageBox.question(None, 'Authenticate', msg,
                                           QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                           QtWidgets.QMessageBox.No)
    if reply == QtWidgets.QMessageBox.No:
        return

    auth.authenticate(force=True)

    msg = 'Authentication successful.'
    QtWidgets.QMessageBox.information(None, 'Authentication', msg,
                                        QtWidgets.QMessageBox.Ok)

def reload_data():
    """
    Load data from Google.
    """
    from ..database import database

    # Load the data
    database.get_remote_data()

    from .signals import signals
    signals.dataFetched.emit()
