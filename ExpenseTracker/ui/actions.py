#!/usr/bin/env python3
"""
Actions Module.

Defines the toolbar actions used in the application. In particular, it
groups the authentication actions (Connect/Disconnect) and the data actions
(Reload/Clear Data) under single tool buttons with drop‐down menus.

Actions provided:
  - SwitchViewAction: Toggles between graph and pie-chart views.
  - AuthGroupAction: Main button shows "Connect"; its menu offers "Connect" and "Disconnect".
  - DataGroupAction: Main button shows "Reload"; its menu offers "Reload" and "Clear Data".
  - ShowLedgerAction: Opens the Google spreadsheet (ledger) in the default browser.

Helper functions for actual operations are also provided.
"""

from PySide6 import QtCore, QtWidgets, QtGui

from . import ui


class Signals(QtCore.QObject):
    switchViewToggled = QtCore.Signal()

    authenticateRequested = QtCore.Signal(bool)
    deauthenticateRequested = QtCore.Signal()

    clearDataRequested = QtCore.Signal()

    dataFetchRequested = QtCore.Signal(bool)
    dataAboutToBeFetched = QtCore.Signal()
    dataFetched = QtCore.Signal()

    dataRangeChanged = QtCore.Signal(str, int)  # year-date, span

    openLedgerRequested = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self._connect_signals()

    def _connect_signals(self):
        self.openLedgerRequested.connect(self.show_ledger)
        self.authenticateRequested.connect(self.authenticate)
        self.deauthenticateRequested.connect(self.unauthenticate)

        self.dataFetchRequested.connect(self.fetch_data)
        self.clearDataRequested.connect(self.clear_data)

    @staticmethod
    @QtCore.Slot()
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

    @staticmethod
    @QtCore.Slot(bool)
    def authenticate(force=False):
        """
        Authenticate with Google and load the data.
        """
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
        """
        Unauthenticate with Google.
        """
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
        """
        Load data from Google.
        """
        from ..database import database

        database.get_remote_data()
        signals.dataFetched.emit()

    @staticmethod
    @QtCore.Slot()
    def clear_data():
        """
        Clear local data.
        """
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
        self.setIcon(ui.get_category_icon('btn_switch'))
        self.clicked.connect(signals.switchViewToggled)


class AuthGroupAction(QtWidgets.QToolButton):
    """
    Grouped authentication action.

    The main button shows "Connect" with the authenticate icon.
    Its dropdown menu offers:
      - Connect (with force mode support)
      - Disconnect
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setText('Connect')
        self.setToolTip('Connect to Google')
        self.setIcon(ui.get_category_icon('btn_authenticate'))
        self.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)

        menu = QtWidgets.QMenu(self)
        self.setMenu(menu)

        # "Authenticate" action
        action = QtGui.QAction(parent=menu)
        action.setText('Authenticate')
        action.setToolTip('Authenticate with Google')
        action.setStatusTip('Authenticate with Google')
        action.setIcon(ui.get_category_icon('btn_authenticate'))
        action.triggered.connect(self.emit_authenticate_requested)
        menu.addAction(action)

        # "Unauthenticate" action
        action = QtGui.QAction(parent=menu)
        action.setText('Unauthenticate')
        action.setToolTip('Unauthenticate from Google')
        action.setStatusTip('Unauthenticate from Google')
        action.setIcon(ui.get_category_icon('btn_deauthenticate'))
        action.triggered.connect(signals.deauthenticateRequested)
        menu.addAction(action)

        #
        #
        # # "Connect" action
        # self.connect_action = QtGui.QAction(ui.get_category_icon('btn_authenticate'),
        #                                     'Connect', self)
        # self.connect_action.setToolTip('Connect to Google')
        # menu.addAction(self.connect_action)
        # # "Disconnect" action
        # self.disconnect_action = QtGui.QAction(ui.get_category_icon('btn_deauthenticate'),
        #                                        'Disconnect', self)
        # self.disconnect_action.setToolTip('Disconnect from Google')
        # menu.addAction(self.disconnect_action)
        # self.setMenu(menu)
        #
        # # When the main button is clicked, trigger Connect.
        # self.clicked.connect(self.emit_authenticate_requested)
        # self.connect_action.triggered.connect(self.emit_authenticate_requested)
        # self.disconnect_action.triggered.connect(signals.deauthenticateRequested)

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

    The main button shows "Reload" with the reload icon.
    Its dropdown menu offers:
      - Reload (with force mode support)
      - Clear Data
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setText('Reload')
        self.setToolTip('Reload data from Google')
        self.setIcon(ui.get_category_icon('btn_reload'))
        self.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)

        # Create the menu
        menu = QtWidgets.QMenu(self)
        self.setMenu(menu)

        # "Reload" action
        action = QtGui.QAction(parent=menu)
        action.setText('Reload Data')
        action.setToolTip('Reload data from Google')
        action.setStatusTip('Reload data from Google')
        action.setIcon(ui.get_category_icon('btn_reload'))
        action.triggered.connect(self.emit_data_fetch_requested)
        menu.addAction(action)

        # "Clear Data" action
        action = QtGui.QAction(parent=menu)
        action.setText('Clear Data')
        action.setToolTip('Clear local data')
        action.setStatusTip('Clear local data')
        action.setIcon(ui.get_category_icon('btn_clear'))
        action.triggered.connect(signals.clearDataRequested)
        menu.addAction(action)

    @QtCore.Slot()
    def emit_data_fetch_requested(self):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        force = bool(modifiers & (QtCore.Qt.ShiftModifier |
                                  QtCore.Qt.AltModifier |
                                  QtCore.Qt.ControlModifier))
        signals.dataFetchRequested.emit(force)


class ShowLedgerAction(QtWidgets.QToolButton):
    """
    Button to open the Google spreadsheet (ledger) in the default browser.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText('Open Ledger')
        self.setToolTip('Open Ledger')
        self.setIcon(ui.get_category_icon('btn_ledger'))
        self.clicked.connect(signals.openLedgerRequested)
