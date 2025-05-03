"""
Dockable widget base class for unified behavior and sizing.

This module defines:
    - DockableWidget: base class for QDockWidget with unified features, size constraints,
      and a custom toggled signal for visibility changes.
"""
from typing import Optional

from PySide6 import QtWidgets, QtCore


class DockableWidget(QtWidgets.QDockWidget):
    """Base class for dockable widgets providing unified feature setup, sizing,
    and a custom toggled signal for visibility changes."""
    toggled = QtCore.Signal(bool)

    def __init__(
            self,
            title: str,
            parent: Optional[QtWidgets.QWidget] = None,
            movable: bool = True,
            floatable: bool = True,
            closable: bool = True,
            min_width: Optional[int] = None,
            min_height: Optional[int] = None,
            max_width: Optional[int] = None,
            max_height: Optional[int] = None,
            size_hint: Optional[QtCore.QSize] = None,
    ) -> None:
        super().__init__(title, parent=parent)

        features = QtWidgets.QDockWidget.NoDockWidgetFeatures

        if movable:
            features |= QtWidgets.QDockWidget.DockWidgetMovable
        if floatable:
            features |= QtWidgets.QDockWidget.DockWidgetFloatable
        if closable:
            features |= QtWidgets.QDockWidget.DockWidgetClosable

        self.setFeatures(features)

        self._size_hint = size_hint
        # Apply size constraints
        if min_width is not None:
            self.setMinimumWidth(min_width)

        if min_height is not None:
            self.setMinimumHeight(min_height)

        if max_width is not None:
            self.setMaximumWidth(max_width)

        if max_height is not None:
            self.setMaximumHeight(max_height)

        self.visibilityChanged.connect(self.toggled.emit)

    def sizeHint(self) -> QtCore.QSize:
        if self._size_hint:
            return self._size_hint  # type: ignore[return-value]
        return super().sizeHint()
