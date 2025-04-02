from PySide6 import QtCore


class Signals(QtCore.QObject):

    switchViewToggled = QtCore.Signal()
    authenticateRequested = QtCore.Signal(bool)
    reloadRequested = QtCore.Signal(bool)
    showLedgerRequested = QtCore.Signal()
    dataRangeChanged = QtCore.Signal(str, int)

    def __init__(self):
        super().__init__()
        self._connect_signals()

    def _connect_signals(self):
        self.dataRangeChanged.connect(lambda s, i: print(f"Range changed: {s}, {i}"))
        self.switchViewToggled.connect(lambda: print("Switch view toggled"))
        self.authenticateRequested.connect(lambda f: print(f"Authenticate requested: {f}"))
        self.reloadRequested.connect(lambda f: print(f"Reload requested: {f}"))
        self.showLedgerRequested.connect(lambda: print("Show ledger requested"))





signals = Signals()