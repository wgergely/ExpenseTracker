from PySide6 import QtWidgets, QtGui


class VerticalScrollMixin:
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


class TreeView(VerticalScrollMixin, QtWidgets.QTreeView):
    """QTreeView subclass that integrates vertical scroll mixin."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class ListView(VerticalScrollMixin, QtWidgets.QListView):
    """QListView subclass that integrates vertical scroll mixin."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
