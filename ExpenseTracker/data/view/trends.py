"""Trend graph visualization and dock widget.

This module provides:
    - Span: predefined span selections for negative lookback
    - paint decorator: wraps paint helpers with save/restore and error logging
    - Geometry: container for calculated drawing regions
    - TrendGraph: custom QWidget showing bar and LOESS trend lines
    - TrendDockWidget: dockable wrapper around TrendGraph
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets

from ...core.sync import sync_manager
from ...data.data import get_trends
from ...settings import lib
from ...settings import locale
from ...ui import ui
from ...ui.actions import signals


class Span(Enum):
    """Predefined negative span durations for TrendGraph menu."""
    THREE_MONTHS = (3, '3 Months')
    SIX_MONTHS = (6, '6 Months')
    ONE_YEAR = (12, '1 Year')
    TWO_YEARS = (24, '2 Years')
    FIVE_YEARS = (60, '5 Years')
    TEN_YEARS = (120, '10 Years')
    TWENTY_YEARS = (240, '20 Years')

    def __init__(self, months: int, label: str) -> None:
        self.months = months
        self.label = label


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
        self._current_category: str = ''

        self._dates: pd.Index = pd.Index([])
        self._bar_series: pd.Series = pd.Series(dtype=float)
        self._trend_series: pd.Series = pd.Series(dtype=float)

        self._geom: Geometry = Geometry()

        self._is_paused = None

        self._show_axes: bool = False
        self._show_bars: bool = True
        self._show_trend: bool = True
        self._show_ticks: bool = True
        self._show_labels: bool = True
        self._show_tooltip: bool = True

        self._hover_index: Optional[int] = None
        self._hover_text: Optional[str] = None
        self._hover_pos: Optional[QtCore.QPoint] = None

        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self._init_data_timer = QtCore.QTimer(self)
        self._init_data_timer.setSingleShot(True)
        self._init_data_timer.setInterval(QtWidgets.QApplication.keyboardInputInterval())

        self._connect_signals()
        self._init_actions()

    @QtCore.Slot()
    def start_init_data_timer(self) -> None:
        self._init_data_timer.start(self._init_data_timer.interval())

    def _connect_signals(self) -> None:
        signals.categoryChanged.connect(self.set_category)
        signals.categoryChanged.connect(self.start_init_data_timer)

        signals.presetAboutToBeActivated.connect(self.clear_data)
        signals.dataAboutToBeFetched.connect(self.clear_data)
        signals.dataFetched.connect(self.init_data)

        self._init_data_timer.timeout.connect(self.init_data)

        @QtCore.Slot(str, object)
        def metadata_changed(key: str, value: object) -> None:
            self.start_init_data_timer()

        signals.metadataChanged.connect(metadata_changed)
        # reload trends when local cache is updated by sync
        sync_manager.dataUpdated.connect(lambda ops: self.start_init_data_timer())

    def _init_actions(self) -> None:
        """Set up context-menu actions for toggles, span selection, and smoothing."""
        bars_action = QtGui.QAction('Show Bars', self, checkable=True)
        bars_action.setChecked(self._show_bars)
        bars_action.toggled.connect(self.toggle_bars)
        bars_action.setToolTip('Show or hide the bars')
        bars_action.setStatusTip('Show or hide the bars')
        bars_action.setWhatsThis('Show or hide the bars')
        bars_action.setShortcut('alt+1')
        self.addAction(bars_action)

        trend_action = QtGui.QAction('Show Trend', self, checkable=True)
        trend_action.setChecked(self._show_trend)
        trend_action.toggled.connect(self.toggle_trend)
        trend_action.setToolTip('Show or hide the trend line')
        trend_action.setStatusTip('Show or hide the trend line')
        trend_action.setWhatsThis('Show or hide the trend line')
        trend_action.setShortcut('alt+2')
        self.addAction(trend_action)

        axes_action = QtGui.QAction('Show Axes', self, checkable=True)
        axes_action.setChecked(self._show_axes)
        axes_action.toggled.connect(self.toggle_axes)
        axes_action.setToolTip('Show or hide the axes')
        axes_action.setStatusTip('Show or hide the axes')
        axes_action.setWhatsThis('Show or hide the axes')
        axes_action.setShortcut('alt+3')
        self.addAction(axes_action)

        ticks_action = QtGui.QAction('Show Ticks', self, checkable=True)
        ticks_action.setChecked(self._show_ticks)
        ticks_action.toggled.connect(self.toggle_ticks)
        ticks_action.setToolTip('Show or hide the tick marks')
        ticks_action.setStatusTip('Show or hide the tick marks')
        ticks_action.setWhatsThis('Show or hide the tick marks')
        ticks_action.setShortcut('alt+4')
        self.addAction(ticks_action)

        labels_action = QtGui.QAction('Show Labels', self, checkable=True)
        labels_action.setChecked(self._show_labels)
        labels_action.toggled.connect(self.toggle_labels)
        labels_action.setToolTip('Show or hide the labels')
        labels_action.setStatusTip('Show or hide the labels')
        labels_action.setWhatsThis('Show or hide the labels')
        labels_action.setShortcut('alt+5')
        self.addAction(labels_action)

        tooltip_action = QtGui.QAction('Show Tooltip', self, checkable=True)
        tooltip_action.setChecked(self._show_tooltip)
        tooltip_action.toggled.connect(self.toggle_tooltip)
        tooltip_action.setToolTip('Show or hide the tooltip')
        tooltip_action.setStatusTip('Show or hide the tooltip')
        tooltip_action.setWhatsThis('Show or hide the tooltip')
        tooltip_action.setShortcut('alt+6')
        self.addAction(tooltip_action)

        @QtCore.Slot()
        def set_negative_span(a: QtGui.QAction) -> None:
            lib.settings['negative_span'] = a.data().months

        # Separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        self.addAction(action)

        # Span selection submenu
        span_menu = QtWidgets.QMenu('Span', self)
        span_group = QtGui.QActionGroup(self)
        span_group.setExclusive(True)
        for span in Span:
            act = QtGui.QAction(span.label, self, checkable=True)
            act.setChecked(lib.settings['negative_span'] == span.months)
            act.setData(span)
            span_group.addAction(act)
            span_menu.addAction(act)
        span_group.triggered.connect(set_negative_span)
        self.addAction(span_menu.menuAction())

        # Separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        self.addAction(action)

        # Loess fraction adjustment action
        smooth_action = QtGui.QAction('Adjust Smoothing...', self)
        smooth_action.triggered.connect(self.open_loess_dialog)
        self.addAction(smooth_action)

    @QtCore.Slot(str)
    def set_category(self, category: str) -> None:
        """Load and show trends for the specified category."""
        if not category:
            self._current_category = ''
            return

        self._current_category = category

    @QtCore.Slot()
    def init_data(self) -> None:
        # fetch category-specific trend data
        try:
            logging.debug(f'TrendGraph: fetching trends for {self._current_category}', )
            df = get_trends(
                category=self._current_category,
                negative_span=lib.settings['negative_span'],
                loess_fraction=lib.settings['loess_fraction']
            )
        except Exception as exc:
            logging.error(f'TrendGraph: failed to fetch trends for {self._current_category}: {exc}')
            self.clear_data()
            return

        # if no data, clear and return
        if df.empty:
            logging.debug(f'TrendGraph: no trend data for category {self._current_category}')
            self.clear_data()
            return

        # update series directly
        self._df = df
        self._dates = df['month']
        self._bar_series = df['monthly_total']
        self._trend_series = df['loess']

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

    @QtCore.Slot(bool)
    def toggle_axes(self, visible: bool) -> None:
        """Toggle axis visibility."""
        self._show_axes = bool(visible)
        self.update()

    @QtCore.Slot(bool)
    def toggle_ticks(self, visible: bool) -> None:
        """Toggle tick marks visibility."""
        self._show_ticks = bool(visible)
        self.update()

    @QtCore.Slot(bool)
    def toggle_labels(self, visible: bool) -> None:
        """Toggle labels visibility."""
        self._show_labels = bool(visible)
        self.update()

    @QtCore.Slot(bool)
    def toggle_tooltip(self, visible: bool) -> None:
        """Toggle tooltip visibility."""
        self._show_tooltip = bool(visible)
        self.update()

    @QtCore.Slot()
    def open_loess_dialog(self) -> None:
        """Open a dialog to adjust the LOESS smoothing fraction.

        """
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle('Adjust Smoothing Fraction')
        layout = QtWidgets.QVBoxLayout(dialog)
        label = QtWidgets.QLabel(f'Loess Fraction: {lib.settings["loess_fraction"]:.2f}', dialog)
        layout.addWidget(label)
        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, dialog)
        slider.setMinimum(1)
        slider.setMaximum(100)
        slider.setValue(int(lib.settings['loess_fraction'] * 100))
        layout.addWidget(slider)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            parent=dialog
        )
        layout.addWidget(buttons)
        original = lib.settings['loess_fraction']

        def on_slider(val: int) -> None:
            frac = float(val / 100.0)
            label.setText(f'Loess Fraction: {frac:.2f}')
            lib.settings['loess_fraction'] = frac

        slider.valueChanged.connect(on_slider)
        buttons.accepted.connect(dialog.accept)

        def on_reject() -> None:
            lib.settings['loess_fraction'] = original
            if self._current_category:
                self.set_category(self._current_category)
            dialog.reject()

        buttons.rejected.connect(on_reject)
        dialog.exec()

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(ui.Size.DefaultWidth(1.0), ui.Size.DefaultHeight(1.0))

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        self._rebuild_geometry()
        super().resizeEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        if self._is_paused:
            return

        painter = QtGui.QPainter(self)

        # Check if the bottom axis is near the top
        small = self._geom.baseline_y < self._geom.area.top() + ui.Size.Margin(0.5)

        self._draw_background(painter)

        if small:
            return

        if self._show_axes:
            self._draw_axes(painter)
        if self._show_bars:
            self._draw_bars(painter)
        if self._show_ticks:
            self._draw_ticks(painter)
        if self._show_trend:
            self._draw_trend(painter)
        if self._show_labels:
            self._draw_labels(painter)
        if self._show_tooltip:
            self._draw_tooltip(painter)

    @paint
    def _draw_background(self, painter: QtGui.QPainter) -> None:
        # fill background using app-defined color
        if self.property('rounded'):
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(ui.Color.VeryDarkBackground())
            painter.drawRoundedRect(self.rect(), ui.Size.Indicator(2.0), ui.Size.Indicator(2.0))
        else:
            painter.fillRect(self.rect(), ui.Color.VeryDarkBackground())

        o = ui.Size.Margin(1.0)
        rect = self.rect().adjusted(o, o, -o, -o)

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(ui.Color.DarkBackground())

        o = ui.Size.Indicator(2.0)
        painter.drawRoundedRect(rect, o, o)

    @paint
    def _draw_axes(self, painter: QtGui.QPainter) -> None:
        def make_label(_i, _metrics):
            rect_i = bars[_i]
            dt = dates[_i]
            try:
                _lbl = dt.strftime('%b %Y')
            except:
                _lbl = str(dt)
            w = _metrics.horizontalAdvance(_lbl)
            cx = rect_i.x() + rect_i.width() / 2
            x0 = cx - w / 2
            y0 = geom.baseline_y + pad

            bounding_rect = _metrics.boundingRect(_lbl)
            padding = ui.Size.Indicator(2.0)
            return _lbl, QtCore.QRectF(x0, y0, bounding_rect.width() + padding, bounding_rect.height())

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        geom = self._geom

        # use thin small font for axis legends
        font, _ = ui.Font.ThinFont(ui.Size.SmallText(1.0))
        painter.setFont(font)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        # get theme color
        config = lib.settings.get_section('categories') or {}
        color = QtGui.QColor(
            config.get(self._current_category, {}).get('color', ui.Color.SecondaryText().name(QtGui.QColor.HexRgb)))

        painter.setPen(color.darker(120))

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
        max_lbl = locale.format_currency_value(geom.data_max, lib.settings['locale'])
        # draw to the right of y-axis
        painter.drawText(
            QtCore.QPointF(
                geom.area.left() + offset,
                geom.area.top() + metrics.ascent()
            ), max_lbl
        )
        min_lbl = locale.format_currency_value(geom.data_min, lib.settings['locale'])
        painter.drawText(
            QtCore.QPointF(
                geom.area.left() + offset,
                geom.baseline_y
            ), min_lbl
        )

        # draw X-axis date labels under each bar, avoiding overlaps
        # set up small font and primary text color for axis labels
        font, metrics = ui.Font.ThinFont(ui.Size.SmallText(1.0))
        painter.setFont(font)
        painter.setPen(QtGui.QPen(ui.Color.Text()))

        pad = ui.Size.Indicator(1.0)
        bars = geom.bars
        dates = self._dates

        n = len(bars)

        if n > 0:
            painter.setPen(QtGui.QPen(ui.Color.Text()))
            painter.setBrush(QtCore.Qt.NoBrush)

            # draw first and last labels (always)
            first_lbl, first_rect = make_label(0, metrics)
            painter.drawText(first_rect, first_lbl, QtCore.Qt.AlignCenter)
            last_lbl, last_rect = make_label(n - 1, metrics)
            painter.drawText(last_rect, last_lbl, QtCore.Qt.AlignCenter)

            # track occupied regions and draw intermediates that don't overlap
            occupied = [first_rect, last_rect]
            j = 0
            for i in range(1, n - 1):
                lbl, rct = make_label(i, metrics)
                if any(rct.intersects(o) for o in occupied):
                    continue

                if j % 2 == 1:
                    painter.drawText(rct, lbl, QtCore.Qt.AlignCenter)
                j += 1
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

        # categorize bars by computed alpha
        pen = QtGui.QPen(QtCore.Qt.NoPen)
        pen.setCosmetic(True)
        pen.setWidthF(ui.Size.Separator(1.0))
        painter.setPen(pen)

        theme_color = ui.Color.VeryDarkBackground()
        # blend base color with theme color
        rate = 0.5
        blend_color = QtGui.QColor(
            int(base_color.red() * rate + theme_color.red() * (1 - rate)),
            int(base_color.green() * rate + theme_color.green() * (1 - rate)),
            int(base_color.blue() * rate + theme_color.blue() * (1 - rate))
        )

        # simplify to eliminate interior overlaps and redundant segments
        painter.setBrush(blend_color)
        for rect in geom.bars:
            painter.drawRoundedRect(rect, ui.Size.Indicator(0.5), ui.Size.Indicator(0.5))

    @paint
    def _draw_trend(self, painter: QtGui.QPainter) -> None:
        geom = self._geom
        if geom.trend_path.isEmpty():
            return

        cfg = lib.settings.get_section('categories') or {}
        color = QtGui.QColor(
            cfg.get(self._current_category, {}).get('color', ui.Color.SecondaryText().name(QtGui.QColor.HexRgb)))

        painter.setBrush(QtCore.Qt.NoBrush)

        pen = QtGui.QPen(color)
        pen.setCosmetic(True)
        pen.setWidthF(ui.Size.Indicator(1.0))
        pen.setCapStyle(QtCore.Qt.RoundCap)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        painter.setPen(pen)

        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.drawPath(geom.trend_path)

    @paint
    def _draw_labels(self, painter: QtGui.QPainter) -> None:
        """Draw the hovered date label beneath the chart with background."""
        geom = self._geom
        idx = self._hover_index
        if idx is None or not geom.labels or idx < 0 or idx >= len(geom.labels):
            return

        static_text, pos = geom.labels[idx]
        # prepare font and styling for labels
        lbl_font, metrics = ui.Font.ThinFont(ui.Size.SmallText(1.0))
        painter.setFont(lbl_font)
        text_color = ui.Color.Text()
        bg_color = ui.Color.Background()
        pad = ui.Size.Indicator(2.0)
        # draw background and text for hovered date label (x-axis)
        size = static_text.size()
        bg_rect = QtCore.QRectF(
            pos.x() - pad,
            pos.y() - pad,
            size.width() + pad * 2,
            size.height() + pad * 2
        )
        painter.setBrush(bg_color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(bg_rect, pad, pad)
        painter.setPen(QtGui.QPen(text_color))
        painter.drawStaticText(pos, static_text)
        # draw hovered value label on y-axis, same styling
        if self._hover_pos is not None:
            y = self._hover_pos.y()
            # clamp to chart area
            y = max(geom.area.top(), min(y, geom.area.bottom()))
            # compute corresponding data value
            data_min = geom.data_min
            data_max = geom.data_max
            span = geom.area.height()
            val = data_min
            if span > 0 and data_max != data_min:
                val = data_min + (geom.area.bottom() - y) / span * (data_max - data_min)
            amt_lbl = locale.format_currency_value(val, lib.settings['locale'])
            w = metrics.horizontalAdvance(amt_lbl)
            h = metrics.height()
            # position to the right of y-axis
            tick_len = ui.Size.Indicator(1.0)
            x0 = geom.area.left() + tick_len + pad
            y0 = y - h / 2
            bg2 = QtCore.QRectF(
                x0 - pad,
                y0 - pad,
                w + pad * 2,
                h + pad * 2
            )
            painter.setBrush(bg_color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(bg2, pad, pad)
            painter.setPen(QtGui.QPen(text_color))
            painter.drawText(
                QtCore.QPointF(x0, y0 + metrics.ascent()),
                amt_lbl
            )

    @paint
    def _draw_tooltip(self, painter: QtGui.QPainter) -> None:
        """Draw hover highlight and tooltip."""
        if self._hover_index is None or not self._hover_text or self._hover_pos is None:
            return

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        # highlight hovered bar
        bars = self._geom.bars
        idx = self._hover_index

        # get cat color
        cfg = lib.settings.get_section('categories') or {}
        color = QtGui.QColor(
            cfg.get(self._current_category, {}).get('color', ui.Color.SecondaryText().name(QtGui.QColor.HexRgb)))

        if 0 <= idx < len(bars):
            # highlight hovered bar
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(color)

            o = ui.Size.Indicator(0.5)
            _o = ui.Size.Separator(1.0)
            painter.drawRoundedRect(
                bars[idx].adjusted(
                    -_o, -_o, _o, _o
                ),
                o, o
            )

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
        painter.setPen(QtCore.Qt.NoPen)
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

        # Determine original data range based solely on bar values to avoid sign flips
        bar_min = self._bar_series.min(skipna=True)
        bar_max = self._bar_series.max(skipna=True)
        orig_min = bar_min
        orig_max = bar_max

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
        # clear current data (preserve selected category)
        self._df = pd.DataFrame()
        # do not reset _current_category here
        self._dates = pd.Index([])
        self._bar_series = pd.Series(dtype=float)
        self._trend_series = pd.Series(dtype=float)

        self._geom = Geometry()
        self.update()

    @QtCore.Slot()
    def pause(self) -> None:
        """Pauses automatic fetching of new log messages."""
        self._is_paused = True

    @QtCore.Slot()
    def resume(self) -> None:
        """Resumes automatic fetching of new log messages."""
        self._is_paused = False

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """Show tooltip and highlight label when hovering over a bar."""
        pos = event.pos()
        # record mouse position for tooltip anchoring
        self._hover_pos = pos
        hovered: Optional[int] = None

        # detect hover by checking proximity to each bar rectangle
        tol = ui.Size.Margin(1.0)
        ptf = QtCore.QPointF(pos.x(), pos.y())
        for idx, rect in enumerate(self._geom.bars):
            hit_rect = rect.adjusted(-tol, -tol, tol, tol)
            if hit_rect.contains(ptf):
                hovered = idx
                break

        # update hover state
        if hovered != self._hover_index:
            self._hover_index = hovered
            if hovered is not None:
                # prepare custom tooltip text using locale currency formatting
                date_str = pd.Timestamp(self._dates[hovered]).strftime('%b %Y')
                total = self._bar_series.iat[hovered]
                total_str = locale.format_currency_value(total, lib.settings['locale'])
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


class TrendDockWidget(QtWidgets.QDockWidget):
    """Dockable widget wrapping the TrendGraph chart."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__('Trends', parent=parent)
        self.setObjectName('ExpenseTrackerTrendDockWidget')
        self.setFeatures(
            QtWidgets.QDockWidget.DockWidgetMovable |
            QtWidgets.QDockWidget.DockWidgetFloatable |
            QtWidgets.QDockWidget.DockWidgetClosable
        )

        graph = TrendGraph(self)
        graph.setProperty('rounded', True)
        graph.setObjectName('ExpenseTrackerTrendGraph')
        self.setWidget(graph)

        self.setContentsMargins(0, 0, 0, 0)
        self.setMinimumSize(
            ui.Size.DefaultWidth(0.3),
            ui.Size.DefaultHeight(0.3),
        )

        self._connect_signals()

    def _connect_signals(self) -> None:
        self.visibilityChanged.connect(self.on_visibility_changed)

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(0.5)
        )

    @QtCore.Slot(bool)
    def on_visibility_changed(self, visible: bool) -> None:
        if visible:
            self.widget().resume()
        else:
            self.widget().pause()
