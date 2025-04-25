"""
TrendGraph widget for visualizing monthly spend trends per category.

This widget displays a bar chart of monthly_total spend and overlays a trend
curve (LOESS or EWMA) for a selected category. Designed for future docking
in the main UI panel. Currently supports category switching, padding control,
and toggling of bars and trend line visibility.
"""
import logging
import typing

import numpy as np
import pandas as pd
from PySide6 import QtWidgets, QtGui, QtCore

from ...data.data import get_trends
from ...ui import ui
from ...ui.actions import signals


class TrendGraph(QtWidgets.QWidget):
    """Custom widget to plot monthly spend bars with trend overlay."""

    def __init__(
            self,
            df_trends: pd.DataFrame,
            parent: typing.Optional[QtWidgets.QWidget] = None,
            initial_category: typing.Optional[str] = None,
    ):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent)
        # Connect to global signals to refresh on data/preset changes
        signals.categoryChanged.connect(self.set_category)
        signals.dataFetchRequested.connect(self._refresh_data)
        signals.dataAboutToBeFetched.connect(self._refresh_data)
        signals.presetActivated.connect(self._refresh_data)
        signals.dataFetched.connect(self._on_data_fetched)
        self._df_all = df_trends.copy()
        self._categories = self._df_all['category'].unique().tolist()
        self._trend_key = 'loess'
        self._show_bars = True
        self._show_trend = True
        self._padding = 0.2
        self._bar_rects: typing.List[QtCore.QRectF] = []
        self._trend_path = QtGui.QPainterPath()
        self._trend_points: typing.List[QtCore.QPointF] = []
        self._month_texts: typing.List[typing.Tuple[QtGui.QStaticText, QtCore.QPointF]] = []
        if initial_category in self._categories:
            self._current_category = initial_category
        elif self._categories:
            self._current_category = self._categories[0]
        else:
            self._current_category = None
        if self._current_category:
            self.set_category(self._current_category)
        else:
            self._df_view = pd.DataFrame()
        self.setMouseTracking(True)

    @QtCore.Slot(str)
    def set_category(self, category: str) -> None:
        """Switch the active category to plot."""
        if category not in self._categories:
            logging.warning(f'Category \'{category}\' not in trend data')
            return
        self._current_category = category
        self._df_view = self._df_all[self._df_all['category'] == category]
        self._dates = self._df_view['month'].tolist()
        self._bar_values = self._df_view['monthly_total'].to_numpy()
        self._trend_values = self._df_view[self._trend_key].to_numpy()
        self._rebuild_geometry()
        self.update()

    @QtCore.Slot(bool)
    def toggle_bars(self, visible: bool) -> None:
        """Show or hide the bar layer."""
        self._show_bars = visible
        self.update()

    @QtCore.Slot(bool)
    def toggle_trend(self, visible: bool) -> None:
        """Show or hide the trend curve."""
        self._show_trend = visible
        self.update()

    @QtCore.Slot(float)
    def set_padding(self, ratio: float) -> None:
        """Set the gap padding ratio between bars."""
        self._padding = max(0.0, min(ratio, 1.0))
        self._rebuild_geometry()
        self.update()

    @property
    def padding_ratio(self) -> float:
        """Current padding ratio between bars (0..1)."""
        return self._padding

    @padding_ratio.setter
    def padding_ratio(self, ratio: float) -> None:
        self.set_padding(ratio)

    def sizeHint(self) -> QtCore.QSize:
        """Suggested size for the widget."""
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.0)
        )

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        self._rebuild_geometry()
        super().resizeEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Render axes, bars, trend line, and labels in the category color."""
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(QtGui.QPalette.Window))
        # Draw axes (no AA)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        text_color = self.palette().color(QtGui.QPalette.Text)
        pen_axis = QtGui.QPen(text_color)
        painter.setPen(pen_axis)
        area = getattr(self, '_area', QtCore.QRectF(self.rect()))
        baseline = getattr(self, '_baseline_y', area.bottom())
        painter.drawLine(area.left(), area.top(), area.left(), area.bottom())
        painter.drawLine(area.left(), baseline, area.right(), baseline)
        # Tick marks
        tick_len = ui.Size.Separator(1.0)
        for st, pos in self._month_texts:
            w = st.size().width()
            x_center = pos.x() + w / 2
            painter.drawLine(x_center, baseline, x_center, baseline + tick_len)
        # Category color
        cfg = lib.settings.get_section('categories') or {}
        cat_cfg = cfg.get(self._current_category, {})
        hex_color = cat_cfg.get('color', '#000000')
        base_color = QtGui.QColor(hex_color)
        # Draw bars at 50% opacity
        if self._show_bars:
            bar_color = QtGui.QColor(base_color)
            bar_color.setAlphaF(0.5)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(bar_color)
            for rect in self._bar_rects:
                painter.drawRect(rect)
        # Draw smooth trend curve
        if self._show_trend:
            painter.save()
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            trend_color = QtGui.QColor(base_color)
            pen_trend = QtGui.QPen(trend_color)
            pen_trend.setCosmetic(True)
            pen_trend.setWidthF(ui.Size.Separator(3.0))
            painter.setPen(pen_trend)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawPath(self._trend_path)
            painter.restore()
        # Draw month labels
        painter.setPen(text_color)
        for st, pos in self._month_texts:
            painter.drawStaticText(pos, st)

    def _rebuild_geometry(self) -> None:
        """Compute bar rectangles, trend path, and label positions."""
        rect = self.contentsRect()
        margin = ui.Size.Margin(1.0)
        area = QtCore.QRectF(rect.adjusted(margin, margin, -margin, -margin))
        self._area = area
        width = area.width()
        height = area.height()
        if not hasattr(self, '_bar_values') or len(self._bar_values) == 0:
            self._bar_rects = []
            self._trend_path = QtGui.QPainterPath()
            self._trend_points = []
            self._month_texts = []
            self._baseline_y = area.bottom()
            return
        n = len(self._bar_values)
        x_step = width / n
        bar_width = x_step * (1 - self._padding)
        gap = x_step * self._padding
        data_min = min(0.0, float(np.nanmin(self._bar_values)), float(np.nanmin(self._trend_values)))
        data_max = max(0.0, float(np.nanmax(self._bar_values)), float(np.nanmax(self._trend_values)))
        data_range = data_max - data_min or 1.0
        baseline_ratio = (0 - data_min) / data_range
        baseline_y = area.bottom() - baseline_ratio * height
        self._baseline_y = baseline_y
        bars: typing.List[QtCore.QRectF] = []
        for i, v in enumerate(self._bar_values):
            x0 = area.left() + i * x_step + gap / 2
            ratio = (v - data_min) / data_range
            bar_h = ratio * height
            if v >= 0:
                y0 = baseline_y - bar_h
                h = bar_h
            else:
                y0 = baseline_y
                h = -bar_h
            bars.append(QtCore.QRectF(x0, y0, bar_width, h))
        self._bar_rects = bars
        path = QtGui.QPainterPath()
        pts: typing.List[QtCore.QPointF] = []
        for i, v in enumerate(self._trend_values):
            x = area.left() + i * x_step + x_step / 2
            ratio = (v - data_min) / data_range
            y = area.bottom() - ratio * height
            pt = QtCore.QPointF(x, y)
            pts.append(pt)
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        self._trend_path = path
        self._trend_points = pts
        labels: typing.List[typing.Tuple[QtGui.QStaticText, QtCore.QPointF]] = []
        for i, ts in enumerate(self._dates):
            x_c = area.left() + i * x_step + x_step / 2
            st = QtGui.QStaticText(pd.to_datetime(ts).strftime('%b %Y'))
            size = st.size()
            x_l = x_c - size.width() / 2
            y_l = baseline_y + size.height() + 5
            labels.append((st, QtCore.QPointF(x_l, y_l)))
        self._month_texts = labels

    @QtCore.Slot()
    def _refresh_data(self) -> None:
        """Reload trends data and update the view."""
        try:
            df = get_trends()
        except Exception as e:
            logging.error(f"Error refreshing trend data: {e}")
            return
        self._df_all = df.copy()
        self._categories = df['category'].unique().tolist()
        # Determine category to display
        if self._current_category in self._categories:
            category = self._current_category
        else:
            category = self._categories[0] if self._categories else None
        if category:
            self.set_category(category)
        else:
            # Clear view
            self._df_view = pd.DataFrame()
            self._bar_rects = []
            self._trend_path = QtGui.QPainterPath()
            self._trend_points = []
            self._month_texts = []
            self._baseline_y = getattr(self, '_area', QtCore.QRectF(self.rect())).bottom()
            self.update()

    @QtCore.Slot(pd.DataFrame)
    def _on_data_fetched(self, df: pd.DataFrame) -> None:
        """Handle incoming raw data fetch by refreshing trends."""
        self._refresh_data()

    def export_paths(self) -> typing.Dict[str, typing.List]:
        """Return geometry data for testing: bar_rects and trend_points."""
        return {
            'bar_rects': list(self._bar_rects),
            'trend_points': list(self._trend_points),
        }
