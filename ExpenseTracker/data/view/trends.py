"""
TrendGraph widget — now with a **single geometry cache** and no NumPy.

Layers
------
0. axes
1. monthly_total column bars
2. smoothed trend curve (ewma or loess)

External API  (all Qt slots)
----------------------------
set_category(str)     -> switch category
toggle_bars(bool)     -> show / hide bar layer
toggle_trend(bool)    -> show / hide trend layer
set_padding(float)    -> 0-to-1 gap ratio
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets

from ..data import DataWindow
from ...data.data import get_trends
from ...settings import lib
from ...ui import ui
from ...ui.actions import signals


def paintmethod(func):  # type: ignore[valid-type]
    """Decorator to wrap paint helpers with save/restore + exception log."""

    def wrapper(self, painter: QtGui.QPainter) -> None:  # type: ignore[valid-type]
        painter.save()
        try:
            func(self, painter)
        except Exception:
            logging.exception('TrendGraph: error in %s', func.__name__)
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
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent)

        # source data
        self._df_all: pd.DataFrame = pd.DataFrame()
        self._df_view: pd.DataFrame = pd.DataFrame()
        self._categories: List[str] = []
        self._current_category: Optional[str] = None

        # convenient slices for the active category
        self._dates: pd.Index = pd.Index([])
        self._bar_series: pd.Series = pd.Series(dtype=float)
        self._trend_series: pd.Series = pd.Series(dtype=float)

        # pixel geometry
        self._geom: Geometry = Geometry()

        # presentation flags
        self._padding: float = 0.05
        self._trend_key: str = 'loess'
        self._show_bars: bool = True
        self._show_trend: bool = True

        self.setMouseTracking(True)
        self._connect_signals()
        self._init_actions()

        QtCore.QTimer.singleShot(50, self.init_data)

    def _connect_signals(self) -> None:
        signals.categoryChanged.connect(self.set_category)
        signals.dataAboutToBeFetched.connect(self.clear_data)
        signals.dataFetched.connect(self.init_data)
        signals.presetActivated.connect(self.clear_data)
        signals.presetActivated.connect(self.init_data)

    def _init_actions(self) -> None:
        """Placeholder for future QAction or context-menu wiring."""
        pass

    @QtCore.Slot(str)
    def set_category(self, category: str) -> None:
        if not self._categories:
            logging.warning('TrendGraph: no data loaded yet')
            return
        if category not in self._categories:
            logging.warning('TrendGraph: %s not among %s', category, self._categories)
            return

        self._current_category = category
        self._df_view = self._df_all[self._df_all['category'] == category]

        self._dates = self._df_view['month']
        self._bar_series = self._df_view['monthly_total']
        self._trend_series = self._df_view[self._trend_key]

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

    @QtCore.Slot(float)
    def set_padding(self, ratio: float) -> None:
        self._padding = max(0.0, min(float(ratio), 1.0))
        self._rebuild_geometry()
        self.update()

    def sizeHint(self) -> QtCore.QSize:  # noqa: D401
        return QtCore.QSize(ui.Size.DefaultWidth(1.0), ui.Size.DefaultHeight(1.0))

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: D401
        self._rebuild_geometry()
        super().resizeEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: D401
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(QtGui.QPalette.Window))

        self._draw_axes(painter)
        if self._show_bars:
            self._draw_bars(painter)
        if self._show_trend:
            self._draw_trend(painter)
        self._draw_labels(painter)

    @paintmethod
    def _draw_axes(self, painter: QtGui.QPainter) -> None:
        geom = self._geom
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QtGui.QPen(self.palette().color(QtGui.QPalette.Text)))

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
        # Y-axis legend: show data_max at top, data_min at baseline
        metrics = painter.fontMetrics()
        offset = ui.Size.Separator(2.0)
        max_lbl = f"{geom.data_max:.2f}"
        painter.drawText(
            QtCore.QPointF(
                geom.area.left() - metrics.horizontalAdvance(max_lbl) - offset,
                geom.area.top() + metrics.ascent()
            ), max_lbl
        )
        min_lbl = f"{geom.data_min:.2f}"
        painter.drawText(
            QtCore.QPointF(
                geom.area.left() - metrics.horizontalAdvance(min_lbl) - offset,
                geom.baseline_y
            ), min_lbl
        )

    @paintmethod
    def _draw_bars(self, painter: QtGui.QPainter) -> None:
        geom = self._geom
        if not geom.bars:
            return
        cfg = lib.settings.get_section('categories') or {}
        color = QtGui.QColor(cfg.get(self._current_category, {}).get('color', '#000000'))
        color.setAlphaF(0.5)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(color)
        for rect in geom.bars:
            painter.drawRect(rect)

    @paintmethod
    def _draw_trend(self, painter: QtGui.QPainter) -> None:
        geom = self._geom
        if geom.trend_path.isEmpty():
            return
        cfg = lib.settings.get_section('categories') or {}
        color = QtGui.QColor(cfg.get(self._current_category, {}).get('color', '#000000'))
        pen = QtGui.QPen(color)
        pen.setCosmetic(True)
        pen.setWidthF(ui.Size.Separator(3.0))
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(geom.trend_path)

    @paintmethod
    def _draw_labels(self, painter: QtGui.QPainter) -> None:
        geom = self._geom
        if not geom.labels:
            return
        painter.setPen(self.palette().color(QtGui.QPalette.Text))
        for static_text, pos in geom.labels:
            painter.drawStaticText(pos, static_text)

    def _rebuild_geometry(self) -> None:
        """Populate self._geom from current data + widget size."""
        self._geom = Geometry()  # fresh slate
        geom = self._geom

        rect = self.contentsRect()
        m = ui.Size.Margin(1.0)
        geom.area = QtCore.QRectF(rect.adjusted(m, m, -m, -m))

        if self._bar_series.empty:
            return

        n = len(self._bar_series)
        x_step = geom.area.width() / n
        bar_w = x_step * (1.0 - self._padding)
        gap = x_step * self._padding

        data_min = min(0.0,
                       self._bar_series.min(skipna=True),
                       self._trend_series.min(skipna=True))
        data_max = max(0.0,
                       self._bar_series.max(skipna=True),
                       self._trend_series.max(skipna=True))
        # store for axis legend
        geom.data_min = data_min
        geom.data_max = data_max
        rng = data_max - data_min or 1.0
        geom.baseline_y = geom.area.bottom() - (-data_min / rng) * geom.area.height()

        # bars
        for i, val in enumerate(self._bar_series):
            x0 = geom.area.left() + i * x_step + gap / 2
            ratio = (val - data_min) / rng
            pix_h = ratio * geom.area.height()
            if val >= 0:
                y0, h = geom.baseline_y - pix_h, pix_h
            else:
                y0, h = geom.baseline_y, -pix_h
            geom.bars.append(QtCore.QRectF(x0, y0, bar_w, h))

        # trend
        for i, val in enumerate(self._trend_series):
            x = geom.area.left() + i * x_step + x_step / 2
            y_ratio = (val - data_min) / rng
            y = geom.area.bottom() - y_ratio * geom.area.height()
            pt = QtCore.QPointF(x, y)
            geom.trend_points.append(pt)
            geom.trend_path.moveTo(pt) if i == 0 else geom.trend_path.lineTo(pt)

        # labels
        for i, ts in enumerate(self._dates):
            x_c = geom.area.left() + i * x_step + x_step / 2
            txt = QtGui.QStaticText(pd.Timestamp(ts).strftime('%b %Y'))
            size = txt.size()
            pos = QtCore.QPointF(x_c - size.width() / 2,
                                 geom.baseline_y + size.height() + 5)
            geom.labels.append((txt, pos))

    @QtCore.Slot()
    def init_data(self) -> None:
        """Load trend table and show first category."""
        try:
            self._df_all = get_trends(data_window=DataWindow.W6).copy()
        except Exception as exc:
            logging.error('TrendGraph: failed to load trends: %s', exc)
            self.clear_data()
            return

        self._categories = sorted(self._df_all['category'].unique().tolist())
        if not self._categories:
            self.clear_data()
            return

        start = self._current_category if self._current_category in self._categories else self._categories[0]
        self.set_category(start)

    @QtCore.Slot()
    def clear_data(self) -> None:
        self._df_all = pd.DataFrame()
        self._df_view = pd.DataFrame()
        self._categories.clear()
        self._current_category = None

        self._dates = pd.Index([])
        self._bar_series = pd.Series(dtype=float)
        self._trend_series = pd.Series(dtype=float)

        self._geom = Geometry()
        self.update()

    def export_paths(self) -> Dict[str, List]:
        """Return geom lists for headless unit tests."""
        return {'bars': list(self._geom.bars), 'trend_points': list(self._geom.trend_points)}
