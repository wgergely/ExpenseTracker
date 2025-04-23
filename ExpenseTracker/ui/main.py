from PySide6 import QtWidgets, QtCore, QtGui

from . import ui
from .yearmonth import RangeSelectorBar
from ..core import database
from ..data.view.expense import ExpenseView
from ..data.view.transaction import TransactionsWidget
from ..settings.presets.view import PresetsDockWidget
from ..ui.actions import signals

main_window = None


def show_main_window():
    global main_window
    if main_window is None:
        main_window = MainWindow()
    main_window.show()
    return main_window


class StatusIndicator(QtWidgets.QWidget):
    """Custom status indicator widget.

    """
    clicked = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setObjectName('ExpenseTrackerStatusIndicator')

        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.setFixedSize(
            ui.Size.RowHeight(1.0),
            ui.Size.RowHeight(1.0)
        )

        self._status = database.CacheState.Uninitialized
        self._connect_signals()

        QtCore.QTimer.singleShot(0, self.update_status)

    def _connect_signals(self):
        self.clicked.connect(self.action)

        signals.configFileChanged.connect(self.update_status)
        signals.configSectionChanged.connect(self.update_status)
        signals.dataAboutToBeFetched.connect(self.update_status)
        signals.dataFetched.connect(self.update_status)
        signals.presetsChanged.connect(self.update_status)
        signals.presetActivated.connect(self.update_status)

    def mouseReleaseEvent(self, event):
        if not self.rect().contains(event.pos()):
            super().mouseReleaseEvent(event)
            return

        if event.button() == QtCore.Qt.LeftButton or event.button() == QtCore.Qt.RightButton:
            self.clicked.emit()
            return

        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        option = QtWidgets.QStyleOption()
        option.initFrom(self)

        hover = option.state & QtWidgets.QStyle.State_MouseOver
        pressed = option.state & QtWidgets.QStyle.State_Sunken

        if self._status == database.CacheState.Valid:
            icon = ui.get_icon('btn_ok', color=ui.Color.Green())
            color = ui.Color.Transparent()
        else:
            color = ui.Color.Yellow()
            icon = ui.get_icon('btn_alert', color=color)

        if hover or pressed:
            color = color.lighter(150)

        rect = self.rect()
        center = self.rect().center()

        rect = QtCore.QRect(
            0, 0,
            ui.Size.Margin(1.2), ui.Size.Margin(1.2)
        )
        rect.moveCenter(center)

        if hover or pressed:
            painter.setOpacity(0.4)
        else:
            painter.setOpacity(0.3)

        pen = QtGui.QPen(color.lighter(150))
        pen.setWidth(ui.Size.Separator(2.0))
        painter.setPen(pen)
        painter.setBrush(color)
        painter.drawRoundedRect(
            rect,
            rect.height() * 0.5,
            rect.height() * 0.5,
        )

        rect = QtCore.QRect(
            0, 0,
            ui.Size.Margin(1.0), ui.Size.Margin(1.0)
        )
        rect.moveCenter(center)

        painter.setOpacity(1.0)
        icon.paint(painter, rect, QtCore.Qt.AlignCenter)

        painter.end()

    @QtCore.Slot()
    def update_status(self):
        from ..core.database import database as db
        self._status = db.get_state()

    @QtCore.Slot()
    def action(self):
        self.update_status()
        QtWidgets.QMessageBox.critical(self, 'Error', self._status.value)


class MainWindow(QtWidgets.QMainWindow):
    """The primary window for the Expense Tracker."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName('ExpenseTrackerMainWindow')
        self.setWindowTitle('Expense Tracker')

        self.toolbar = None
        self.range_selector = None
        self.expense_view = None
        self.transactions_view = None
        self.presets_popup = None
        self.status_indicator = None

        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self._create_ui()
        self._init_actions()
        self._connect_signals()

    def _create_ui(self):
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)

        central = QtWidgets.QWidget(self)
        QtWidgets.QVBoxLayout(central)

        o = ui.Size.Margin(1.0)
        central.layout().setContentsMargins(o, o, o, o)
        central.layout().setSpacing(ui.Size.Margin(0.5))

        self.setCentralWidget(central)

        # Action bar at the top.
        self.toolbar = QtWidgets.QToolBar(self)
        self.toolbar.setObjectName('ExpenseTrackerActionToolBar')
        central.layout().addWidget(self.toolbar, 1)

        self.range_selector = RangeSelectorBar(parent=self)
        self.range_selector.setObjectName('ExpenseTrackerRangeSelector')
        self.toolbar.addWidget(self.range_selector)

        self.expense_view = ExpenseView(parent=central)
        self.expense_view.setObjectName('ExpenseTrackerExpenseView')
        central.layout().addWidget(self.expense_view, 1)

        self.status_indicator = StatusIndicator(parent=self)

        self.transactions_view = TransactionsWidget(parent=self)
        self.transactions_view.setObjectName('ExpenseTrackerTransactionsView')

        # Add transactions dock (right side)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.transactions_view)
        self.transactions_view.hide()

        # Add presets dock (left side)
        self.presets_view = PresetsDockWidget(parent=self)
        self.presets_view.setObjectName('ExpenseTrackerPresetsDockWidget')
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.presets_view)
        self.presets_view.hide()

    def _connect_signals(self):
        signals.openTransactions.connect(
            lambda: self.transactions_view.setHidden(not self.transactions_view.isHidden()))

    def _init_actions(self):
        # stretch
        stretch = QtWidgets.QWidget(self)
        stretch.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        stretch.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        stretch.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        stretch.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.toolbar.addWidget(stretch)

        # Presets dock toggle button
        presets_btn = QtWidgets.QToolButton(self)
        presets_btn.setText('Presets')
        presets_btn.setIcon(ui.get_icon('btn_presets'))
        # Toggle the presets dock visibility
        presets_btn.clicked.connect(
            lambda: self.presets_view.setHidden(not self.presets_view.isHidden())
        )
        self.toolbar.addWidget(presets_btn)

        action = QtGui.QAction(self)
        action.setText('Settings')
        action.setIcon(ui.get_icon('btn_settings'))
        action.setToolTip('Show settings...')
        action.setShortcut(QtGui.QKeySequence('Ctrl+.'))
        action.triggered.connect(signals.openSettings)
        self.toolbar.addAction(action)

        self.toolbar.addWidget(self.status_indicator)



    def sizeHint(self):
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.6),
            ui.Size.DefaultHeight(1.6)
        )

    @QtCore.Slot(QtCore.QModelIndex)
    def activate_action(self, index: QtCore.QModelIndex) -> None:
        """
        Slot called on double-clicking or pressing Enter on a row.
        Opens a dockable TransactionsWidget on the right side.
        """
        if not index.isValid():
            return

        main = self.window()
        if main is None or not hasattr(main, 'addDockWidget'):
            return

        if not hasattr(main, 'transactions_view') or main.transactions_view is None:
            main.transactions_view = TransactionsWidget(parent=main)
            main.addDockWidget(QtCore.Qt.RightDockWidgetArea, main.transactions_view)
        elif main.transactions_view.isVisible():
            main.transactions_view.raise_()
            return

        main.transactions_view.show()
