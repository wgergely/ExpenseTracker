import dataclasses
import enum
import functools

from PySide6 import QtWidgets, QtCore, QtGui

from . import ui
from .yearmonth import RangeSelectorBar
from ..core import database
from ..data.view.expense import ExpenseView
from ..data.view.piechart import PieChartDockWidget
from ..data.view.transaction import TransactionsWidget
from ..data.view.trends import TrendDockWidget
from ..log.view import LogDockWidget
from ..settings.lib import app_name
from ..settings.presets.view import PresetsDockWidget
from ..settings.settings import SettingsDockWidget
from ..ui.actions import signals

main_window = None


def show_main_window():
    global main_window
    if main_window is None:
        main_window = MainWindow()
    main_window.show()
    return main_window


class Edge(enum.Flag):
    NONE = 0
    LEFT = enum.auto()
    TOP = enum.auto()
    RIGHT = enum.auto()
    BOTTOM = enum.auto()
    TOP_LEFT = TOP | LEFT
    TOP_RIGHT = TOP | RIGHT
    BOTTOM_LEFT = BOTTOM | LEFT
    BOTTOM_RIGHT = BOTTOM | RIGHT


CURSOR_MAP: dict[Edge, QtCore.Qt.CursorShape] = {
    Edge.LEFT: QtCore.Qt.SizeHorCursor,
    Edge.RIGHT: QtCore.Qt.SizeHorCursor,
    Edge.TOP: QtCore.Qt.SizeVerCursor,
    Edge.BOTTOM: QtCore.Qt.SizeVerCursor,
    Edge.TOP_LEFT: QtCore.Qt.SizeFDiagCursor,
    Edge.BOTTOM_RIGHT: QtCore.Qt.SizeFDiagCursor,
    Edge.TOP_RIGHT: QtCore.Qt.SizeBDiagCursor,
    Edge.BOTTOM_LEFT: QtCore.Qt.SizeBDiagCursor,
}


