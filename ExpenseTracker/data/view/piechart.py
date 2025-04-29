import logging
import math
from typing import Optional

from PySide6 import QtWidgets, QtCore, QtGui

from ...data import data
from ...settings import lib, locale
from ...ui import ui
from ...ui.ui import get_icon, CategoryIconEngine


def paint(func):  # type: ignore[valid-type]
    """Decorator to wrap paint helpers with save/restore + exception log."""

    def wrapper(self, painter: QtGui.QPainter) -> None:
        painter.save()
        try:
            func(self, painter)
        except Exception as ex:
            logging.error(f'PieChartView: error in {func.__name__}', exc_info=ex)
        painter.restore()

    return wrapper

class PieChartView(QtWidgets.QWidget):
    """Widget to display expense distribution as an exploded pie chart."""

    def __init__(self, parent: QtWidgets.QWidget = None) -> None:
        super().__init__(parent)
        self._slices: dict[int, dict] = {}
        self._slice_geoms: list[dict] = []
        self._hover_index: Optional[int] = None
        self._hover_pos: Optional[QtCore.QPoint] = None

        self.setMouseTracking(True)
        self._create_ui()
        self._connect_signals()
        self._init_actions()
        QtCore.QTimer.singleShot(100, self.init_data)

    def _create_ui(self) -> None:
        self.setMinimumSize(ui.Size.DefaultWidth(), ui.Size.DefaultHeight())
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding,
        )

    def _connect_signals(self) -> None:
        from ...ui.actions import signals
        signals.configSectionChanged.connect(self.init_data)
        signals.dataRangeChanged.connect(self.init_data)

    def _init_actions(self) -> None:
        pass

    def init_data(self) -> None:
        df = data.get_data()
        df = df[(df['category'] != 'Total') & (df['category'] != '')]
        if not lib.settings['exclude_negative'] and not lib.settings['exclude_positive']:
            logging.warning('PieChartView requires exclusively positive or negative totals')
            self._slices.clear()
            return

        df = df[df['total'] > 0] if lib.settings['exclude_negative'] else df[df['total'] < 0]
        df = df.reset_index(drop=True)
        if df.empty or df['total'].abs().sum() == 0:
            logging.warning('PieChartView has no data to display')
            self._slices.clear()
            return

        total_abs = df['total'].abs().sum()
        qt_circle = 360 * 16
        rotation = 90 * 16

        spans: list[tuple[int, int, float]] = []
        for idx, row in df.iterrows():
            span = int(round(abs(row['total']) / total_abs * qt_circle))
            spans.append((idx, span, abs(row['total'])))

        used = sum(s for _, s, _ in spans)
        leftover = qt_circle - used
        if leftover:
            largest = max(spans, key=lambda x: x[2])[0]
            for i, (idx, s, amt) in enumerate(spans):
                if idx == largest:
                    spans[i] = (idx, s + leftover, amt)
                    break
            logging.debug('PieChartView: distributed %s units rounding residue', leftover)

        self._slices.clear()
        angle = 0
        config = lib.settings.get_section('categories') or {}
        for idx, span, _ in spans:
            row = df.loc[idx]
            cat = row['category']
            amt = locale.format_currency_value(abs(row['total']), lib.settings['locale'])
            color_str = config.get(cat, {}).get('color', ui.Color.Text().name(QtGui.QColor.HexRgb))
            color = QtGui.QColor(color_str) if QtGui.QColor(color_str).isValid() else ui.Color.Text()
            icon_name = config.get(cat, {}).get('icon', 'cat_unclassified')
            self._slices[idx] = {
                'category': cat,
                'amount': amt,
                'start_angle': (angle + rotation) % qt_circle,
                'span_angle': span,
                'color': color,
                'icon': icon_name,
            }
            angle += span

        self._hover_index = None
        self._hover_pos = None

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        self._slice_geoms.clear()
        self._draw_background(painter)

        widget_rect = self.rect()
        edge = min(widget_rect.width(), widget_rect.height())
        square = QtCore.QRect(
            widget_rect.x() + (widget_rect.width() - edge) // 2,
            widget_rect.y() + (widget_rect.height() - edge) // 2,
            edge, edge,
        )
        margin = ui.Size.Margin(1.0)
        square = square.adjusted(margin, margin, -margin, -margin)

        min_off = ui.Size.Indicator(1.0)
        max_off = ui.Size.Indicator(10.0)
        pie_radius = (square.width() - 2 * margin) / 2.0
        max_off_clip = min(max_off, pie_radius * 0.30)
        pie_rect = square.adjusted(
            int(margin + max_off_clip), int(margin + max_off_clip),
            -int(margin + max_off_clip), -int(margin + max_off_clip),
        )

        for sl in self._slices.values():
            geom = self._draw_segment(painter, pie_rect, sl, min_off, max_off_clip)
            if geom:
                self._slice_geoms.append(geom)

        self._draw_legend(painter)
        self._draw_icons(painter)
        self._draw_tooltip(painter)

    @paint
    def _draw_background(self, painter: QtGui.QPainter) -> None:
        if self.property('rounded'):
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(ui.Color.Background())
            painter.drawRoundedRect(self.rect(), ui.Size.Indicator(2.0), ui.Size.Indicator(2.0))
        else:
            painter.fillRect(self.rect(), ui.Color.VeryDarkBackground())
        o = ui.Size.Margin(1.0)
        r = self.rect().adjusted(o, o, -o, -o)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(ui.Color.DarkBackground())
        rad = ui.Size.Indicator(2.0)
        painter.drawRoundedRect(r, rad, rad)

    # @paint
    def _draw_segment(self, painter: QtGui.QPainter,
                      pie_rect: QtCore.QRect,
                      sl: dict,
                      min_off: float,
                      max_off: float) -> Optional[dict]:
        start = sl['start_angle']
        span = sl['span_angle']
        col = sl['color']
        alpha = math.radians(span / 16.0)
        half = alpha / 2.0
        t_raw = 0.0 if half <= 0 else min_off / (2.0 * math.sin(half))
        t = max(min_off, min(t_raw, max_off))
        mid = (start + span / 2) / 16.0
        theta = math.radians(mid)
        dx = int(round(t * math.cos(theta)))
        dy = int(round(-t * math.sin(theta)))
        rect = QtCore.QRect(pie_rect)
        rect.translate(dx, dy)
        painter.setBrush(QtGui.QBrush(col))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawPie(rect, start, span)
        return {
            'slice_rect': rect,
            'mid_deg': mid,
            'span': span / 16.0,
            'category': sl['category'],
            'amount': sl['amount'],
            'color': col,
            'icon': sl['icon'],
        }

    @paint
    def _draw_legend(self, painter: QtGui.QPainter) -> None:
        if not self._slice_geoms:
            return
        first = self._slice_geoms[0]['slice_rect']
        center = first.center()
        radius = first.width() / 2.0
        font, metrics = ui.Font.BoldFont(ui.Size.MediumText())
        painter.setFont(font)
        pad = ui.Size.Indicator(2.0)
        for g in self._slice_geoms:
            # label position
            theta = math.radians(g['mid_deg'])
            x = center.x() + (radius + pad * 2) * math.cos(theta)
            y = center.y() - (radius + pad * 2) * math.sin(theta)

            # text and background size
            label = g['amount']
            w = metrics.horizontalAdvance(label)
            h = metrics.height()
            bg = QtCore.QRectF(
                x - w / 2 - pad,
                y - h / 2 - pad,
                w + pad * 2,
                h + pad * 2,
            )

            # draw semi-transparent background
            painter.save()
            painter.setOpacity(0.5)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(ui.Color.VeryDarkBackground())
            painter.drawRoundedRect(bg, pad, pad)
            painter.restore()

            # draw text label
            painter.setPen(QtGui.QPen(ui.Color.Text()))
            painter.drawText(
                QtCore.QPointF(
                    bg.x() + pad,
                    bg.y() + pad + metrics.ascent(),
                ),
                label,
            )

    @paint
    def _draw_icons(self, painter: QtGui.QPainter) -> None:
        if not self._slice_geoms:
            return
        first = self._slice_geoms[0]['slice_rect']
        center = first.center()
        radius = first.width() / 2.0
        icon_size = ui.Size.Margin(1.5)
        for g in self._slice_geoms:
            if g['span'] < 30.0:
                continue
            theta = math.radians(g['mid_deg'])
            x = center.x() + (radius * 0.5) * math.cos(theta) - icon_size / 2
            y = center.y() - (radius * 0.5) * math.sin(theta) - icon_size / 2
            icon = get_icon(g['icon'], color=g['color'].darker(150), engine=CategoryIconEngine)
            pix = icon.pixmap(icon_size, icon_size)
            painter.drawPixmap(int(x), int(y), pix)

    @paint
    def _draw_tooltip(self, painter: QtGui.QPainter) -> None:
        """Draw tooltip for the currently hovered slice."""
        if self._hover_index is None or self._hover_pos is None:
            return

        # retrieve slice info and mouse position
        g = self._slice_geoms[self._hover_index]
        pos = self._hover_pos

        # prepare text and icon
        text = f"{g['category']}: {g['amount']}"
        font, metrics = ui.Font.BoldFont(ui.Size.MediumText())
        painter.setFont(font)
        tw = metrics.horizontalAdvance(text)
        th = metrics.height()

        icon = get_icon(g['icon'], color=g['color'], engine=CategoryIconEngine)
        icon_size = th

        pad = ui.Size.Indicator(2.0)
        tooltip_w = icon_size + pad + tw + pad * 2
        tooltip_h = icon_size + pad * 2

        # position the tooltip rectangle
        x = pos.x() - tooltip_w / 2
        x = max(self.rect().left(), min(x, self.rect().right() - tooltip_w))
        margin = ui.Size.Separator(3.0)
        y = pos.y() - tooltip_h - margin
        if y < self.rect().top():
            y = pos.y() + margin

        bg = QtCore.QRectF(x, y, tooltip_w, tooltip_h)

        # draw background
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(ui.Color.DarkBackground())
        painter.drawRoundedRect(bg, pad, pad)

        # draw icon
        painter.drawPixmap(
            int(bg.x() + pad), int(bg.y() + pad),
            icon.pixmap(icon_size, icon_size),
        )

        # draw text
        painter.setPen(QtGui.QPen(ui.Color.Text()))
        painter.drawText(
            QtCore.QPointF(
                bg.x() + pad + icon_size + pad,
                bg.y() + pad + metrics.ascent(),
            ),
            text,
        )

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        pos = event.pos()
        self._hover_pos = pos
        hit: Optional[int] = None
        tol = ui.Size.Indicator(1.0)
        for i, g in enumerate(self._slice_geoms):
            if g['slice_rect'].adjusted(-tol, -tol, tol, tol).contains(pos):
                hit = i
                break
        if hit != self._hover_index:
            self._hover_index = hit
        self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        if self._hover_index is not None:
            self._hover_index = None
            self._hover_pos = None
            self.update()
        super().leaveEvent(event)

class PieChartDockWidget(QtWidgets.QDockWidget):
    """Dockable widget wrapping the PieChartView chart."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__('Pie Chart', parent=parent)
        self.setObjectName('ExpenseTrackerPieChartDockWidget')
        self.setFeatures(
            QtWidgets.QDockWidget.DockWidgetMovable |
            QtWidgets.QDockWidget.DockWidgetFloatable
        )
        chart = PieChartView(parent=self)
        chart.setProperty('rounded', True)
        chart.setObjectName('ExpenseTrackerPieChartView')
        self.setWidget(chart)
        self.setContentsMargins(0, 0, 0, 0)
        self.setMinimumSize(
            ui.Size.DefaultWidth(0.3),
            ui.Size.DefaultHeight(0.3),
        )
        self.setMaximumHeight(ui.Size.DefaultHeight(0.5))
        self.visibilityChanged.connect(self._on_visibility_changed)

    @QtCore.Slot(bool)
    def _on_visibility_changed(self, visible: bool) -> None:
        if visible:
            self.widget().init_data()