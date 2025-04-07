"""Actions Module.

"""

from PySide6 import QtCore, QtWidgets


class Signals(QtCore.QObject):
    configSectionChanged = QtCore.Signal(str)  # Section, config

    dataAboutToBeFetched = QtCore.Signal()
    dataFetched = QtCore.Signal()

    dataRangeChanged = QtCore.Signal(str, int)  # year-date, span

    openSpreadsheetRequested = QtCore.Signal()

    categorySelectionChanged = QtCore.Signal()

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
        msg = 'Unauthentication successful.'
        QtWidgets.QMessageBox.information(parent(), 'Unauthentication', msg,
                                          QtWidgets.QMessageBox.Ok)
    except Exception as e:
        msg = f'Error during unauthentication: {str(e)}'
        QtWidgets.QMessageBox.critical(parent(), 'Error', msg,
                                       QtWidgets.QMessageBox.Ok)
    finally:
        database.clear_local_cache()
        signals.dataFetched.emit()


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