class TitleLabel(QtWidgets.QWidget):
    """Custom title label for the main window."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent=parent)
        self.setObjectName('ExpenseTrackerTitleLabel')

        self._connect_signals()

        QtCore.QTimer.singleShot(250, self.update_title)

    def _connect_signals(self) -> None:
        from ..ui.actions import signals

        @QtCore.Slot(str, object)
        def metadata_changed(key: str, value: object) -> None:
            if key == 'name':
                self.update_title()

        signals.metadataChanged.connect(metadata_changed)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(ui.Color.Text())

        font, metrics = self.get_font()
        x = self.rect().x() + ui.Size.Margin(0.5)
        y = self.rect().center().y() + metrics.height() / 2.0 - metrics.descent()

        path = QtGui.QPainterPath()
        path.addText(
            x,
            y,
            font,
            self.get_title()
        )

        painter.drawPath(path)

    @staticmethod
    def get_font():
        return ui.Font.BlackFont(ui.Size.MediumText(2.0))

    @staticmethod
    def get_title():
        from ..settings import lib
        v = lib.settings['name']
        return v or 'Untitled'

    @QtCore.Slot()
    def update_title(self) -> None:
        """Set the title of the label."""
        font, metrics = self.get_font()
        title = self.get_title()
        self.setFixedWidth(metrics.horizontalAdvance(title) + ui.Size.Margin(1.0))
        self.update()


class TitleBar(QtWidgets.QWidget):
    """A custom title bar with branding and window controls."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent=parent)
        self._drag_pos = None
        self.icon_label = None
        self.title_label = None

        self.setFixedHeight(ui.Size.RowHeight(1.5))

        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Fixed
        )

        self._create_ui()
        self._connect_signals()
        self._init_actions()

    def _create_ui(self) -> None:
        QtWidgets.QHBoxLayout(self)
        self.setObjectName('ExpenseTrackerTitleBar')

        o = ui.Size.Margin(1.5)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(ui.Size.Indicator(2.0))
        self.layout().setAlignment(QtCore.Qt.AlignCenter)

        # Title
        self.title_label = TitleLabel(parent=self)
        self.layout().addWidget(self.title_label, 0)

        # Min button
        self.btn_min = QtWidgets.QToolButton(self)
        self.btn_min.setIcon(ui.get_icon('btn_minimize'))
        self.btn_min.setFocusPolicy(QtCore.Qt.NoFocus)
        self.btn_min.setFixedSize(o, o)
        self.btn_min.setCursor(QtCore.Qt.ArrowCursor)
        self.btn_min.setAutoRaise(True)
        self.layout().addWidget(self.btn_min, 0)

        # Max button
        self.btn_max = QtWidgets.QToolButton(self)
        self.btn_max.setIcon(ui.get_icon('btn_maximize'))
        self.btn_max.setFocusPolicy(QtCore.Qt.NoFocus)
        self.btn_max.setFixedSize(o, o)
        self.btn_max.setCursor(QtCore.Qt.ArrowCursor)
        self.btn_max.setAutoRaise(True)
        self.layout().addWidget(self.btn_max, 0)

        # Close button
        self.btn_close = QtWidgets.QToolButton(self)
        self.btn_close.setIcon(ui.get_icon('btn_close'))
        self.btn_close.setFocusPolicy(QtCore.Qt.NoFocus)
        self.btn_close.setFixedSize(o, o)
        self.btn_close.setCursor(QtCore.Qt.ArrowCursor)
        self.btn_close.setAutoRaise(True)
        self.layout().addWidget(self.btn_close, 0)

    def _init_actions(self) -> None:
        pass

    def _connect_signals(self) -> None:
        self.btn_min.clicked.connect(self.window().showMinimized)
        self.btn_max.clicked.connect(self.toggle_max_restore)
        self.btn_close.clicked.connect(self.window().close)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        # only start drag when not maximized
        if event.button() == QtCore.Qt.LeftButton and not self.window().isMaximized():
            self._drag_pos = event.globalPosition().toPoint()
        else:
            self._drag_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if (event.buttons() & QtCore.Qt.LeftButton and
                self._drag_pos is not None and
                not self.window().isMaximized()):
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.window().move(self.window().pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        self.toggle_max_restore()
        super().mouseDoubleClickEvent(event)

    @QtCore.Slot()
    def toggle_max_restore(self) -> None:
        """Toggle between maximized and normal via the ResizableMainWidget API."""
        win = self.window()
        if hasattr(win, 'toggle_maximised'):
            win.toggle_maximised()
        else:
            # fallback
            if win.isMaximized():
                win.showNormal()
            else:
                win.showMaximized()
        # update icon (show maximize icon)
        self.btn_max.setIcon(ui.get_icon('btn_maximize'))


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

        signals.configSectionChanged.connect(self.update_status)
        signals.dataAboutToBeFetched.connect(self.update_status)
        signals.dataFetched.connect(self.update_status)
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
            icon = ui.get_icon('btn_ok', color=ui.Color.Green)
            color = ui.Color.Transparent()
        else:
            color = ui.Color.Yellow()
            icon = ui.get_icon('btn_alert', color=ui.Color.Yellow)

        if hover or pressed:
            color = color.lighter(150)

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
        QtWidgets.QMessageBox.information(self, 'Status', self._status.value.capitalize())


@dataclasses.dataclass
class InteractionState:
    edge: Edge = Edge.NONE
    pos: QtCore.QPointF = dataclasses.field(default_factory=QtCore.QPoint)
    rect: QtCore.QRect = dataclasses.field(default_factory=QtCore.QRect)


class ResizableMainWidget(QtWidgets.QMainWindow):
    """QMainWindow subclass providing custom resize, move, and window state change batching."""
    windowChanged = QtCore.Signal()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._press_state: InteractionState = InteractionState()

        self._previous_geometry: QtCore.QRect = None
        self._default_geometry = self._get_default_geometry()

        self._window_changed_timer = QtCore.QTimer(self)
        self._window_changed_timer.setInterval(200)
        self._window_changed_timer.setSingleShot(True)
        self._window_changed_timer.timeout.connect(self.windowChanged)

        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        o = ui.Size.Margin(2.0)
        self._default_margins: tuple[int, int, int, int] = (o, o * 0.5, o, o)
        self.setContentsMargins(*self._default_margins)

        self.setMinimumSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.0)
        )

        self.setGraphicsEffect(self._get_effect())

    def _get_default_geometry(self) -> QtCore.QRect:
        s = self.sizeHint()
        screen = QtGui.QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QtCore.QRect(0, 0, s.width(), s.height())
        x = avail.x() + (avail.width() - s.width()) // 2
        y = avail.y() + (avail.height() - s.height()) // 2
        return QtCore.QRect(x, y, s.width(), s.height())

    def _get_effect(self) -> QtWidgets.QGraphicsDropShadowEffect:
        """Factory for creating a drop shadow effect."""
        effect = QtWidgets.QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(self.contentsMargins().left() * 0.5)
        effect.setOffset(0, 0)
        effect.setColor(QtGui.QColor(0, 0, 0, 150))
        return effect

    def _get_edge_at_cursor(self) -> Edge:
        """Determine the edge of the window being pressed.

        """
        if self.isMaximized():
            return Edge.NONE

        # determine cursor position in widget-local coordinates
        pos = self.mapFromGlobal(QtGui.QCursor.pos())
        rect = self.visible_geometry()
        # threshold for detecting edges or corners
        threshold = ui.Size.Margin(0.5)
        flag = Edge.NONE
        if abs(pos.x() - rect.left()) <= threshold:
            flag |= Edge.LEFT
        if abs(pos.x() - rect.right()) <= threshold:
            flag |= Edge.RIGHT
        if abs(pos.y() - rect.top()) <= threshold:
            flag |= Edge.TOP
        if abs(pos.y() - rect.bottom()) <= threshold:
            flag |= Edge.BOTTOM
        return flag

    def set_state(self) -> None:
        """Record state at mouse press for resizing."""
        self._press_state.edge = self._get_edge_at_cursor()
        self._press_state.pos = QtGui.QCursor.pos()
        self._press_state.rect = self.geometry()

    def set_cursor(self) -> None:
        """Set the cursor shape based on the edge being pressed."""
        if self.isMaximized():
            self.setCursor(QtCore.Qt.ArrowCursor)
            return
        edge = self._get_edge_at_cursor()
        cursor = QtGui.QCursor(CURSOR_MAP.get(edge, QtCore.Qt.ArrowCursor))
        self.setCursor(cursor)

    def reset_cursor(self) -> None:
        """Reset cursor to default."""
        self.setCursor(QtCore.Qt.ArrowCursor)

    def reset_state(self) -> None:
        """Reset resize state after release."""
        self._press_state.edge = Edge.NONE
        self._press_state.pos = QtCore.QPointF()
        self._press_state.rect = QtCore.QRect()

        self.reset_cursor()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.LeftButton:
            super().mousePressEvent(event)
            return

        if self.isMaximized():
            super().mousePressEvent(event)
            return

        self.set_state()
        self.set_cursor()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        self.set_cursor()

        if not event.buttons() & QtCore.Qt.LeftButton:
            super().mouseMoveEvent(event)
            return

        if self.isMaximized():
            super().mouseMoveEvent(event)
            return

        event.accept()
        self.resize_window()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self.reset_state()
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.emit_window_changed()

    def moveEvent(self, event: QtGui.QMoveEvent) -> None:
        super().moveEvent(event)
        self.emit_window_changed()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.emit_window_changed()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.emit_window_changed()

    def showMinimized(self) -> None:
        self._previous_geometry = self.geometry()
        super().setWindowState(QtCore.Qt.WindowMinimized)
        super().showMinimized()
        self.emit_window_changed()

    def showMaximized(self) -> None:
        self._previous_geometry = self.geometry()

        self.setGraphicsEffect(None)
        super().setContentsMargins(0, 0, 0, 0)
        super().setWindowState(QtCore.Qt.WindowMaximized)
        super().showMaximized()

        self.emit_window_changed()
        self.update()

    def showNormal(self) -> None:
        self.setGraphicsEffect(self._get_effect())
        super().setContentsMargins(*self._default_margins)
        super().setWindowState(QtCore.Qt.WindowNoState)
        super().showNormal()

        if self._previous_geometry is not None:
            self.setGeometry(self._previous_geometry)

        self.emit_window_changed()
        self.update()

    @QtCore.Slot()
    def emit_window_changed(self) -> None:
        if not self._window_changed_timer.isActive():
            self._window_changed_timer.start()

    @QtCore.Slot()
    def toggle_maximised(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    @QtCore.Slot()
    def toggle_minimized(self) -> None:
        if self.isMinimized():
            self.showNormal()
        else:
            self.showMinimized()

    def resize_window(self) -> None:
        """Resize the window according to the dragged edge and global pointer."""
        edge = self._press_state.edge
        if edge == Edge.NONE:
            return

        global_pos = QtGui.QCursor.pos()
        delta = global_pos - self._press_state.pos
        if delta.x() == 0 and delta.y() == 0:
            return

        r = QtCore.QRect(self._press_state.rect)

        if edge & Edge.LEFT:
            r.setLeft(r.left() + delta.x())
        if edge & Edge.RIGHT:
            r.setRight(r.right() + delta.x())
        if edge & Edge.TOP:
            r.setTop(r.top() + delta.y())
        if edge & Edge.BOTTOM:
            r.setBottom(r.bottom() + delta.y())

        # mw, mh = self.minimumWidth(), self.minimumHeight()
        # if r.width() <= mw:
        #     return
        # if r.height() <= mh:
        #     return

        self.setGeometry(r)

    def visible_geometry(self) -> QtCore.QRect:
        if self.isMaximized():
            return self.rect()
        m = self.contentsMargins()
        return self.rect().adjusted(
            m.left() // 2.0,
            m.top(),
            -m.right() // 2.0,
            -m.bottom() // 2.0
        )

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        color = ui.Color.VeryDarkBackground()
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(color)

        rect = self.visible_geometry()

        if self.isMaximized():
            painter.drawRect(rect)
            return

        c = ui.Size.Indicator(2.0)
        painter.drawRoundedRect(rect, c, c)


class MainWindow(ResizableMainWidget):

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle(app_name)

        self.setObjectName('ExpenseTrackerMainWindow')

        self.content_area = None

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
        self.load_window_settings()

    def _create_ui(self):
        self.setMenuWidget(TitleBar(self))

        central = QtWidgets.QWidget(self)
        central.setProperty('rounded', True)
        QtWidgets.QVBoxLayout(central)

        o = ui.Size.Margin(1.0)
        central.layout().setContentsMargins(o, 0, o, o)
        central.layout().setSpacing(o * 0.5)

        self.setCentralWidget(central)

        # Action bar at the top.
        self.toolbar = QtWidgets.QToolBar(self)
        self.toolbar.setProperty('no_background', True)
        self.toolbar.setObjectName('ExpenseTrackerActionToolBar')
        self.menuWidget().layout().insertWidget(1, self.toolbar, 1)

        self.range_selector = RangeSelectorBar(parent=self)
        self.range_selector.setObjectName('ExpenseTrackerRangeSelector')
        self.toolbar.addWidget(self.range_selector)

        self.expense_view = ExpenseView(parent=central)
        self.expense_view.setObjectName('ExpenseTrackerExpenseView')
        central.layout().addWidget(self.expense_view, 1)

        self.status_indicator = StatusIndicator(parent=self)

        # Add transactions dock (right side)
        self.transactions_view = TransactionsWidget(parent=self)
        self.transactions_view.setObjectName('ExpenseTrackerTransactionsView')
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.transactions_view)
        self.transactions_view.hide()

        # Add presets dock (left side)
        self.presets_view = PresetsDockWidget(parent=self)
        self.presets_view.setObjectName('ExpenseTrackerPresetsDockWidget')
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.presets_view)
        self.presets_view.hide()

        # Add settings dock (bottom)
        self.settings_view = SettingsDockWidget(parent=self)
        self.settings_view.setObjectName('ExpenseTrackerSettingsDockWidget')
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.settings_view)
        self.settings_view.hide()

        # Add log dock (top)
        self.log_view = LogDockWidget(parent=self)
        self.log_view.setObjectName('ExpenseTrackerLogDockWidget')
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.log_view)
        self.log_view.hide()

        # Add trend dock (bottom)
        self.trends_view = TrendDockWidget(parent=self)
        self.trends_view.setObjectName('ExpenseTrackerTrendDockWidget')
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.trends_view)
        self.trends_view.hide()

        # Add pie chart dock (right side)
        self.piechart_view = PieChartDockWidget(parent=self)
        self.piechart_view.setObjectName('ExpenseTrackerPieChartDockWidget')
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.piechart_view)
        self.piechart_view.hide()

    def _connect_signals(self):
        signals.openTransactions.connect(
            lambda: self.transactions_view.setHidden(not self.transactions_view.isHidden()))
        signals.showLogs.connect(lambda: (self.log_view.show(), self.log_view.raise_()))

        signals.showSettings.connect(self.settings_view.show)

    def _init_actions(self):
        action = QtGui.QAction('Maximize', self)
        action.setIcon(ui.get_icon('btn_maximize'))
        action.setToolTip('Maximize')
        action.setStatusTip('Maximize')
        action.setShortcut('Ctrl+M')
        action.triggered.connect(self.toggle_maximised)
        self.addAction(action)

        action = QtGui.QAction('Minimize', self)
        action.setIcon(ui.get_icon('btn_minimize'))
        action.setToolTip('Minimize')
        action.setStatusTip('Minimize')
        action.setShortcut('Ctrl+Shift+M')
        action.triggered.connect(self.toggle_minimized)
        self.addAction(action)

        # Separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

        w = QtWidgets.QWidget(self)
        w.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        w.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        w.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.toolbar.addWidget(w)

        action = QtGui.QAction('Refresh Data', self)
        action.setIcon(ui.get_icon('btn_sync'))
        action.setToolTip('Fetch data')
        action.setStatusTip('Fetch data')
        action.triggered.connect(signals.dataFetchRequested)
        self.toolbar.addAction(action)

        action = QtGui.QAction('Open Spreadsheet', self)
        action.setShortcut('Ctrl+Shift+O')
        action.setToolTip('Open spreadsheet in browser')
        action.setIcon(ui.get_icon('btn_ledger'))
        action.triggered.connect(signals.openSpreadsheet)
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.toolbar.addAction(action)
        self.addAction(action)

        toggle_func = lambda a, s: a.setIcon(
            ui.get_icon(s, color=ui.Color.SelectedText)) if a.isChecked() else a.setIcon(
            ui.get_icon(s, color=ui.Color.DisabledText))
        toggle_vis = lambda e: e.setHidden(not e.isHidden())

        action = QtGui.QAction('Presets', self)
        action.setCheckable(True)
        action.setChecked(self.presets_view.isVisible())
        action.setIcon(ui.get_icon('btn_presets', color=ui.Color.DisabledText))
        action.setToolTip('Show presets...')
        action.setStatusTip('Show presets...')
        action.setShortcut('Ctrl+Shift+P')
        action.triggered.connect(functools.partial(toggle_func, action, 'btn_presets'))
        action.triggered.connect(functools.partial(toggle_vis, self.presets_view))
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Transactions', self)
        action.setCheckable(True)
        action.setChecked(self.transactions_view.isVisible())
        action.setIcon(ui.get_icon('btn_transactions', color=ui.Color.DisabledText))
        action.setToolTip('Show transactions...')
        action.setStatusTip('Show transactions...')
        action.setShortcut('Ctrl+Shift+T')
        action.triggered.connect(functools.partial(toggle_func, action, 'btn_transactions'))
        action.triggered.connect(signals.openTransactions)
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Trends', self)
        action.setCheckable(True)
        action.setChecked(self.trends_view.isVisible())
        action.setIcon(ui.get_icon('btn_trend', color=ui.Color.DisabledText))
        action.setToolTip('Show trends chart...')
        action.setStatusTip('Show trends chart...')
        action.setShortcut('Ctrl+Shift+T')
        action.triggered.connect(functools.partial(toggle_func, action, 'btn_trend'))
        action.triggered.connect(functools.partial(toggle_vis, self.trends_view))
        self.toolbar.addAction(action)
        self.addAction(action)
        # Pie Chart toggle
        action = QtGui.QAction('Pie Chart', self)
        action.setCheckable(True)
        action.setChecked(self.piechart_view.isVisible())
        action.setToolTip('Show pie chart...')
        action.setStatusTip('Show pie chart...')
        action.triggered.connect(functools.partial(toggle_vis, self.piechart_view))
        self.toolbar.addAction(action)
        self.addAction(action)

        # Separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Logs', self)
        action.setCheckable(True)
        action.setChecked(self.log_view.isVisible())
        action.setIcon(ui.get_icon('btn_log', color=ui.Color.DisabledText))
        action.setToolTip('Show logs...')
        action.setStatusTip('Show logs...')
        action.setShortcut('Ctrl+Shift+L')
        action.triggered.connect(functools.partial(toggle_func, action, 'btn_log'))
        action.triggered.connect(functools.partial(toggle_vis, self.log_view))
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Settings', self)
        action.setIcon(ui.get_icon('btn_settings', color=ui.Color.DisabledText))
        action.setToolTip('Show settings...')
        action.setStatusTip('Show settings...')
        action.setCheckable(True)
        action.setChecked(self.settings_view.isVisible())
        action.setShortcuts(['Ctrl+,', 'Ctrl+Shift+,', 'Ctrl+.', 'Ctrl+Shift+.', 'Ctrl+Shift+S'])
        action.triggered.connect(functools.partial(toggle_func, action, 'btn_settings'))
        action.triggered.connect(functools.partial(toggle_vis, self.settings_view))
        self.toolbar.addAction(action)
        self.addAction(action)

        # Separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Previous Month', self)
        action.setShortcuts(['Alt+Left', 'Ctrl+Left'])
        action.setShortcutContext(QtCore.Qt.WindowShortcut)
        action.triggered.connect(self.range_selector.previous_month)
        self.addAction(action)

        action = QtGui.QAction('Next Month', self)
        action.setShortcuts(['Alt+Right', 'Ctrl+Right'])
        action.setShortcutContext(QtCore.Qt.WindowShortcut)
        action.triggered.connect(self.range_selector.next_month)
        self.addAction(action)

        self.toolbar.addWidget(self.status_indicator)

    def sizeHint(self):
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.5)
        )

    def closeEvent(self, event) -> None:
        """Persist window geometry and state on close."""
        settings = QtCore.QSettings(app_name, app_name)
        settings.setValue('MainWindow/geometry', self.saveGeometry())
        settings.setValue('MainWindow/windowState', self.saveState())
        settings.setValue('MainWindow/maximized', self.isMaximized())
        super().closeEvent(event)

    @QtCore.Slot(QtCore.QModelIndex)
    def activate_action(self, index: QtCore.QModelIndex) -> None:
        """
        Slot called on double-clicking or pressing Enter on a row.
        Opens a dockable TransactionsWidget on the right side.
        """
        if not index.isValid():
            return
        self.window().transactions_view.show()

    def load_window_settings(self) -> None:
        settings = QtCore.QSettings(app_name, app_name)
        geom_data = settings.value('MainWindow/geometry')
        was_maximized = settings.value('MainWindow/maximized', False)
        primary = QtGui.QGuiApplication.primaryScreen()
        avail_primary = primary.availableGeometry()

        if isinstance(geom_data, QtCore.QByteArray) and not was_maximized:
            tmp = QtWidgets.QWidget()
            tmp.restoreGeometry(geom_data)
            rect = tmp.frameGeometry()
            width = min(rect.width(), avail_primary.width())
            height = min(rect.height(), avail_primary.height())

            center = rect.center()
            screen = QtGui.QGuiApplication.screenAt(center) or primary
            avail = screen.availableGeometry()

            x = max(avail.left(), min(rect.x(), avail.right() - width))
            y = max(avail.top(), min(rect.y(), avail.bottom() - height))
            self.setGeometry(x, y, width, height)
        else:
            self.resize(self.sizeHint())
            x = avail_primary.x() + (avail_primary.width() - self.width()) // 2
            y = avail_primary.y() + (avail_primary.height() - self.height()) // 2
            self.move(x, y)

        state = settings.value('MainWindow/windowState')
        if isinstance(state, QtCore.QByteArray):
            self.restoreState(state)

        if was_maximized:
            self.showMaximized()
        else:
            self.clamp_window_to_screens()

    def clamp_window_to_screens(self) -> None:
        frame = self.frameGeometry()
        center = frame.center()
        screen = QtGui.QGuiApplication.screenAt(center) or QtGui.QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()

        width = min(frame.width(), avail.width())
        height = min(frame.height(), avail.height())

        x = max(avail.left(), min(frame.x(), avail.right() - width))
        y = max(avail.top(), min(frame.y(), avail.bottom() - height))

        self.setGeometry(x, y, width, height)
