"""
Dockable widget base class for unified behavior and sizing.

This module defines:
    - DockableWidget: base class for QDockWidget with unified features, size constraints,
      and a custom toggled signal for visibility changes.
"""
from typing import Optional

from PySide6 import QtWidgets, QtCore, QtGui


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
        self.setAllowedAreas(QtCore.Qt.AllDockWidgetAreas)

        self._size_hint = size_hint

        if min_width is not None:
            self.setMinimumWidth(min_width)

        if min_height is not None:
            self.setMinimumHeight(min_height)

        if max_width is not None:
            self.setMaximumWidth(max_width)

        if max_height is not None:
            self.setMaximumHeight(max_height)

        self.visibilityChanged.connect(self.toggled.emit)
        self.topLevelChanged.connect(self.refresh_main_dock_options)
        # ensure active when shown
        self.visibilityChanged.connect(self._on_visibility_changed)

    def sizeHint(self) -> QtCore.QSize:
        if self._size_hint:
            return self._size_hint  # type: ignore[return-value]
        return super().sizeHint()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        """Override to ensure widget is visible and active when shown."""
        super().showEvent(event)
        # schedule after event loop to raise and focus
        QtCore.QTimer.singleShot(0, self._ensure_visible_and_active)

    def _on_visibility_changed(self, visible: bool) -> None:
        """Handle visibility toggled to true by user actions."""
        if visible:
            # ensure visible and active when toggled on
            QtCore.QTimer.singleShot(0, self._ensure_visible_and_active)

    def _ensure_visible_and_active(self) -> None:
        """Bring this dock widget to the front, activate its tab or window, and ensure on-screen."""
        # find main window if any
        app = QtWidgets.QApplication.instance()
        main_win = None
        if app:
            for w in app.topLevelWidgets():
                if isinstance(w, QtWidgets.QMainWindow):
                    main_win = w
                    break
        # if floating, ensure on-screen over main window
        if self.isFloating() and main_win:
            mw_geom = main_win.frameGeometry()
            fw_geom = self.frameGeometry()
            if not mw_geom.intersects(fw_geom):
                # center over main window
                x = mw_geom.center().x() - fw_geom.width() // 2
                y = mw_geom.center().y() - fw_geom.height() // 2
                self.move(x, y)
        # bring to front and activate
        try:
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

    def moveEvent(self, event: QtGui.QMoveEvent) -> None:
        """Override to refresh main window dock options when floating and moved."""
        super().moveEvent(event)
        if self.isFloating():
            self.refresh_main_dock_options(True)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        """Provide a context menu on the title bar for docking actions."""
        title_height = self.style().pixelMetric(QtWidgets.QStyle.PM_TitleBarHeight)

        if event.pos().y() <= title_height:
            menu = QtWidgets.QMenu(self)

            toggle = menu.addAction('Toggle Floating')

            # dock area options
            dock_actions = {}
            for name, area in (('Left', QtCore.Qt.LeftDockWidgetArea),
                               ('Right', QtCore.Qt.RightDockWidgetArea),
                               ('Top', QtCore.Qt.TopDockWidgetArea),
                               ('Bottom', QtCore.Qt.BottomDockWidgetArea)):
                act = menu.addAction(f'Dock {name}')
                dock_actions[act] = area
            chosen = menu.exec_(event.globalPos())
            if chosen == toggle:
                self.setFloating(not self.isFloating())
            elif chosen in dock_actions:
                area = dock_actions[chosen]
                # redock into parent main window
                parent = self.parent()
                while parent and not isinstance(parent, QtWidgets.QMainWindow):
                    parent = parent.parent()
                if parent:
                    parent.addDockWidget(area, self)
            event.accept()
        else:
            super().contextMenuEvent(event)

    def refresh_main_dock_options(self, floating: bool) -> None:
        """Workaround: reapply main window dock options on floating state change to refresh drop zones."""
        app = QtWidgets.QApplication.instance()
        if not app:
            return

        main_window = next((w for w in app.topLevelWidgets() if isinstance(w, QtWidgets.QMainWindow)), None)
        if not main_window:
            return

        opts = main_window.dockOptions()
        main_window.setDockOptions(opts)
