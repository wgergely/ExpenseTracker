"""Shared chart slice, model, and base view for category-based charts."""
import logging
from dataclasses import dataclass, field
from typing import List

from PySide6 import QtCore, QtGui, QtWidgets

from . import ui
from .actions import signals
from ..core.sync import sync
from ..data import data
from ..settings import lib, locale


@dataclass(slots=True)
class ChartSlice:
    """Immutable slice data plus optional geometry."""
    category: str  # raw category key
    amount_txt: str
    value_abs: float
    color: QtGui.QColor
    icon_name: str
    start_qt: int
    span_qt: int
    display_name: str = ''  # human-readable category name
    # geometry fields for slice rendering
    base_rect: QtCore.QRect = field(default_factory=QtCore.QRect, repr=False)
    popped_rect: QtCore.QRect = field(default_factory=QtCore.QRect, repr=False)
    half_rect: QtCore.QRect = field(default_factory=QtCore.QRect, repr=False)
    base_path: QtGui.QPainterPath = field(default_factory=QtGui.QPainterPath, repr=False)
    popped_path: QtGui.QPainterPath = field(default_factory=QtGui.QPainterPath, repr=False)
    mid_deg: float = 0.0
    dx: int = 0
    dy: int = 0
    dx_max: int = 0
    dy_max: int = 0


class ChartModel(QtCore.QObject):
    """Model for constructing ChartSlice instances from expense data."""

    def __init__(self) -> None:
        self._slices: List[ChartSlice] = []
        self._version: int = 0

    @property
    def slices(self) -> List[ChartSlice]:
        return self._slices

    @property
    def version(self) -> int:
        return self._version

    def rebuild(self) -> None:
        """Populate slices from the current filtered dataframe."""
        df = data.get_data()
        if df.empty:
            logging.debug('ChartModel: no data available')
            self._slices = []
            self._version += 1
            return

        df = df[(df['category'] != 'Total') & (df['category'] != '')]

        if not lib.settings['exclude_negative'] and not lib.settings['exclude_positive']:
            logging.warning('ChartModel requires exclusive sign totals')
            self._slices = []
            self._version += 1
            return

        df = df[df['total'] > 0] if lib.settings['exclude_negative'] else df[df['total'] < 0]
        df = df.reset_index(drop=True)
        if df.empty or df['total'].abs().sum() == 0:
            self._slices = []
            self._version += 1
            return

        total_abs = df['total'].abs().sum()
        qt_circle = 360 * 16
        rotation_qt = 90 * 16
        spans: List[tuple[int, int, float]] = []
        for idx, row in df.iterrows():
            span_qt = int(round(abs(row['total']) / total_abs * qt_circle))
            spans.append((idx, span_qt, abs(row['total'])))

        used = sum(s for _, s, _ in spans)
        leftover = qt_circle - used
        if leftover:
            max_idx = max(spans, key=lambda t: t[2])[0]
            for n, (idx, span_qt, val) in enumerate(spans):
                if idx == max_idx:
                    spans[n] = (idx, span_qt + leftover, val)
                    break

        cursor = 0
        new_slices: List[ChartSlice] = []

        config = lib.settings.get_section('categories') or {}

        for idx, span_qt, _ in spans:
            row = df.loc[idx]
            cat = row['category']
            display = cat

            if config and cat in config:
                display = config[cat].get('display_name', cat)

            amount_txt = locale.format_currency_value(abs(row['total']), lib.settings['locale'])
            col_name = config.get(cat, {}).get('color', ui.Color.Text().name(QtGui.QColor.HexRgb))
            color = QtGui.QColor(col_name) if QtGui.QColor(col_name).isValid() else ui.Color.Text()
            icon_name = config.get(cat, {}).get('icon', 'cat_unclassified')

            new_slices.append(
                ChartSlice(
                    category=cat,
                    amount_txt=amount_txt,
                    value_abs=abs(row['total']),
                    color=color,
                    icon_name=icon_name,
                    start_qt=(cursor + rotation_qt) % qt_circle,
                    span_qt=span_qt,
                    display_name=display,
                )
            )
            cursor += span_qt

        self._slices = new_slices
        self._version += 1

    def clear(self) -> None:
        """Clear the model."""
        self._slices = []
        self._version += 1


