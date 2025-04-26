"""
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets

from ...data.data import get_trends
from ...settings import lib
from ...settings import locale as _locale
from ...ui import ui
from ...ui.actions import signals


def paint(func):  # type: ignore[valid-type]
    """Decorator to wrap paint helpers with save/restore + exception log."""

    def wrapper(self, painter: QtGui.QPainter) -> None:  # type: ignore[valid-type]
        painter.save()
        try:
            func(self, painter)
        except (Exception, BaseException) as ex:
            logging.error(f'TrendGraph: error in {func.__name__}', exc_info=ex)
        painter.restore()

    return wrapper


@dataclass
class Geometry:
    """All pixel-space objects bundled in one container."""
    area: QtCore.QRectF = field(default_factory=QtCore.QRectF)
    bars: list[QtCore.QRectF] = field(default_factory=list)
    trend_path: QtGui.QPainterPath = field(default_factory=QtGui.QPainterPath)
    trend_points: list[QtCore.QPointF] = field(default_factory=list)
    labels: list[tuple[QtGui.QStaticText, QtCore.QPointF]] = field(default_factory=list)
    baseline_y: float = 0.0
    data_min: float = 0.0
    data_max: float = 0.0


class TrendGraph(QtWidgets.QWidget):
    """Custom QWidget painting a bar-plus-trend chart."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._df: pd.DataFrame = pd.DataFrame()
        self._current_category: Optional[str] = None

        self._dates: pd.Index = pd.Index([])
        self._bar_series: pd.Series = pd.Series(dtype=float)
        self._trend_series: pd.Series = pd.Series(dtype=float)

        self._geom: Geometry = Geometry()

        self._show_bars: bool = True
        self._show_trend: bool = True
        self._show_axes: bool = True
        self._show_ticks: bool = True
        self._show_labels: bool = True
        self._show_tooltip: bool = True

        self._hover_index: Optional[int] = None
        self._hover_text: Optional[str] = None
        self._hover_pos: Optional[QtCore.QPoint] = None

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)

        self._connect_signals()
        self._init_actions()

    def _connect_signals(self) -> None:
        signals.categoryChanged.connect(self.set_category)
        # reload for current category when date range changes
        signals.dataRangeChanged.connect(self._on_data_range_changed)
        # clear trends on preset activation; categoryChanged will reload when needed
        signals.presetActivated.connect(self.clear_data)

    def _init_actions(self) -> None:
        """Placeholder for future QAction or context-menu wiring."""
        pass

    @QtCore.Slot(str, int)
    def _on_data_range_changed(self, yearmonth: str, span: int) -> None:
        """Reload current category trends when the date range changes."""
        logging.debug(f'TrendGraph: dataRangeChanged received yearmonth={yearmonth}, span={span}')
        # reload for the active category
        if self._current_category:
            self.set_category(self._current_category)

    @QtCore.Slot(str)
    def set_category(self, category: str) -> None:
        """Load and show trends for the specified category."""
        # clear if no valid category
        if not category:
            self.clear_data()
            return

        self._current_category = category
        # fetch category-specific trend data
        try:
            df = get_trends(category=category, negative_span=120)
        except Exception as exc:
            logging.error('TrendGraph: failed to fetch trends for %s: %s', category, exc)
            self.clear_data()
            return
        # if no data, clear and return
        if df.empty:
            logging.debug('TrendGraph: no trend data for category %s', category)
            self.clear_data()
            return
        # update series directly
        self._df = df
        self._dates = df['month']
        self._bar_series = df['monthly_total']
        self._trend_series = df['loess']
        # rebuild geometry and repaint
        self._rebuild_geometry()
        self.update()

    @QtCore.Slot(bool)
    def toggle_bars(self, visible: bool) -> None:
        self._show_bars = bool(visible)
        self.update()

    @QtCore.Slot(bool)
    def toggle_trend(self, visible: bool) -> None:
        self._show_trend = bool(visible)
        self.update()

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(ui.Size.DefaultWidth(1.0), ui.Size.DefaultHeight(1.0))

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        self._rebuild_geometry()
        super().resizeEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)

        self._draw_background(painter)
        if self._show_axes:
            self._draw_axes(painter)
        if self._show_ticks:
            self._draw_ticks(painter)
        if self._show_bars:
            self._draw_bars(painter)
        if self._show_trend:
            self._draw_trend(painter)
        if self._show_labels:
            self._draw_labels(painter)
        if self._hover_index is not None and self._show_tooltip:
            self._draw_tooltip(painter)

    @paint
    def _draw_background(self, painter: QtGui.QPainter) -> None:
        # fill background using app-defined color
        painter.fillRect(self.rect(), ui.Color.Background())

    @paint
    def _draw_axes(self, painter: QtGui.QPainter) -> None:
        """
        Draws the axes for a graphical representation using the provided painter object.

        This method uses the given `QtGui.QPainter` to draw the axes, including the
        vertical and horizontal axis lines, tick marks, and axis labels. It handles
        font settings, rendering hints, and axis legend placement appropriately
        based on geometrical and locale-specific settings.

        Args:
            painter: The `QtGui.QPainter` instance used to perform the drawing operations.

        """
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        geom = self._geom
        # use thin small font for axis legends
        font, _ = ui.Font.ThinFont(ui.Size.SmallText(1.0))
        painter.setFont(font)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        # use primary text color for axes lines and ticks
        painter.setPen(QtGui.QPen(ui.Color.Text()))

        painter.drawLine(geom.area.left(), geom.area.top(),
                         geom.area.left(), geom.area.bottom())
        painter.drawLine(geom.area.left(), geom.baseline_y,
                         geom.area.right(), geom.baseline_y)

        # Tick marks only at first and last bar
        tick = ui.Size.Separator(1.0)
        if geom.bars:
            for rect in (geom.bars[0], geom.bars[-1]):
                x = rect.x() + rect.width() / 2
                painter.drawLine(x, geom.baseline_y, x, geom.baseline_y + tick)
        # Y-axis legend: show data_max at top, data_min at baseline (inside area)
        # use secondary text color for labels
        # draw Y-axis labels in primary text color
        painter.setPen(QtGui.QPen(ui.Color.Text()))
        metrics = painter.fontMetrics()
        offset = ui.Size.Separator(2.0)
        # format axis labels according to user locale
        max_lbl = _locale.format_currency_value(geom.data_max, lib.settings['locale'])
        # draw to the right of y-axis
        painter.drawText(
            QtCore.QPointF(
                geom.area.left() + offset,
                geom.area.top() + metrics.ascent()
            ), max_lbl
        )
        min_lbl = _locale.format_currency_value(geom.data_min, lib.settings['locale'])
        painter.drawText(
            QtCore.QPointF(
                geom.area.left() + offset,
                geom.baseline_y
            ), min_lbl
        )
        # draw X-axis date labels under each bar, avoiding overlaps
        # set up small font and primary text color for axis labels
        date_font, metrics = ui.Font.ThinFont(ui.Size.SmallText(1.0))
        painter.setFont(date_font)
        painter.setPen(QtGui.QPen(ui.Color.Text()))
        metrics = painter.fontMetrics()
        pad = ui.Size.Indicator(1.0)
        bars = geom.bars
        dates = self._dates
        n = len(bars)
        if n > 0:
            # helper to measure and position each date label
            def make_label(i):
                rect_i = bars[i]
                dt = dates[i]
                try:
                    lbl = dt.strftime('%b %Y')
                except Exception:
                    lbl = str(dt)
                w = metrics.horizontalAdvance(lbl)
                h = metrics.height()
                cx = rect_i.x() + rect_i.width() / 2
                x0 = cx - w / 2
                y0 = geom.baseline_y + pad
                return lbl, QtCore.QRectF(x0, y0, w, h)

            # draw first and last labels (always)
            first_lbl, first_rect = make_label(0)
            painter.setBrush(ui.Color.Background())
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(first_rect)
            painter.setPen(QtGui.QPen(ui.Color.Text()))
            painter.drawText(QtCore.QPointF(first_rect.x(), first_rect.y() + metrics.ascent()), first_lbl)
            last_lbl, last_rect = make_label(n - 1)
            painter.setBrush(ui.Color.Background())
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(last_rect)
            painter.setPen(QtGui.QPen(ui.Color.Text()))
            painter.drawText(QtCore.QPointF(last_rect.x(), last_rect.y() + metrics.ascent()), last_lbl)
            # track occupied regions and draw intermediates that don't overlap
            occupied = [first_rect, last_rect]
            for i in range(1, n - 1):
                lbl, rct = make_label(i)
                if any(rct.intersects(o) for o in occupied):
                    continue
                painter.setBrush(ui.Color.Background())
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawRect(rct)
                painter.setPen(QtGui.QPen(ui.Color.Text()))
                painter.drawText(QtCore.QPointF(rct.x(), rct.y() + metrics.ascent()), lbl)
                occupied.append(rct)

    @paint
    def _draw_ticks(self, painter: QtGui.QPainter) -> None:
        """Draw moving tick-marks on both axes at hover position, with value labels."""
        geom = self._geom
        # need hover info
        pos = self._hover_pos
        if pos is None or not geom.bars:
            return
        # X-axis tick at hovered bar center
        idx = self._hover_index
        tick_len = ui.Size.Indicator(1.0)
        # use primary text color for tick marks
        painter.setPen(QtGui.QPen(ui.Color.Text()))
        if idx is not None and 0 <= idx < len(geom.bars):
            bar = geom.bars[idx]
            xh = bar.x() + bar.width() / 2
            painter.drawLine(xh, geom.baseline_y, xh, geom.baseline_y + tick_len)
        # Y-axis tick at mouse Y, clamped to chart area
        y = pos.y()
        if y < geom.area.top():
            y = geom.area.top()
        elif y > geom.area.bottom():
            y = geom.area.bottom()
        painter.drawLine(geom.area.left(), y, geom.area.left() + tick_len, y)
        # compute data value for this Y position
        data_min = geom.data_min
        data_max = geom.data_max
        span = geom.area.height()
        val = data_min
        if span > 0 and data_max != data_min:
            val = data_min + (geom.area.bottom() - y) / span * (data_max - data_min)
        # format label
        lbl = _locale.format_currency_value(val, lib.settings['locale'])
        # draw background rectangle for readability
        lbl_font, lbl_metrics = ui.Font.ThinFont(ui.Size.SmallText(1.0))
        painter.setFont(lbl_font)
        tw = lbl_metrics.horizontalAdvance(lbl)
        th = lbl_metrics.height()
        gap = ui.Size.Separator(1.0)
        x0 = geom.area.left() + tick_len + gap
        y0 = y
        bg = QtCore.QRectF(x0, y0, tw, th)
        # draw background for label using app color
        painter.setBrush(ui.Color.Background())
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(bg)
        # draw value text in primary color
        painter.setPen(QtGui.QPen(ui.Color.Text()))
        painter.drawText(QtCore.QPointF(x0, y0 + lbl_metrics.ascent()), lbl)

    @paint
    def _draw_bars(self, painter: QtGui.QPainter) -> None:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        geom = self._geom
        if not geom.bars:
            return
        cfg = lib.settings.get_section('categories') or {}
        base_color_rgb = cfg.get(self._current_category, {}) \
            .get('color', ui.Color.SecondaryText().name(QtGui.QColor.HexRgb))
        base_color = QtGui.QColor(base_color_rgb)
        base_alpha = 0.5

        # categorize bars by computed alpha
        pen = QtGui.QPen(QtCore.Qt.NoPen)
        pen.setCosmetic(True)
        pen.setWidthF(ui.Size.Separator(1.0))
        painter.setPen(pen)

        union_path: QtGui.QPainterPath | None = None
        for rect in geom.bars:
            rect_path = QtGui.QPainterPath()
            rect_path.addRoundedRect(
                rect,
                ui.Size.Separator(1.0),
                ui.Size.Separator(1.0),
            )
            if union_path is None:
                union_path = rect_path
            else:
                union_path = union_path.united(rect_path)

        # simplify to eliminate interior overlaps and redundant segments
        if not union_path:
            return

        union_path = union_path.simplified()
        full_color = QtGui.QColor(base_color)
        full_color.setAlphaF(base_alpha)
        painter.setBrush(QtGui.QBrush(full_color))
        painter.drawPath(union_path)

    @paint
    def _draw_trend(self, painter: QtGui.QPainter) -> None:
        geom = self._geom
        if geom.trend_path.isEmpty():
            return

        cfg = lib.settings.get_section('categories') or {}
        color = QtGui.QColor(
            cfg.get(self._current_category, {}).get('color', ui.Color.SecondaryText().name(QtGui.QColor.HexRgb)))

        pen = QtGui.QPen(color)
        pen.setCosmetic(True)
        pen.setWidthF(ui.Size.Indicator(1.0))
        # round line caps and joins for smoother rendering
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(geom.trend_path)

    @paint
    def _draw_labels(self, painter: QtGui.QPainter) -> None:
        """Draw the hovered date label beneath the chart with background."""
        geom = self._geom
        idx = self._hover_index
        if idx is None or not geom.labels or idx < 0 or idx >= len(geom.labels):
            return

        static_text, pos = geom.labels[idx]
        # draw background for legibility
        size = static_text.size()
        bg_rect = QtCore.QRectF(pos.x(), pos.y(), size.width(), size.height())
        painter.setBrush(self.palette().color(QtGui.QPalette.Window))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(bg_rect)
        # draw the date label text
        painter.setPen(QtGui.QPen(ui.Color.SecondaryText()))
        painter.drawStaticText(pos, static_text)

    @paint
    def _draw_tooltip(self, painter: QtGui.QPainter) -> None:
        """Draw hover highlight and tooltip."""
        if self._hover_index is None or not self._hover_text or self._hover_pos is None:
            return

        # highlight hovered bar
        bars = self._geom.bars
        idx = self._hover_index
        if 0 <= idx < len(bars):
            # highlight hovered bar
            pen = QtGui.QPen(ui.Color.Blue())
            pen.setWidthF(ui.Size.Separator(1.0))
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRect(bars[idx])
        # draw tooltip
        font, _ = ui.Font.BoldFont(ui.Size.MediumText(1.0))
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text = self._hover_text
        tw = metrics.horizontalAdvance(text)
        th = metrics.height()
        pad = ui.Size.Indicator(2.0)
        r = pad
        w = tw + pad * 2
        h = th + pad * 2
        mx = self._hover_pos.x()
        my = self._hover_pos.y()
        ax = self._geom.area
        x = mx - w / 2
        x = max(ax.left(), min(x, ax.right() - w))
        margin = ui.Size.Separator(3.0)
        y = my - h - margin
        if y < ax.top():
            y = my + margin
        tooltip_rect = QtCore.QRectF(x, y, w, h)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(ui.Color.DarkBackground())
        painter.drawRoundedRect(tooltip_rect, r, r)
        painter.setPen(QtGui.QPen(ui.Color.SecondaryText()))
        painter.drawText(QtCore.QPointF(x + pad, y + pad + metrics.ascent()), text)

    def _rebuild_geometry(self) -> None:
        """Populate self._geom from current data + widget size."""
        self._geom = Geometry()  # fresh slate
        geom = self._geom

        rect = self.contentsRect()
        m = ui.Size.Margin(2.0)
        geom.area = QtCore.QRectF(rect.adjusted(m, m, -m, -m))

        if self._bar_series.empty:
            return

        n = len(self._bar_series)
        # calculate bar width and gap; enforce minimum bar width and full span (allow overlap)
        w = geom.area.width()
        min_w = ui.Size.Indicator(1.0)
        if n == 1:
            bar_w = w
            step = bar_w
        else:
            default_gap = ui.Size.Separator(1.0)
            # initial bar width with a default gap
            bar_w = (w - default_gap * (n - 1)) / n
            if bar_w < min_w:
                # clamp to a minimum and compute a dynamic gap for full coverage
                bar_w = min_w
                gap = (w - bar_w * n) / (n - 1)
            else:
                gap = default_gap
            step = bar_w + gap

        # Determine original data range
        bar_min = self._bar_series.min(skipna=True)
        bar_max = self._bar_series.max(skipna=True)
        trend_min = self._trend_series.min(skipna=True)
        trend_max = self._trend_series.max(skipna=True)
        orig_min = min(bar_min, trend_min)
        orig_max = max(bar_max, trend_max)

        # Decide if only positive or only negative values
        only_positive = orig_min >= 0.0
        only_negative = orig_max <= 0.0

        if only_positive or only_negative:
            # Use absolute values and baseline at bottom
            values_for_bars = self._bar_series.abs()
            values_for_trend = self._trend_series.abs()
            data_min = 0.0
            data_max = max(values_for_bars.max(skipna=True),
                           values_for_trend.max(skipna=True))
            geom.baseline_y = geom.area.bottom()
        else:
            # Mixed values: keep sign, baseline proportional
            values_for_bars = self._bar_series
            values_for_trend = self._trend_series
            data_min = min(0.0, orig_min)
            data_max = max(0.0, orig_max)
            geom.baseline_y = geom.area.bottom() - (-data_min / (data_max - data_min or 1.0)) * geom.area.height()
        # clamp baseline within drawing area
        geom.baseline_y = max(min(geom.baseline_y, geom.area.bottom()), geom.area.top())

        # Store range for axis legend
        geom.data_min = data_min
        geom.data_max = data_max
        rng = data_max - data_min or 1.0

        # Bars
        for i in range(len(self._bar_series)):
            orig_val = self._bar_series.iat[i]
            val = values_for_bars.iat[i]
            x0 = geom.area.left() + i * step
            ratio = (val - data_min) / rng
            # clamp ratio to [0, 1]
            ratio = max(0.0, min(ratio, 1.0))
            pix_h = ratio * geom.area.height()
            if only_positive or only_negative:
                y0 = geom.baseline_y - pix_h
                h = pix_h
            else:
                if orig_val >= 0:
                    y0 = geom.baseline_y - pix_h
                    h = pix_h
                else:
                    y0 = geom.baseline_y
                    h = -pix_h
            geom.bars.append(QtCore.QRectF(x0, y0, bar_w, h))

        # Trend
        for i in range(len(self._trend_series)):
            orig_val = self._trend_series.iat[i]
            val = values_for_trend.iat[i]
            x = geom.area.left() + i * step + bar_w / 2
            ratio = (val - data_min) / rng
            # clamp ratio to [0, 1]
            ratio = max(0.0, min(ratio, 1.0))
            y = geom.area.bottom() - ratio * geom.area.height()
            pt = QtCore.QPointF(x, y)
            geom.trend_points.append(pt)
            if i == 0:
                geom.trend_path.moveTo(pt)
            else:
                geom.trend_path.lineTo(pt)

        # labels
        for i, ts in enumerate(self._dates):
            x_c = geom.area.left() + i * step + bar_w / 2
            txt = QtGui.QStaticText(pd.Timestamp(ts).strftime('%b %Y'))
            size = txt.size()
            pos = QtCore.QPointF(x_c - size.width() / 2,
                                 geom.baseline_y + ui.Size.Indicator(1.0))
            geom.labels.append((txt, pos))

    @QtCore.Slot()
    def clear_data(self) -> None:
        # clear current data
        self._df = pd.DataFrame()
        self._current_category = None

        self._dates = pd.Index([])
        self._bar_series = pd.Series(dtype=float)
        self._trend_series = pd.Series(dtype=float)

        self._geom = Geometry()
        self.update()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """Show tooltip and highlight label when hovering over a bar."""
        pos = event.pos()
        # record mouse position for tooltip anchoring
        self._hover_pos = pos
        hovered: Optional[int] = None
        # detect nearest bar within a horizontal tolerance
        tol = ui.Size.Margin(1.0)
        best_dist = float('inf')
        for idx, rect in enumerate(self._geom.bars):
            cx = rect.x() + rect.width() / 2
            dist = abs(pos.x() - cx)
            if dist < best_dist:
                best_dist = dist
                hovered = idx
        # if outside tolerance, clear hover
        if best_dist > tol:
            hovered = None
        # update hover state
        if hovered != self._hover_index:
            self._hover_index = hovered
            if hovered is not None:
                # prepare custom tooltip text using locale currency formatting
                date_str = pd.Timestamp(self._dates[hovered]).strftime('%b %Y')
                total = self._bar_series.iat[hovered]
                total_str = _locale.format_currency_value(total, lib.settings['locale'])
                self._hover_text = f"{date_str}: {total_str}"
            else:
                self._hover_text = None
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        """Clear hover state when mouse leaves widget."""
        if self._hover_index is not None or self._hover_text is not None:
            self._hover_index = None
            self._hover_text = None
            self._hover_pos = None
            self.update()
        super().leaveEvent(event)
