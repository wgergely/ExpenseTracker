"""Actions Module.

"""
import logging

import pandas
from PySide6 import QtCore, QtWidgets, QtGui

from ..status import status


@QtCore.Slot()
def open_spreadsheet(self) -> None:
    """
    Opens the spreadsheet in the default browser.
    """
    from ..settings import lib
    from .. import ui

    config = lib.settings.get_section('spreadsheet')

    try:
        spreadsheet_id: str = config['id']
        sheet_name: str = config['worksheet']
    except Exception as ex:
        logging.error(f'Error retrieving spreadsheet config: {ex}')
        QtWidgets.QMessageBox.critical(ui.parent(), 'Error', 'Invalid spreadsheet configuration.')
        raise

    url: str = f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid=0'
    if sheet_name:
        url += f'&sheet={sheet_name}'
    logging.debug(f'Opening spreadsheet: {url}')
    QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))


class Signals(QtCore.QObject):
    configFileChanged = QtCore.Signal(str)
    configSectionChanged = QtCore.Signal(str)  # Section, config

    dataFetchRequested = QtCore.Signal()
    dataAboutToBeFetched = QtCore.Signal()
    dataFetched = QtCore.Signal(pandas.DataFrame)

    dataRangeChanged = QtCore.Signal(str, int)  # year-date, span

    expenseCategoryChanged = QtCore.Signal(list)
    categoryChanged = QtCore.Signal(str)

    statusError = QtCore.Signal(status.Status)

    showSettings = QtCore.Signal()
    openSpreadsheet = QtCore.Signal()
    openTransactions = QtCore.Signal()
    showLogs = QtCore.Signal()

    themeChanged = QtCore.Signal(str)
    calculationChanged = QtCore.Signal()

    presetsChanged = QtCore.Signal()
    presetActivated = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self._connect_signals()

    def _connect_signals(self):
        self.openSpreadsheet.connect(open_spreadsheet)

        from ..core import service
        self.dataFetchRequested.connect(service.fetch_data)

        from . import ui
        self.themeChanged.connect(ui.apply_theme)

        @QtCore.Slot()
        def emit_changed_signals():
            from ..settings import lib
            for section in lib.LEDGER_SCHEMA.keys():
                self.configSectionChanged.emit(section)
            self.themeChanged.emit(lib.settings['theme'])
            QtCore.QTimer.singleShot(100, self.dataFetchRequested.emit)

        self.presetActivated.connect(emit_changed_signals)


# Create a singleton instance of Signals
signals = Signals()
