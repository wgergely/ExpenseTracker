"""Custom Qt view classes with enhanced scrolling behavior for settings UI.

Provides:
    - VerticalScrollMixin: intercept wheel events at scroll limits
    - TableView, TreeView, ListView: integrate mixin with Qt views
"""
from PySide6 import QtWidgets, QtGui

from ...ui import ui


class VerticalScrollMixin:
    """Mixin that intercepts vertical wheel events to avoid scrolling parent when at boundaries."""

    def __init__(self, *args, **kwargs):
        self._accumulated_delta = 0
        super().__init__(*args, **kwargs)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if not hasattr(self, 'verticalScrollBar') or not hasattr(self, 'horizontalScrollBar'):
            super().wheelEvent(event)
            return

        # Check if event is vertical or horizontal
        is_vertical = event.angleDelta().y() != 0
        if not is_vertical:
            super().wheelEvent(event)
            return

        scrollbar = self.verticalScrollBar()
        delta = event.angleDelta().y()
        self._accumulated_delta += delta

        threshold = 15  # Adjust sensitivity as needed.
        if ((self._accumulated_delta > threshold and scrollbar.value() == scrollbar.minimum()) or
                (self._accumulated_delta < -threshold and scrollbar.value() == scrollbar.maximum())):
            self._accumulated_delta = 0
            event.ignore()
        else:
            event.accept()
            self._accumulated_delta = 0
            super().wheelEvent(event)


class TableView(VerticalScrollMixin, QtWidgets.QTableView):
    """QTableView subclass that integrates vertical scroll mixin."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)

        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        self.setShowGrid(False)

        self.setItemDelegate(ui.RoundedRowDelegate(parent=self))
        self.setProperty('noitembackground', True)


class TreeView(VerticalScrollMixin, QtWidgets.QTreeView):
    """QTreeView subclass that integrates vertical scroll mixin."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class ListView(VerticalScrollMixin, QtWidgets.QListView):
    """QListView subclass that integrates vertical scroll mixin."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
