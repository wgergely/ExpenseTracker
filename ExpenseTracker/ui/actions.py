"""Application-wide Qt signals and utility slots for ExpenseTracker.

This module provides:
    - open_spreadsheet slot: opens the configured Google Sheets URL in the browser.
    - Signals: custom Qt signals for configuration changes, data fetch lifecycle,
      category selection, UI actions (showSettings, showTransactions, showLogs), and presets.
"""
import logging

import pandas
from PySide6 import QtCore, QtWidgets, QtGui


@QtCore.Slot()
def open_spreadsheet() -> None:
    """
    Opens the spreadsheet in the default browser.
    """
    from ..settings import lib

    config = lib.settings.get_section('spreadsheet')

    try:
        spreadsheet_id: str = config['id']
        sheet_name: str = config['worksheet']
    except Exception as ex:
        logging.error(f'Error retrieving spreadsheet config: {ex}')
        QtWidgets.QMessageBox.critical(None, 'Error', 'Invalid spreadsheet configuration.')
        raise

    url: str = f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid=0'
    if sheet_name:
        url += f'&sheet={sheet_name}'
    logging.debug(f'Opening spreadsheet: {url}')
    QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))


class Signals(QtCore.QObject):
    """Centralized Qt signals for application config, data, and UI events."""
    initializationRequested = QtCore.Signal()

    authenticationRequested = QtCore.Signal()

    configSectionChanged = QtCore.Signal(str)  # Section, config
    metadataChanged = QtCore.Signal(str, object)

    dataFetchRequested = QtCore.Signal()
    dataAboutToBeFetched = QtCore.Signal()
    dataFetched = QtCore.Signal(pandas.DataFrame)

    transactionsChanged = QtCore.Signal(list)
    transactionItemSelected = QtCore.Signal(int)

    categoryChanged = QtCore.Signal(str)
    categoryUpdateRequested = QtCore.Signal(str)

    openSpreadsheet = QtCore.Signal()

    showSettings = QtCore.Signal()
    showTransactions = QtCore.Signal()
    showLogs = QtCore.Signal()
    showTransactionPreview = QtCore.Signal()

    presetsChanged = QtCore.Signal()
    presetAboutToBeActivated = QtCore.Signal()
    presetActivated = QtCore.Signal()

    categoryAdded = QtCore.Signal(str, int)
    categoryRemoved = QtCore.Signal(str, int)
    categoryOrderChanged = QtCore.Signal(str, int, int)
    categoryPaletteChanged = QtCore.Signal(str)
    categoryExcluded = QtCore.Signal(str)

    error = QtCore.Signal(str)

    def __init__(self):
        super().__init__()
        self._connect_signals()

    def _connect_signals(self):
        self.openSpreadsheet.connect(open_spreadsheet)

        from ..core import service
        self.dataFetchRequested.connect(service.fetch_data)

        # Handle authentication requests emitted by background workers
        @QtCore.Slot()
        def _on_authentication_requested() -> None:
            try:
                from ..core.auth import auth_manager
                auth_manager.refresh_credentials_interactive()
            except Exception as ex:
                QtWidgets.QMessageBox.critical(None, 'Authentication Failed', str(ex))
                return
            # Retry data fetch after successful authentication
            self.dataFetchRequested.emit()

        self.authenticationRequested.connect(_on_authentication_requested)

        @QtCore.Slot(str, object)
        def metadata_changed(key: str, value: object) -> None:
            if key != 'theme':
                return

            try:
                from . import ui
                ui.apply_theme()
            except Exception as ex:
                logging.debug(f'Error applying theme: {ex}')

        self.metadataChanged.connect(metadata_changed)


signals = Signals()
