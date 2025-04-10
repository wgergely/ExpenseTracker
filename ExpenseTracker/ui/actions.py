"""Actions Module.

"""
import logging

import pandas
from PySide6 import QtCore, QtWidgets, QtGui

from ..status import status




class Signals(QtCore.QObject):
    configFileChanged = QtCore.Signal(str)
    configSectionChanged = QtCore.Signal(str)  # Section, config

    dataFetchRequested = QtCore.Signal()

    dataAboutToBeFetched = QtCore.Signal()
    dataFetched = QtCore.Signal(pandas.DataFrame)
    dataReady = QtCore.Signal(pandas.DataFrame)

    dataRangeChanged = QtCore.Signal(str, int)  # year-date, span

    categorySelectionChanged = QtCore.Signal()

    statusError = QtCore.Signal(status.Status)

    def __init__(self):
        super().__init__()
        self._connect_signals()

    def _connect_signals(self):
        self.dataRangeChanged.connect(self.categorySelectionChanged)
        self.dataFetched.connect(self.categorySelectionChanged)

        self.dataFetched.connect(lambda df: logging.info(f'Data fetched [{df.shape[0]} rows, {df.shape[1]} columns]'))
        self.dataReady.connect(lambda df: logging.info(f'Data ready [{df.shape[0]} rows, {df.shape[1]} columns]'))


# Create a singleton instance of Signals
signals = Signals()



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
    logging.info(f'Opening spreadsheet: {url}')
    QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))