class BaseChartView(QtWidgets.QWidget):
    """Base widget for interactive category charts."""
    hoverChanged = QtCore.Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._selected_category: str = ''
        self._show_legend: bool = True
        self._show_icons: bool = True
        self._show_tooltip: bool = True
        self._geom_sig: tuple[int, int, int] = (-1, -1, -1)
        self._hover_index: int = -1

        self._anim_progress = 0.0

        self._init_data_timer = QtCore.QTimer(self)
        self._init_data_timer.setSingleShot(True)
        self._init_data_timer.setInterval(50)

        self.model = ChartModel()

        self.setMouseTracking(True)
        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self._animation = QtCore.QVariantAnimation(self)
        self._animation.setDuration(400)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QtCore.QEasingCurve.OutQuad)
        self._animation.setLoopCount(1)
        self._animation.setDirection(QtCore.QAbstractAnimation.Forward)
        self._animation.finished.connect(self._animation.stop)

        self._create_ui()
        self._connect_signals()
        self._init_actions()

    def _create_ui(self) -> None:
        self.setMinimumSize(
            ui.Size.DefaultWidth(0.5), ui.Size.DefaultWidth(0.5)
        )
        self.setMaximumSize(
            ui.Size.DefaultWidth(1.0), ui.Size.DefaultWidth(1.0)
        )
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

    def _connect_signals(self) -> None:
        signals.presetAboutToBeActivated.connect(self.clear_data)
        signals.dataAboutToBeFetched.connect(self.clear_data)

        signals.dataFetched.connect(self.start_init_data_timer)

        @QtCore.Slot(str, object)
        def _meta(key: str, _: object) -> None:
            if key in (
                    'hide_empty_categories', 'exclude_negative',
                    'exclude_zero', 'exclude_positive',
                    'span', 'yearmonth'):
                self.start_init_data_timer()

        signals.metadataChanged.connect(_meta)
        sync.dataUpdated.connect(lambda _: self.start_init_data_timer())

        @QtCore.Slot(str)
        def _cfg(section: str) -> None:
            if section in ('categories', 'mapping'):
                self.start_init_data_timer()

        signals.configSectionChanged.connect(_cfg)

        @QtCore.Slot(str)
        def _on_cat(cat: str) -> None:
            self._selected_category = cat or ''
            self.update()

        signals.categoryChanged.connect(_on_cat)

        self._init_data_timer.timeout.connect(self.init_data)

        signals.initializationRequested.connect(self.start_init_data_timer)

        self._init_data_timer.timeout.connect(self._animation.start)

        def on_anim_value_chaged(value: float) -> None:
            self._anim_progress = value
            self._recalc_geometry()
            self.repaint()

        self._animation.valueChanged.connect(on_anim_value_chaged)

    @QtCore.Slot()
    def start_init_data_timer(self) -> None:
        self._init_data_timer.start(self._init_data_timer.interval())

    @QtCore.Slot()
    def init_data(self) -> None:
        self.model.rebuild()
        self._geom_sig = (-1, -1, -1)
        self.update()

    @QtCore.Slot()
    def clear_data(self) -> None:
        self.model.clear()
        self._geom_sig = (-1, -1, -1)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        self._recalc_geometry()

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        self._draw_background(painter)

        self._draw_slices(painter)

        if self._show_legend:
            self._draw_legend(painter)

        if self._show_icons:
            self._draw_icons(painter)

        if self._show_tooltip:
            self._draw_tooltip(painter)

    def _draw_background(self, painter: QtGui.QPainter) -> None:
        if self.property('rounded'):
            painter.setBrush(ui.Color.VeryDarkBackground())
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(
                self.rect(), ui.Size.Indicator(2.0), ui.Size.Indicator(2.0)
            )
        else:
            painter.fillRect(self.rect(), ui.Color.VeryDarkBackground())
        offset = ui.Size.Margin(1.0)
        inner = self.rect().adjusted(offset, offset, -offset, -offset)
        painter.setBrush(ui.Color.DarkBackground())
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(inner, ui.Size.Indicator(2.0), ui.Size.Indicator(2.0))

    # Subclasses must implement:
    def _recalc_geometry(self) -> None:
        raise NotImplementedError

    def _draw_slices(self, painter: QtGui.QPainter) -> None:
        raise NotImplementedError

    def _slice_at(self, pos: QtCore.QPoint) -> int:
        raise NotImplementedError

    def _draw_legend(self, painter: QtGui.QPainter) -> None:
        raise NotImplementedError

    def _draw_icons(self, painter: QtGui.QPainter) -> None:
        raise NotImplementedError

    def _draw_tooltip(self, painter: QtGui.QPainter) -> None:
        raise NotImplementedError

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        self.update()
        idx = self._slice_at(event.pos())
        if idx != self._hover_index:
            self._hover_index = idx
            self.hoverChanged.emit(idx)
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        if self._hover_index != -1:
            self._hover_index = -1
            self.hoverChanged.emit(-1)
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        idx = self._slice_at(event.pos())
        cat = self.model.slices[idx].category if 0 <= idx < len(self.model.slices) else ''
        # update selection state locally and request global category update
        self._selected_category = cat
        self.update()
        # request expense view to select this category (authoritative source)
        signals.categoryUpdateRequested.emit(cat)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        idx = self._slice_at(event.pos())
        if 0 <= idx < len(self.model.slices):
            category = self.model.slices[idx].category
            from .palette import CategoryIconColorEditorDialog
            dlg = CategoryIconColorEditorDialog(category, self)
            dlg.iconChanged.connect(lambda _: self.start_init_data_timer())
            dlg.colorChanged.connect(lambda _: self.start_init_data_timer())
            dlg.open()
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        self._geom_sig = (-1, -1, -1)
        self.update()
        super().resizeEvent(event)

    def _init_actions(self) -> None:
        @QtCore.Slot(bool)
        def toggle_legend(checked: bool) -> None:
            self._show_legend = checked
            self.update()

        action = QtGui.QAction('Toggle Legend', self)
        action.setCheckable(True)
        action.setChecked(self._show_legend)
        action.setToolTip('Show/hide legend')
        action.setStatusTip('Show/hide legend')
        action.setWhatsThis('Show/hide legend')
        action.setShortcut('Alt+1')
        action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        action.triggered.connect(toggle_legend)
        self.addAction(action)

        @QtCore.Slot(bool)
        def toggle_icons(checked: bool) -> None:
            self._show_icons = checked
            self.update()

        action = QtGui.QAction('Toggle Icons', self)
        action.setCheckable(True)
        action.setChecked(self._show_icons)
        action.setToolTip('Show/hide icons')
        action.setStatusTip('Show/hide icons')
        action.setWhatsThis('Show/hide icons')
        action.setShortcut('Alt+2')
        action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        action.triggered.connect(toggle_icons)
        self.addAction(action)

        @QtCore.Slot(bool)
        def toggle_tooltip(checked: bool) -> None:
            self._show_tooltip = checked
            self.update()

        action = QtGui.QAction('Toggle Tooltip', self)
        action.setCheckable(True)
        action.setChecked(self._show_tooltip)
        action.setToolTip('Show/hide tooltip')
        action.setStatusTip('Show/hide tooltip')
        action.setWhatsThis('Show/hide tooltip')
        action.setShortcut('Alt+3')
        action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        action.triggered.connect(toggle_tooltip)
        self.addAction(action)
        # separator
        sep = QtGui.QAction('', self)
        sep.setSeparator(True)
        self.addAction(sep)

        @QtCore.Slot()
        def reload_chart() -> None:
            self.start_init_data_timer()

        action = QtGui.QAction('Reload Chart', self)
        action.setToolTip('Reload chart')
        action.setStatusTip('Reload chart')
        action.setShortcut('Ctrl+R')
        action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        action.triggered.connect(reload_chart)
        self.addAction(action)
