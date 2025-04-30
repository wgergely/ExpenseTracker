"""Actions Module.

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
    configSectionChanged = QtCore.Signal(str)  # Section, config
    metadataChanged = QtCore.Signal(str, object)

    dataFetchRequested = QtCore.Signal()
    dataAboutToBeFetched = QtCore.Signal()
    dataFetched = QtCore.Signal(pandas.DataFrame)

    expenseCategoryChanged = QtCore.Signal(list)
    categoryChanged = QtCore.Signal(str)

    showSettings = QtCore.Signal()
    openSpreadsheet = QtCore.Signal()
    openTransactions = QtCore.Signal()
    showLogs = QtCore.Signal()

    presetsChanged = QtCore.Signal()
    presetAboutToBeActivated = QtCore.Signal()
    presetActivated = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self._connect_signals()

    def _connect_signals(self):
        self.openSpreadsheet.connect(open_spreadsheet)

        from ..core import service
        self.dataFetchRequested.connect(service.fetch_data)

        @QtCore.Slot(str, object)
        def metadata_changed(key: str, value: object) -> None:
            if key != 'theme':
                return

            try:
                from . import ui
                ui.apply_theme()
            except Exception as ex:
                logging.error(f'Error applying theme: {ex}')

        self.metadataChanged.connect(metadata_changed)


# Create a singleton instance of Signals
signals = Signals()
