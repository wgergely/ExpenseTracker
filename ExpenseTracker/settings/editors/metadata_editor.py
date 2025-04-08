from PySide6 import QtCore, QtGui, QtWidgets

from ...ui import ui
from ..import lib
from ...ui.actions import signals



class MetadataEditor(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.locale_editor = None
        self.currency_editor = None
        self.summary_mode_editor = None
        self.hide_empty_editor = None

        self.text_changed_timer = QtCore.QTimer(self)
        self.text_changed_timer.setSingleShot(True)
        self.text_changed_timer.setInterval(QtWidgets.QApplication.keyboardInputInterval())

        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Maximum
        )

        self._create_ui()
        self._init_actions()
        self._connect_signals()

    def _create_ui(self):
        QtWidgets.QFormLayout(self)
        self.layout().setContentsMargins(0, 0, 0, 0)
        o = ui.Size.Indicator(1.0)