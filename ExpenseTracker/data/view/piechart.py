import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ...core.sync import sync_manager
from ...data import data
from ...settings import lib, locale
from ...ui import ui
from ...ui.actions import signals
from ...ui.ui import CategoryIconEngine, get_icon


@dataclass(slots=True)
class PieChartSlice:
    """Immutable slice data plus geometry filled by the view."""

    category: str
    amount_txt: str
    value_abs: float
    color: QtGui.QColor
    icon_name: str
    start_qt: int  # Qt angle units (1/16 °)
    span_qt: int  # Qt angle units (1/16 °)

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


class PieChartModel:
    """Builds :class:`PieChartSlice` objects from the dataframe."""

    def __init__(self) -> None:
        self._slices: List[PieChartSlice] = []
        self._version: int = 0

    @property
    def slices(self) -> List[PieChartSlice]:
        return self._slices

    @property
    def version(self) -> int:
        return self._version

    def rebuild(self) -> None:
        """Populate slices from the current filtered dataframe."""
        df = data.get_data()
        df = df[(df['category'] != 'Total') & (df['category'] != '')]

        if not lib.settings['exclude_negative'] and not lib.settings['exclude_positive']:
            logging.warning('PieChart requires exclusively positive or negative totals')
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

        used = sum(span for _, span, _ in spans)
        leftover = qt_circle - used
        if leftover:
            largest_idx = max(spans, key=lambda x: x[2])[0]
            for n, (idx, span_qt, val) in enumerate(spans):
                if idx == largest_idx:
                    spans[n] = (idx, span_qt + leftover, val)
                    break

        cfg = lib.settings.get_section('categories') or {}
        cursor = 0
        new_slices: List[PieChartSlice] = []

        for idx, span_qt, _ in spans:
            row = df.loc[idx]
            cat = row['category']
            amount_txt = locale.format_currency_value(abs(row['total']), lib.settings['locale'])
            col_name = cfg.get(cat, {}).get('color', ui.Color.Text().name(QtGui.QColor.HexRgb))
            color = QtGui.QColor(col_name) if QtGui.QColor(col_name).isValid() else ui.Color.Text()
            icon_name = cfg.get(cat, {}).get('icon', 'cat_unclassified')

            new_slices.append(
                PieChartSlice(
                    category=cat,
                    amount_txt=amount_txt,
                    value_abs=abs(row['total']),
                    color=color,
                    icon_name=icon_name,
                    start_qt=(cursor + rotation_qt) % qt_circle,
                    span_qt=span_qt,
                )
            )
            cursor += span_qt

        self._slices = new_slices
        self._version += 1


