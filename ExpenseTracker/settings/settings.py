"""Settings UI and dock widget for configuring application preferences.

Provides:
    - SettingsScrollArea: scroll area ensuring horizontal expansion without scrollbars.
    - SettingsWidget: composite editor for all configuration sections (metadata, spreadsheet, etc.).
    - SettingsDockWidget: dockable container wrapping the settings UI.
"""
from typing import Optional

from PySide6 import QtWidgets, QtCore

from .editors import category_editor
from .editors import client_editor
from .editors import data_mapping_editor
from .editors import header_editor
from .editors import metadata_editor
from .editors import spreadsheet_editor
from ..ui import ui
from ..ui.dockable_widget import DockableWidget


class SettingsScrollArea(QtWidgets.QScrollArea):
    """
    Custom QScrollArea ensuring the contained widget expands horizontally
    to fill available width, without horizontal scrolling.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)

        # Only vertical scroll. Hide the horizontal scroll.
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setFocusPolicy(QtCore.Qt.NoFocus)


class SettingsWidget(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName('SettingsWidget')
        self.setWindowTitle('Settings')

        self._sections = []

        self.client_editor = None
        self.spreadsheet_editor = None
        self.header_editor = None
        self.data_mapping_editor = None
        self.category_editor = None
        self.metadata_editor = None

        self.setMinimumWidth(ui.Size.DefaultWidth(1.0))

        self._create_ui()
        self._connect_signals()

    def _add_section(self, title: str, label: str, parent: QtWidgets.QWidget, editor):
        title_widget = QtWidgets.QLabel(title)
        title_widget.setProperty('h1', True)

        parent.layout().addSpacing(ui.Size.Margin(1.0))
        parent.layout().addWidget(title_widget, 0)

        group = QtWidgets.QGroupBox('')
        QtWidgets.QFormLayout(group)

        o = ui.Size.Margin(0.5)
        group.layout().setContentsMargins(o, o, o, o)
        group.layout().setSpacing(o)
        group.layout().setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        group.layout().setRowWrapPolicy(QtWidgets.QFormLayout.WrapAllRows)
        group.layout().setHorizontalSpacing(o)
        group.layout().setVerticalSpacing(o)
        group.layout().addRow(label, editor)

        parent.layout().addWidget(group, 0)

        self._sections.append([title, group])

        return group

    def _create_ui(self):
        QtWidgets.QVBoxLayout(self)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)
        self.layout().setAlignment(QtCore.Qt.AlignTop)

        scroll_area = SettingsScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumWidth(ui.Size.DefaultWidth(1.0))
        self.layout().addWidget(scroll_area)

        parent = QtWidgets.QWidget()
        parent.setMinimumWidth(ui.Size.DefaultWidth(1.0))
        QtWidgets.QVBoxLayout(parent)

        parent.setContentsMargins(0, 0, 0, 0)

        scroll_area.setFocusProxy(parent)
        scroll_area.setWidget(parent)

        parent.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Maximum
        )

        o = ui.Size.Margin(0.5)
        parent.layout().setContentsMargins(o, o, o, o)
        parent.layout().setSpacing(o)

        self.metadata_editor = metadata_editor.MetadataWidget(self)
        self._add_section(
            'General Settings',
            'Settings for locale, theme, and summary mode.',
            parent,
            self.metadata_editor
        )

        self.client_editor = client_editor.ClientEditor(self)
        self._add_section(
            'Google Authentication',
            '',
            parent,
            self.client_editor
        )

        self.spreadsheet_editor = spreadsheet_editor.SpreadsheetEditor(self)
        self._add_section(
            'Google Spreadsheet',
            'The remote spreadsheet\'s ID and source sheet name.',
            parent,
            self.spreadsheet_editor
        )

        self.header_editor = header_editor.HeaderEditor(self)
        self._add_section(
            'Source Columns',
            'Define the columns of the source spreadsheet.',
            parent,
            self.header_editor
        )

        self.data_mapping_editor = data_mapping_editor.DataMappingEditor(self)
        self._add_section(
            'Column Roles',
            'Define which source column should be used for which role.',
            parent,
            self.data_mapping_editor
        )

        self.category_editor = category_editor.CategoryEditor(self)
        self._add_section(
            'Expense Categories',
            'The expense categories used in the remote spreadsheet.',
            parent,
            self.category_editor
        )

        parent.layout().addStretch(1)

    def _connect_signals(self):
        pass

    def sizeHint(self):
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.6),
            ui.Size.DefaultHeight(1.6)
        )


class SettingsDockWidget(DockableWidget):
    """Dockable widget for editing app settings."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__('Settings', parent=parent, min_width=ui.Size.DefaultWidth(1.0))
        self.setObjectName('ExpenseTrackerSettingsWidget')

        content = QtWidgets.QWidget(self)
        QtWidgets.QVBoxLayout(content)
        content.layout().setContentsMargins(0, 0, 0, 0)
        content.layout().setSpacing(0)

        settings_widget = SettingsWidget(parent=content)
        settings_widget.setWindowFlags(QtCore.Qt.Widget)
        content.layout().addWidget(settings_widget, 1)

        self.setWidget(content)
