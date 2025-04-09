from ...ui import ui
from .. import lib

from PySide6 import QtWidgets, QtCore, QtGui


class PresetListView(QtWidgets.QListView):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setContextMenuPolicy(QtCore.Qt.NoContextMenu)


class PresetWidget(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.toolbar = None
        self.view = None

        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )

        ui.set_stylesheet(self)

        self._create_ui()
        self._init_actions()
        self._connect_signals()

    def _create_ui(self):
        QtWidgets.QVBoxLayout(self)
        self.layout().setContentsMargins(0, 0, 0, 0)

        o = ui.Size.Indicator(1.0)
        self.layout().setSpacing(o)

        # Toolbar
        self.toolbar = QtWidgets.QToolBar(self)
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(
            QtCore.QSize(
                ui.Size.Margin(1.0),
                ui.Size.Margin(1.0)
            )
        )

        self.layout().addWidget(self.toolbar, 1)

        # List view
        self.view = PresetListView(self)
        self.layout().addWidget(self.view, 1)

    def _init_actions(self):
        action = QtGui.QAction('Create Preset...', self)
        action.setIcon(ui.get_icon('btn_add'))

        self.toolbar.addAction(action)
        self.addAction(action)

    def _connect_signals(self):
        pass

    def sizeHint(self):
        return QtCore.QSize(
            ui.Size.DefaultWidth(0.66),
            ui.Size.DefaultHeight(0.66)
        )