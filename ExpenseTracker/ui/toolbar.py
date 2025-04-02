#!/usr/bin/env python3
"""
Toolbar Module.

Implements a custom action toolbar using QToolBar and QToolButtons.
The toolbar consists of the following items:

    RangeSelectorBar | Switch View | Authenticate, Reload | Show Ledger

RangeSelectorBar is imported from the yearmonth module.
Other actions are defined in the actions module.

Actions:
    - Switch View toggles between graph and pie-chart views.
    - Authenticate attempts Google authentication.
      Force mode is triggered when shift, alt, or control are pressed.
    - Reload fetches data from Google and caches it locally.
      Force mode is supported.
    - Show Ledger opens the Google spreadsheet in the default browser.
"""

from PySide6 import QtWidgets, QtCore

from . import actions, ui
from .yearmonth import RangeSelectorBar


class ActionToolBar(QtWidgets.QToolBar):
    """
    Custom action toolbar using QToolBar.

    Contains:
      - RangeSelectorBar
      - Switch View button
      - Authenticate and Reload buttons
      - Show Ledger button
    """

    def __init__(self, parent=None):
        """
        Initialize the ActionToolBar.

        Args:
            parent (QWidget, optional): Parent widget.
        """
        super().__init__(parent=parent)
        self.setMovable(False)
        self.setFloatable(False)

        self.setObjectName('ExpenseTrackerActionToolBar')

        # Make buttons icon only
        self.setIconSize(QtCore.QSize(
            ui.Size.Margin(1.0),
            ui.Size.Margin(1.0)
        ))
        self.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Maximum,
            QtWidgets.QSizePolicy.MinimumExpanding
        )

        ui.set_stylesheet(self)

        self._create_actions()
        self._populate_toolbar()

    def _create_actions(self):
        self.range_selector = RangeSelectorBar(self)
        self.switch_view_btn = actions.SwitchViewAction(self)
        self.authenticate_btn = actions.AuthenticateAction(self)
        self.reload_btn = actions.ReloadAction(self)
        self.show_ledger_btn = actions.ShowLedgerAction(self)

    def _populate_toolbar(self):
        self.addWidget(self.range_selector)

        spacer = QtWidgets.QWidget(self)
        spacer.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        spacer.setAttribute(QtCore.Qt.WA_OpaquePaintEvent)
        spacer.setAttribute(QtCore.Qt.WA_NoSystemBackground)

        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.addWidget(spacer)

        self.addWidget(self.switch_view_btn)
        self.addSeparator()
        self.addWidget(self.authenticate_btn)
        self.addWidget(self.reload_btn)
        self.addSeparator()
        self.addWidget(self.show_ledger_btn)
