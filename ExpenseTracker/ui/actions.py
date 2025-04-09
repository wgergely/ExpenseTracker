"""Actions Module.

"""
import logging

from PySide6 import QtCore, QtWidgets, QtGui

from ..status import status

logging.basicConfig(level=logging.INFO)


class Signals(QtCore.QObject):
    configFileChanged = QtCore.Signal(str)
    configSectionChanged = QtCore.Signal(str)  # Section, config

    dataAboutToBeFetched = QtCore.Signal()
    dataFetched = QtCore.Signal()

    dataRangeChanged = QtCore.Signal(str, int)  # year-date, span

    categorySelectionChanged = QtCore.Signal()

    statusError = QtCore.Signal(status.Status)

    def __init__(self):
        super().__init__()
        self._connect_signals()

    def _connect_signals(self):
        self.dataRangeChanged.connect(self.categorySelectionChanged)
        self.dataFetched.connect(self.categorySelectionChanged)


# Create a singleton instance of Signals
signals = Signals()


@QtCore.Slot()
def authenticate():
    from ..auth import auth
    from ..ui import parent
    from ..database import database

    msg = 'Are you sure you want to authenticate with Google?'
    reply = QtWidgets.QMessageBox.question(parent(), 'Authenticate', msg,
                                           QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                           QtWidgets.QMessageBox.No)
    if reply == QtWidgets.QMessageBox.No:
        return

    signals.dataAboutToBeFetched.emit()

    database.clear_local_cache()
    auth.authenticate(force=True)
    database.cache_remote_data()

    signals.dataFetched.emit()

    QtWidgets.QMessageBox.information(
        parent(),
        'Authentication',
        'Authentication successful.',
        QtWidgets.QMessageBox.Ok
    )


@QtCore.Slot()
def fetch_data():
    from ..database import database
    from .. import ui

    signals.dataAboutToBeFetched.emit()
    try:
        database.cache_remote_data()
    except Exception as e:
        msg = f'Error fetching data: {str(e)}'
        QtWidgets.QMessageBox.critical(ui.parent(), 'Error', msg,
                                       QtWidgets.QMessageBox.Ok)
        raise RuntimeError('Error fetching data') from e
    finally:
        signals.dataFetched.emit()


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
    try:
        database.clear_local_cache()
        msg = 'Local data cleared successfully.'
        QtWidgets.QMessageBox.information(parent(), 'Clear Data', msg,
                                          QtWidgets.QMessageBox.Ok)
    except Exception as e:
        msg = f'Error clearing local data: {str(e)}'
        QtWidgets.QMessageBox.critical(parent(), 'Error', msg,
                                       QtWidgets.QMessageBox.Ok)
    finally:
        signals.dataFetched.emit()


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