class PieChartView(QtWidgets.QWidget):
    """Interactive exploded-view pie chart."""

    hoverChanged = QtCore.Signal(int)  # emits -1 when nothing is hovered

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self._show_legend = True
        self._show_icons = True
        self._show_tooltip = True

        self.model = PieChartModel()

        self.min_offset_px = ui.Size.Indicator(1.0)
        self.max_offset_px = ui.Size.Indicator(10.0)
        self.gap_px = self.min_offset_px

        self._geom_sig: tuple[int, int, int] = (-1, -1, -1)
        self._hover_index: int = -1

        self.setMouseTracking(True)
        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self._create_ui()
        self._connect_signals()
        self._init_actions()

        QtCore.QTimer.singleShot(0, self.model.rebuild)

    def _create_ui(self) -> None:
        self.setMinimumSize(ui.Size.DefaultWidth(), ui.Size.DefaultHeight())
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

    def _connect_signals(self) -> None:

        signals.presetAboutToBeActivated.connect(self.init_data)
        signals.dataFetched.connect(self.init_data)

        @QtCore.Slot(str, object)
        def metadata_changed(key: str, value: object) -> None:
            if key in ('hide_empty_categories', 'exclude_negative', 'exclude_zero', 'exclude_positive', 'span',
                       'yearmonth'):
                self.init_data()

        signals.metadataChanged.connect(metadata_changed)
        # refresh slices when local cache is updated by sync
        sync_manager.dataUpdated.connect(lambda _: self.init_data())

    @QtCore.Slot()
    def init_data(self) -> None:
        self.model.rebuild()
        self._geom_sig = (-1, -1, -1)
        self.update()

    @staticmethod
    def _slice_path(rect: QtCore.QRect, start_deg: float, span_deg: float) -> QtGui.QPainterPath:
        path = QtGui.QPainterPath()
        path.moveTo(rect.center())
        path.arcTo(rect, start_deg, span_deg)
        path.closeSubpath()
        return path

    def _recalc_geometry(self) -> None:
        sig = (self.model.version, self.width(), self.height())
        if sig == self._geom_sig:
            return

        if not self.model.slices:
            self._geom_sig = sig
            return

        widget_rect = self.rect()
        edge = min(widget_rect.width(), widget_rect.height())
        outer = QtCore.QRect(
            widget_rect.x() + (widget_rect.width() - edge) // 2,
            widget_rect.y() + (widget_rect.height() - edge) // 2,
            edge,
            edge,
        )

        margin = ui.Size.Margin(1.0)
        outer = outer.adjusted(margin, margin, -margin, -margin)

        radius = (outer.width() - margin * 2) / ui.Size.Separator(2.0)
        max_off_clip = min(self.max_offset_px, radius * 0.30)

        inner = outer.adjusted(
            int(margin + max_off_clip),
            int(margin + max_off_clip),
            -int(margin + max_off_clip),
            -int(margin + max_off_clip),
        )

        for sl in self.model.slices:
            alpha_rad = math.radians(sl.span_qt / 16.0)
            t_raw = 0.0 if alpha_rad == 0 else self.gap_px / (2.0 * math.sin(alpha_rad / 2.0))
            t = max(self.min_offset_px, min(t_raw, max_off_clip))

            start_deg = sl.start_qt / 16.0
            span_deg = sl.span_qt / 16.0
            sl.mid_deg = start_deg + span_deg / 2.0
            theta = math.radians(sl.mid_deg)

            sl.dx = int(round(t * math.cos(theta)))
            sl.dy = int(round(-t * math.sin(theta)))
            sl.dx_max = int(round(max_off_clip * math.cos(theta)))
            sl.dy_max = int(round(-max_off_clip * math.sin(theta)))

            sl.base_rect = QtCore.QRect(inner.translated(sl.dx, sl.dy))
            sl.popped_rect = QtCore.QRect(inner.translated(sl.dx_max, sl.dy_max))
            sl.half_rect = QtCore.QRect(
                inner.translated(
                    (sl.dx + sl.dx_max) // 2,
                    (sl.dy + sl.dy_max) // 2,
                )
            )

            sl.base_path = self._slice_path(sl.base_rect, start_deg, span_deg)
            sl.popped_path = self._slice_path(sl.popped_rect, start_deg, span_deg)

        self._geom_sig = sig

    def _slice_at(self, pos: QtCore.QPoint) -> int:
        for index, sl in enumerate(self.model.slices):
            if sl.popped_path.contains(QtCore.QPointF(pos)):
                return index
        return -1

    def paintEvent(self, _: QtGui.QPaintEvent) -> None:
        """
        Repaint the widget.

        Each slice's centre angle θ and angular width α are known in Qt
        *angle units* (1/16 °).  For a desired linear gap *g* between two
        neighbouring slice edges, the radial offset *t* that produces it is::

            t_raw = g / (2 · sin(α / 2))

        ``t_raw`` is clamped to *[min_offset_px, max_offset_clip]*, where
        *max_offset_clip* is the smaller of *max_offset_px* and 30 % of the
        pie radius.  The hovered slice is rendered at half the full pop-out
        distance for a subtler effect.
        """
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
            painter.drawRoundedRect(self.rect(), ui.Size.Indicator(2.0), ui.Size.Indicator(2.0))
        else:
            painter.fillRect(self.rect(), ui.Color.VeryDarkBackground())

        offset = ui.Size.Margin(1.0)
        inner = self.rect().adjusted(offset, offset, -offset, -offset)
        painter.setBrush(ui.Color.DarkBackground())
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(inner, ui.Size.Indicator(2.0), ui.Size.Indicator(2.0))

    def _draw_slices(self, painter: QtGui.QPainter) -> None:
        for idx, sl in enumerate(self.model.slices):
            rect = sl.half_rect if idx == self._hover_index else sl.base_rect
            painter.setBrush(sl.color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawPie(rect, sl.start_qt, sl.span_qt)

    def _draw_legend(self, painter: QtGui.QPainter) -> None:
        if not self.model.slices:
            return

        pad = ui.Size.Indicator(1.0)
        radial_step = ui.Size.Separator(0.8)
        font, metrics = ui.Font.BoldFont(ui.Size.MediumText())
        painter.setFont(font)

        placed_boxes: List[QtCore.QRectF] = []

        for idx, sl in sorted(enumerate(self.model.slices), key=lambda t: t[1].mid_deg):
            rect_ref = sl.half_rect if idx == self._hover_index else sl.base_rect
            centre = rect_ref.center()
            base_r = rect_ref.width() / 2.0 + pad * 2
            theta = math.radians(sl.mid_deg)

            text = sl.amount_txt
            txt_w = metrics.horizontalAdvance(text)
            txt_h = metrics.height()

            current_r = base_r
            while True:
                cx = centre.x() + current_r * math.cos(theta)
                cy = centre.y() - current_r * math.sin(theta)
                box = QtCore.QRectF(
                    cx - txt_w / 2 - pad,
                    cy - txt_h / 2 - pad,
                    txt_w + pad * 2,
                    txt_h + pad * 2,
                )

                if all(not box.intersects(other) for other in placed_boxes):
                    placed_boxes.append(box)
                    break

                current_r += radial_step

        for sl, box in zip(self.model.slices, placed_boxes):
            painter.save()
            painter.setOpacity(0.5)
            painter.setBrush(ui.Color.VeryDarkBackground())
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(box, pad, pad)
            painter.restore()

            painter.setPen(ui.Color.Text())
            painter.drawText(QtCore.QPointF(box.x() + pad, box.y() + pad + metrics.ascent()), sl.amount_txt)

    def _draw_icons(self, painter: QtGui.QPainter) -> None:
        if not self.model.slices:
            return

        size = ui.Size.Margin(2.0)
        for idx, sl in enumerate(self.model.slices):
            if sl.span_qt / 16.0 < 20.0:
                continue

            rect_ref = sl.half_rect if idx == self._hover_index else sl.base_rect
            centre = rect_ref.center()
            radius = rect_ref.width() / 2.0
            theta = math.radians(sl.mid_deg)

            x = centre.x() + radius * 0.5 * math.cos(theta) - size / 2
            y = centre.y() - radius * 0.5 * math.sin(theta) - size / 2

            icon = get_icon(sl.icon_name, color=sl.color.darker(150), engine=CategoryIconEngine)
            painter.drawPixmap(int(x), int(y), icon.pixmap(size, size))

    def _draw_tooltip(self, painter: QtGui.QPainter) -> None:
        if self._hover_index < 0:
            return

        sl = self.model.slices[self._hover_index]
        cursor_pos = self.mapFromGlobal(QtGui.QCursor.pos())

        text = f'{sl.category}: {sl.amount_txt}'
        font, metrics = ui.Font.BoldFont(ui.Size.MediumText())
        painter.setFont(font)

        pad = ui.Size.Indicator(2.0)
        icon_size = metrics.height()
        width = icon_size + pad + metrics.horizontalAdvance(text) + pad * 2
        height = icon_size + pad * 2

        x = max(self.rect().left(), min(cursor_pos.x() - width / 2, self.rect().right() - width))
        y = cursor_pos.y() - height - pad
        if y < self.rect().top():
            y = cursor_pos.y() + pad

        bg = QtCore.QRectF(x, y, width, height)
        painter.setBrush(ui.Color.DarkBackground())
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(bg, pad, pad)

        icon = get_icon(sl.icon_name, color=sl.color, engine=CategoryIconEngine)
        painter.drawPixmap(int(bg.x() + pad), int(bg.y() + pad), icon.pixmap(icon_size, icon_size))

        painter.setPen(ui.Color.Text())
        painter.drawText(
            QtCore.QPointF(bg.x() + pad + icon_size + pad, bg.y() + pad + metrics.ascent()),
            text,
        )

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        self.update()  # smooth tooltip tracking
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

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        self._geom_sig = (-1, -1, -1)
        self.update()
        super().resizeEvent(event)

    def _init_actions(self):
        @QtCore.Slot(bool)
        def toggle_legend(checked: bool) -> None:
            self._show_legend = checked
            self.update()

        action = QtGui.QAction(self, 'Toggle Legend')
        action.setCheckable(True)
        action.setChecked(self._show_legend)
        action.setToolTip('Show/hide legend')
        action.setStatusTip('Show/hide legend')
        action.setWhatsThis('Show/hide legend')
        action.setShortcut(QtGui.QKeySequence('alt+1'))
        action.triggered.connect(toggle_legend)
        self.addAction(action)

        @QtCore.Slot(bool)
        def toggle_icons(checked: bool) -> None:
            self._show_icons = checked
            self.update()

        action = QtGui.QAction(self, 'Toggle Icons')
        action.setCheckable(True)
        action.setChecked(self._show_icons)
        action.setToolTip('Show/hide icons')
        action.setStatusTip('Show/hide icons')
        action.setWhatsThis('Show/hide icons')
        action.setShortcut(QtGui.QKeySequence('alt+2'))
        action.triggered.connect(toggle_icons)
        self.addAction(action)

        @QtCore.Slot(bool)
        def toggle_tooltip(checked: bool) -> None:
            self._show_tooltip = checked
            self.update()

        action = QtGui.QAction(self, 'Toggle Tooltip')
        action.setCheckable(True)
        action.setChecked(self._show_tooltip)
        action.setToolTip('Show/hide tooltip')
        action.setStatusTip('Show/hide tooltip')
        action.setWhatsThis('Show/hide tooltip')
        action.setShortcut(QtGui.QKeySequence('alt+3'))
        action.triggered.connect(toggle_tooltip)
        self.addAction(action)


class PieChartDockWidget(QtWidgets.QDockWidget):
    """Dockable wrapper around :class:`PieChartView`."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__('Pie Chart', parent)

        self.setObjectName('ExpenseTrackerPieChartDockWidget')
        self.setFeatures(
            QtWidgets.QDockWidget.DockWidgetMovable |
            QtWidgets.QDockWidget.DockWidgetFloatable |
            QtWidgets.QDockWidget.DockWidgetClosable
        )

        chart = PieChartView(self)
        chart.setProperty('rounded', True)
        chart.setObjectName('ExpenseTrackerPieChartView')
        self.setWidget(chart)

        self.setContentsMargins(0, 0, 0, 0)
        self.setMinimumSize(ui.Size.DefaultWidth(0.3), ui.Size.DefaultHeight(0.3))
