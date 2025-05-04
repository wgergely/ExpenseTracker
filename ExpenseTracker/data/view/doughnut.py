"""Doughnut chart view for visualizing category expense distribution."""
import math
from typing import List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ...ui import ui
from ...ui.basechart import BaseChartView
from ...ui.dockable_widget import DockableWidget
from ...ui.ui import CategoryIconEngine, get_icon


class DoughnutView(BaseChartView):
    """Interactive doughnut chart."""
    hoverChanged = QtCore.Signal(int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        # doughnut defaults: legend and icons off
        self._show_legend = False
        self._show_icons = False
        self._show_tooltip = True
        # hole size ratio (inner radius / outer radius)
        self.hole_ratio = 2.0 / 3.0
        # ensure geometry attributes exist before first paint
        self._outer_rect = QtCore.QRect()
        self._inner_rect = QtCore.QRect()
        # synchronize context-menu toggle actions to defaults
        for act in self.actions():
            txt = act.text()
            if txt == 'Toggle Legend':
                act.setChecked(self._show_legend)
            elif txt == 'Toggle Icons':
                act.setChecked(self._show_icons)
            elif txt == 'Toggle Tooltip':
                act.setChecked(self._show_tooltip)

    def _recalc_geometry(self) -> None:
        sig = (self.model.version, self.width(), self.height())
        if sig == self._geom_sig:
            return

        if not self.model.slices:
            self._geom_sig = sig
            return

        # first inset by background margin
        margin = ui.Size.Margin(1.0)
        bg_inner = self.rect().adjusted(margin, margin, -margin, -margin)
        # then inset by same margin for chart padding
        chart_inner = bg_inner.adjusted(margin, margin, -margin, -margin)
        edge = min(chart_inner.width(), chart_inner.height())
        outer = QtCore.QRect(
            chart_inner.x() + (chart_inner.width() - edge) // 2,
            chart_inner.y() + (chart_inner.height() - edge) // 2,
            edge, edge
        )

        radius = outer.width() / 2.0
        inner_r = radius * self.hole_ratio
        thickness = radius - inner_r

        inner = outer.adjusted(
            int(thickness), int(thickness),
            -int(thickness), -int(thickness)
        )

        self._outer_rect = outer
        self._inner_rect = inner

        for sl in self.model.slices:
            start_deg = sl.start_qt / 16.0
            span_deg = sl.span_qt / 16.0
            sl.mid_deg = start_deg + span_deg / 2.0

        self._geom_sig = sig

    def _slice_at(self, pos: QtCore.QPoint) -> int:
        for index, sl in enumerate(self.model.slices):
            ptf = QtCore.QPointF(pos)
            center = self._outer_rect.center()
            dx = ptf.x() - center.x()
            dy = center.y() - ptf.y()
            dist = math.hypot(dx, dy)
            inner_r = self._inner_rect.width() / 2.0
            outer_r = self._outer_rect.width() / 2.0
            if dist < inner_r or dist > outer_r:
                continue

            angle = math.degrees(math.atan2(dy, dx)) % 360.0
            start = (sl.start_qt / 16.0) % 360.0
            span = sl.span_qt / 16.0
            end = (start + span) % 360.0

            if span == 0:
                continue

            if start < end:
                if start <= angle <= end:
                    return index
            else:
                if angle >= start or angle <= end:
                    return index

        return -1

    def _draw_background(self, painter: QtGui.QPainter) -> None:
        if self.property('rounded'):
            painter.setBrush(ui.Color.VeryDarkBackground())
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(
                self.rect(),
                ui.Size.Indicator(2.0),
                ui.Size.Indicator(2.0)
            )
        else:
            painter.fillRect(self.rect(), ui.Color.VeryDarkBackground())

        offset = ui.Size.Margin(1.0)
        inner = self.rect().adjusted(offset, offset, -offset, -offset)

        painter.setBrush(ui.Color.DarkBackground())
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(
            inner,
            ui.Size.Indicator(2.0),
            ui.Size.Indicator(2.0)
        )

    def _draw_slices(self, painter: QtGui.QPainter) -> None:
        if not self.model.slices:
            return
        for idx, sl in enumerate(self.model.slices):
            painter.setBrush(sl.color)
            if sl.category == self._selected_category:
                pen = QtGui.QPen(sl.color.lighter(125))
                pen.setWidthF(ui.Size.Separator(3.0))
                painter.setPen(pen)
            else:
                painter.setPen(QtCore.Qt.NoPen)

            painter.drawPie(self._outer_rect, sl.start_qt, sl.span_qt)

        painter.setBrush(ui.Color.DarkBackground())
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(self._inner_rect)

    def _draw_legend(self, painter: QtGui.QPainter) -> None:
        pad = ui.Size.Indicator(1.0)
        radial_step = ui.Size.Separator(0.8)
        font, metrics = ui.Font.BoldFont(ui.Size.MediumText())
        painter.setFont(font)

        # place legend labels sorted by slice angle
        slices_sorted = sorted(self.model.slices, key=lambda sl: sl.mid_deg)
        placed_boxes: List[QtCore.QRectF] = []
        # constrain legend within inner background rectangle
        offset = ui.Size.Margin(1.0)
        bg_rect = self.rect().adjusted(offset, offset, -offset, -offset)
        legend_bound = bg_rect.adjusted(pad, pad, -pad, -pad)
        # compute placement boxes
        for sl in slices_sorted:
            centre = self._outer_rect.center()
            base_r = self._outer_rect.width() / 2.0 + pad * 2
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
                    txt_h + pad * 2
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
        size = ui.Size.Margin(2.0)
        radius_outer = self._outer_rect.width() / 2.0
        radius_inner = self._inner_rect.width() / 2.0
        ring_mid = (radius_outer + radius_inner) / 2.0

        for sl in self.model.slices:
            if sl.span_qt / 16.0 < 20.0:
                continue

            centre = self._outer_rect.center()
            theta = math.radians(sl.mid_deg)
            x = centre.x() + ring_mid * math.cos(theta) - size / 2
            y = centre.y() - ring_mid * math.sin(theta) - size / 2

            icon = get_icon(
                sl.icon_name,
                color=sl.color.darker(150),
                engine=CategoryIconEngine
            )
            icon.paint(
                painter,
                x, y,
                size, size,
                alignment=QtCore.Qt.AlignCenter
            )

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
        painter.setBrush(ui.Color.VeryDarkBackground())
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(bg, pad, pad)

        icon = get_icon(sl.icon_name, color=sl.color, engine=CategoryIconEngine)
        icon.paint(painter, bg.x() + pad, bg.y() + pad, icon_size, icon_size,
                   alignment=QtCore.Qt.AlignCenter)

        painter.setPen(ui.Color.Text())
        painter.drawText(
            QtCore.QPointF(bg.x() + pad + icon_size + pad, bg.y() + pad + metrics.ascent()),
            text
        )


class DoughnutDockWidget(DockableWidget):
    """Dock widget for displaying a doughnut chart."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            'Doughnut Chart',
            parent,
            min_width=ui.Size.DefaultWidth(0.5),
            min_height=ui.Size.DefaultWidth(0.5),
            max_width=ui.Size.DefaultWidth(1.0),
            max_height=ui.Size.DefaultWidth(1.0),
        )

        self.setObjectName('ExpenseTrackerDoughnutDockWidget')

        chart = DoughnutView(self)
        chart.setProperty('rounded', True)
        chart.setObjectName('ExpenseTrackerDoughnutView')
        self.setWidget(chart)

        self.setContentsMargins(0, 0, 0, 0)
