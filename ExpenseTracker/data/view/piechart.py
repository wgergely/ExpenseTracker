"""Pie chart view for visualizing category expense distribution."""
import math
from typing import Optional, List

from PySide6 import QtCore, QtGui, QtWidgets

from ...ui import ui
from ...ui.basechart import BaseChartView
from ...ui.dockable_widget import DockableWidget
from ...ui.ui import CategoryIconEngine, get_icon


class PieChartView(BaseChartView):
    """Interactive exploded-view pie chart."""

    hoverChanged = QtCore.Signal(int)  # emits -1 when nothing is hovered

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        # pie-specific settings: enable legend and icons by default
        self._show_legend = True
        self._show_icons = True
        self._show_tooltip = True
        # explosion offsets
        self.min_offset_px = ui.Size.Indicator(1.0)
        self.max_offset_px = ui.Size.Indicator(10.0)
        self.gap_px = self.min_offset_px

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
            # highlight selected slice with a border
            if sl.category == self._selected_category:
                pen = QtGui.QPen(sl.color.lighter(125))
                pen.setWidthF(ui.Size.Separator(3.0))
                painter.setPen(pen)
            else:
                painter.setPen(QtCore.Qt.NoPen)
            painter.drawPie(rect, sl.start_qt, sl.span_qt)

    def _draw_legend(self, painter: QtGui.QPainter) -> None:
        if not self.model.slices:
            return

        pad = ui.Size.Indicator(1.0)
        radial_step = ui.Size.Separator(0.8)
        font, metrics = ui.Font.BoldFont(ui.Size.MediumText())
        painter.setFont(font)

        # prepare legend label placement
        slices_sorted = sorted(self.model.slices, key=lambda sl: sl.mid_deg)
        placed_boxes: List[QtCore.QRectF] = []
        # constrain legend within inner background rectangle
        offset = ui.Size.Margin(1.0)
        bg_rect = self.rect().adjusted(offset, offset, -offset, -offset)
        legend_bound = bg_rect.adjusted(pad, pad, -pad, -pad)
        # compute placement boxes
        for sl in slices_sorted:
            idx = self.model.slices.index(sl)
            rect_ref = sl.half_rect if idx == self._hover_index else sl.base_rect
            centre = rect_ref.center()
            base_r = rect_ref.width() / 2.0 + pad * 2
            theta = math.radians(sl.mid_deg)
            text = sl.amount_txt
            txt_w = metrics.horizontalAdvance(text)
            txt_h = metrics.height()
            # limit iterations to avoid infinite loop
            current_r = base_r
            max_radius = math.hypot(legend_bound.width(), legend_bound.height())
            max_iters = int(max_radius / radial_step) + 1
            box = QtCore.QRectF()
            for _ in range(max_iters):
                cx = centre.x() + current_r * math.cos(theta)
                cy = centre.y() - current_r * math.sin(theta)
                box = QtCore.QRectF(
                    cx - txt_w / 2 - pad,
                    cy - txt_h / 2 - pad,
                    txt_w + pad * 2,
                    txt_h + pad * 2,
                )
                if all(not box.intersects(other) for other in placed_boxes) and \
                        box.left() >= legend_bound.left() and box.right() <= legend_bound.right() and \
                        box.top() >= legend_bound.top() and box.bottom() <= legend_bound.bottom():
                    break
                current_r += radial_step
            placed_boxes.append(box)
        # draw legend boxes and labels in sorted order
        for sl, box in zip(slices_sorted, placed_boxes):
            painter.save()
            painter.setOpacity(0.5)
            painter.setBrush(ui.Color.VeryDarkBackground())
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(box, pad, pad)
            painter.restore()
            painter.setPen(ui.Color.Text())
            painter.drawText(
                QtCore.QPointF(box.x() + pad, box.y() + pad + metrics.ascent()), sl.amount_txt)

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
            icon.paint(painter, x, y, size, size, alignment=QtCore.Qt.AlignCenter)

    def _draw_tooltip(self, painter: QtGui.QPainter) -> None:
        if self._hover_index < 0:
            return

        sl = self.model.slices[self._hover_index]
        cursor_pos = self.mapFromGlobal(QtGui.QCursor.pos())

        # Determine display name or fallback to raw category key
        name = sl.display_name if sl.display_name else sl.category
        text = f'{name}: {sl.amount_txt}'
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
        painter.setBrush(ui.Color.VeryDarkBackground())
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(bg, pad, pad)

        icon = get_icon(sl.icon_name, color=sl.color, engine=CategoryIconEngine)
        icon.paint(painter, bg.x() + pad, bg.y() + pad, icon_size, icon_size, alignment=QtCore.Qt.AlignCenter)

        painter.setPen(ui.Color.Text())
        painter.drawText(
            QtCore.QPointF(bg.x() + pad + icon_size + pad, bg.y() + pad + metrics.ascent()),
            text,
        )


class PieChartDockWidget(DockableWidget):
    """Dock widget for displaying a pie chart of expenses."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            'Pie Chart',
            parent,
            min_width=ui.Size.DefaultWidth(0.5),
            min_height=ui.Size.DefaultWidth(0.5),
            max_width=ui.Size.DefaultWidth(1.0),
            max_height=ui.Size.DefaultWidth(1.0),
        )

        self.setObjectName('ExpenseTrackerPieChartDockWidget')

        chart = PieChartView(self)
        chart.setProperty('rounded', True)
        chart.setObjectName('ExpenseTrackerPieChartView')
        self.setWidget(chart)

        self.setContentsMargins(0, 0, 0, 0)
