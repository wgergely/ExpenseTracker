import logging
import math
from typing import Optional

from PySide6 import QtWidgets, QtCore, QtGui

from ...data import data
from ...settings import lib, locale
from ...ui import ui


class PieChartView(QtWidgets.QWidget):
    """
    Widget to display expense distribution as a pie chart for a given date range.
    """

    def __init__(
            self,
            parent: QtWidgets.QWidget = None,
    ):
        super().__init__(parent)
        self._slices: dict = {}

        self._create_ui()
        self._connect_signals()
        self._init_actions()

        QtCore.QTimer.singleShot(100, self.init_data)

    def _create_ui(self) -> None:
        """
        Set up widget UI properties.
        """
        self.setMinimumSize(
            ui.Size.DefaultWidth(),
            ui.Size.DefaultHeight(),
        )
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding,
        )

    def _connect_signals(self) -> None:
        """
        Connect to global data-range change signal to refresh the chart.
        """
        from ...ui.actions import signals
        signals.configSectionChanged.connect(self.init_data)
        signals.dataRangeChanged.connect(self.init_data)

    def _init_actions(self) -> None:
        """
        Initialize widget actions if needed.
        """
        pass

    def init_data(self) -> None:
        """
        Build ``self._slices`` – one dict per category – each containing the
        geometry needed by :pymeth:`paintEvent`.

        * Qt expects angles in 1/16 degrees; a full circle is ``5760``.
        * The chart is rotated +90° so the first slice starts at 12 o’clock.
        * Any rounding residue is added to the largest slice so the pie closes.
        """
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
        rotation = 90 * 16  # 12 o’clock

        # raw spans
        spans: list[tuple[int, int, float]] = []  # (idx, span, abs_amount)
        for idx, row in df.iterrows():
            span = int(round(abs(row['total']) / total_abs * qt_circle))
            spans.append((idx, span, abs(row['total'])))

        # close the pie by fixing rounding error
        used = sum(span for _, span, _ in spans)
        leftover = qt_circle - used
        if leftover:
            largest_idx = max(spans, key=lambda s: s[2])[0]
            for pos, (idx, span, amt) in enumerate(spans):
                if idx == largest_idx:
                    spans[pos] = (idx, span + leftover, amt)
                    break
            logging.debug('PieChartView: distributed %s units rounding residue', leftover)

        self._slices.clear()
        angle_cursor = 0
        config = lib.settings.get_section('categories')

        for idx, span, _ in spans:
            row = df.loc[idx]
            category = row['category']
            color_str = config.get(category, {}).get('color', ui.Color.Text().name(QtGui.QColor.HexRgb))
            color = QtGui.QColor(color_str) if QtGui.QColor(color_str).isValid() else ui.Color.Text()

            self._slices[idx] = {
                'category': category,
                'amount': locale.format_currency_value(abs(row['total']), lib.settings['locale']),
                'start_angle': (angle_cursor + rotation) % qt_circle,
                'span_angle': span,
                'color': color,
                'description': config.get(category, {}).get('description', ''),
            }
            angle_cursor += span

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """
        Render an exploded pie chart.

        Each slice is moved outwards along its bisector by a distance *t*:

            t_raw = gap_px / (2 · sin(α / 2))

        where *α* is the slice's span in radians and ``gap_px`` is a small visual
        clearance (here the same as ``min_offset_px``).  The raw value is then
        clamped to the range ``[min_offset_px, max_offset_px_clipped]`` so that

        * narrow slices do not overshoot, and
        * the whole chart remains fully visible.
        """
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # ------------------------------------------------------------------ #
        # Background
        # ------------------------------------------------------------------ #
        painter.fillRect(self.rect(), ui.Color.VeryDarkBackground())

        widget_rect = self.rect()
        edge = min(widget_rect.width(), widget_rect.height())

        square_rect = QtCore.QRect(
            widget_rect.x() + (widget_rect.width() - edge) // 2,
            widget_rect.y() + (widget_rect.height() - edge) // 2,
            edge,
            edge,
        )

        margin = ui.Size.Margin(1.0)
        square_rect = square_rect.adjusted(margin, margin, -margin, -margin)

        painter.setBrush(QtGui.QBrush(ui.Color.DarkBackground()))
        painter.setPen(QtCore.Qt.NoPen)
        radius_indicator = ui.Size.Indicator(3.0)
        painter.drawRoundedRect(square_rect, radius_indicator, radius_indicator)

        # ------------------------------------------------------------------ #
        # Translation parameters
        # ------------------------------------------------------------------ #
        min_offset_px = ui.Size.Indicator(1.0)  # always at least this much
        max_offset_px = ui.Size.Indicator(12.0)  # never more than this

        pie_radius = (square_rect.width() - 2 * margin) / 2.0
        max_offset_px_clipped = min(max_offset_px, pie_radius * 0.30)  # ≤ 30 % R

        # base rectangle shrunk so even the most displaced slice stays inside
        pie_rect = square_rect.adjusted(
            int(margin + max_offset_px_clipped),
            int(margin + max_offset_px_clipped),
            -int(margin + max_offset_px_clipped),
            -int(margin + max_offset_px_clipped),
        )

        # ------------------------------------------------------------------ #
        # Draw each slice
        # ------------------------------------------------------------------ #
        gap_px = min_offset_px  # use the base displacement as the visual gap

        for idx, sl in self._slices.items():
            start_qt = sl['start_angle']  # 1/16 °
            span_qt = sl['span_angle']  # 1/16 °
            color = sl['color']

            # --- translation magnitude -------------------------------------
            alpha_rad = math.radians(span_qt / 16.0)  # full span in rad
            half_alpha = alpha_rad / 2.0
            if half_alpha <= 0:
                t_raw = 0.0
            else:
                t_raw = gap_px / (2.0 * math.sin(half_alpha))

            t = max(min_offset_px, min(t_raw, max_offset_px_clipped))

            # --- angle & displacement vector -------------------------------
            mid_deg = (start_qt + span_qt / 2) / 16.0
            theta = math.radians(mid_deg)

            dx = int(round(t * math.cos(theta)))
            dy = int(round(-t * math.sin(theta)))  # invert Y axis

            # --- draw -------------------------------------------------------
            slice_rect = QtCore.QRect(pie_rect)
            slice_rect.translate(dx, dy)

            painter.setBrush(QtGui.QBrush(color))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawPie(slice_rect, start_qt, span_qt)

            logging.debug(
                'slice %s: span=%5.2f°  t_raw=%6.2f  t=%5.2f  dx=%3d  dy=%3d',
                idx, span_qt / 16.0, t_raw, t, dx, dy,
            )


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
