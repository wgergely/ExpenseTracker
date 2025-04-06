#!/usr/bin/env python3
"""
Actions Module.

Defines the toolbar actions used in the application. In particular, it
groups the authentication actions (Connect/Disconnect) and the data actions
(Reload/Clear Data) under single tool buttons with drop‐down menus.
"""

from PySide6 import QtCore, QtWidgets, QtGui

from . import ui


class Signals(QtCore.QObject):
    configSectionChanged = QtCore.Signal(str) # Section, config

    switchViewToggled = QtCore.Signal()

    authenticateRequested = QtCore.Signal(bool)
    deauthenticateRequested = QtCore.Signal()

    clearDataRequested = QtCore.Signal()

    dataFetchRequested = QtCore.Signal(bool)
    dataAboutToBeFetched = QtCore.Signal()
    dataFetched = QtCore.Signal()

    dataRangeChanged = QtCore.Signal(str, int)  # year-date, span

    openSpreadsheetRequested = QtCore.Signal()

    categorySelectionChanged = QtCore.Signal()

    # New signals for sorting/filtering
    sortExpenseRequested = QtCore.Signal(int, bool)        # column, ascending?
    sortTransactionRequested = QtCore.Signal(int, bool)    # column, ascending?
    filterTransactionsRequested = QtCore.Signal(str)

    def __init__(self):
        super().__init__()
        self._connect_signals()

    def _connect_signals(self):
        self.authenticateRequested.connect(self.authenticate)
        self.deauthenticateRequested.connect(self.unauthenticate)

        self.dataFetchRequested.connect(self.fetch_data)
        self.clearDataRequested.connect(self.clear_data)

        self.dataRangeChanged.connect(self.categorySelectionChanged)
        self.dataFetched.connect(self.categorySelectionChanged)

        self.configSectionChanged.connect(lambda s: print(f'Config section changed: {s}'))


    @staticmethod
    @QtCore.Slot(bool)
    def authenticate(force=False):
        from ..auth import auth
        from ..ui import parent

        msg = 'Are you sure you want to authenticate with Google?'
        reply = QtWidgets.QMessageBox.question(parent(), 'Authenticate', msg,
                                               QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                               QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.No:
            return

        auth.authenticate(force=True)
        msg = 'Authentication successful.'
        QtWidgets.QMessageBox.information(parent(), 'Authentication', msg,
                                          QtWidgets.QMessageBox.Ok)

    @staticmethod
    @QtCore.Slot()
    def unauthenticate():
        from ..auth import auth
        from ..database import database
        from ..ui import parent

        msg = 'Are you sure you want to disconnect from the current Google account?'
        reply = QtWidgets.QMessageBox.question(parent(), 'Unauthenticate', msg,
                                               QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                               QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.No:
            return

        signals.dataAboutToBeFetched.emit()
        try:
            auth.unauthenticate()
        except Exception as e:
            msg = f'Error during unauthentication: {str(e)}'
            QtWidgets.QMessageBox.critical(parent(), 'Error', msg,
                                           QtWidgets.QMessageBox.Ok)
            return

        database.clear_local_cache()
        signals.dataFetched.emit()

        msg = 'Unauthentication successful.'
        QtWidgets.QMessageBox.information(parent(), 'Unauthentication', msg,
                                          QtWidgets.QMessageBox.Ok)

    @staticmethod
    @QtCore.Slot()
    def fetch_data():
        from ..database import database

        database.get_remote_data()
        signals.dataFetched.emit()

    @staticmethod
    @QtCore.Slot()
    def clear_data():
        from ..database import database
        from ..ui import parent

        msg = 'Are you sure you want to clear all local data?'
        reply = QtWidgets.QMessageBox.question(parent(), 'Clear Data', msg,
                                               QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                               QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.No:
            return

        signals.dataAboutToBeFetched.emit()
        database.clear_local_cache()
        signals.dataFetched.emit()
        msg = 'Local data cleared successfully.'
        QtWidgets.QMessageBox.information(parent(), 'Clear Data', msg,
                                          QtWidgets.QMessageBox.Ok)


# Create a singleton instance of Signals
signals = Signals()


class SwitchViewAction(QtWidgets.QToolButton):
    """
    Button to toggle between graph and pie-chart views.
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setText('Switch View')
        self.setToolTip('Switch View')
        self.setIcon(ui.get_icon('btn_switch'))
        self.clicked.connect(signals.switchViewToggled)


class AuthGroupAction(QtWidgets.QToolButton):
    """
    Grouped authentication action.
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setText('Connect')
        self.setToolTip('Connect to Google')
        self.setIcon(ui.get_icon('btn_authenticate'))
        self.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)

        menu = QtWidgets.QMenu(self)
        self.setMenu(menu)

        action = QtGui.QAction(parent=menu)
        action.setText('Authenticate')
        action.setToolTip('Authenticate with Google')
        action.setStatusTip('Authenticate with Google')
        action.setIcon(ui.get_icon('btn_authenticate'))
        action.triggered.connect(self.emit_authenticate_requested)
        menu.addAction(action)

        action = QtGui.QAction(parent=menu)
        action.setText('Unauthenticate')
        action.setToolTip('Unauthenticate from Google')
        action.setStatusTip('Unauthenticate from Google')
        action.setIcon(ui.get_icon('btn_deauthenticate'))
        action.triggered.connect(signals.deauthenticateRequested)
        menu.addAction(action)

    @QtCore.Slot()
    def emit_authenticate_requested(self):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        force = bool(modifiers & (QtCore.Qt.ShiftModifier |
                                  QtCore.Qt.AltModifier |
                                  QtCore.Qt.ControlModifier))
        signals.authenticateRequested.emit(force)


class DataGroupAction(QtWidgets.QToolButton):
    """
    Grouped data action.
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setText('Reload')
        self.setToolTip('Reload data from Google')
        self.setIcon(ui.get_icon('btn_reload'))
        self.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)

        menu = QtWidgets.QMenu(self)
        self.setMenu(menu)

        action = QtGui.QAction(parent=menu)
        action.setText('Reload Data')
        action.setToolTip('Reload data from Google')
        action.setStatusTip('Reload data from Google')
        action.setIcon(ui.get_icon('btn_reload'))
        action.triggered.connect(self.emit_data_fetch_requested)
        menu.addAction(action)

        action = QtGui.QAction(parent=menu)
        action.setText('Clear Data')
        action.setToolTip('Clear local data')
        action.setStatusTip('Clear local data')
        action.setIcon(ui.get_icon('btn_clear'))
        action.triggered.connect(signals.clearDataRequested)
        menu.addAction(action)

    @QtCore.Slot()
    def emit_data_fetch_requested(self):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        force = bool(modifiers & (QtCore.Qt.ShiftModifier |
                                  QtCore.Qt.AltModifier |
                                  QtCore.Qt.ControlModifier))
        signals.dataFetchRequested.emit(force)
