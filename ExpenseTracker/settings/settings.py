"""The main settings widget for the app.

"""

from PySide6 import QtWidgets, QtCore

from .editors import category_editor
from .editors import client_editor
from .editors import data_mapping_editor
from .editors import header_editor
from .editors import spreadsheet_editor
from ..ui import ui

settings_widget = None


def show_settings_widget(parent=None):
    """
    Show the settings widget.

    Args:
        parent (QWidget, optional): Parent widget.
    """
    global settings_widget
    if settings_widget is None:
        settings_widget = SettingsWidget(parent=parent)
    settings_widget.open()
    return settings_widget


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
    #
    # def resizeEvent(self, event):
    #     super().resizeEvent(event)
    #     # Force container to match our viewport width after each resize
    #     if self.widget():
    #         self.widget().setFixedWidth(self.viewport().width())


class SettingsWidget(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName('SettingsWidget')
        self.setWindowTitle('Settings')

        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.WindowCloseButtonHint |
            QtCore.Qt.WindowMinMaxButtonsHint
        )

        self._sections = []

        self.client_editor = None
        self.spreadsheet_editor = None
        self.header_editor = None
        self.data_mapping_editor = None
        self.category_editor = None

        ui.set_stylesheet(self)

        self._create_ui()
        self._connect_signals()

    def _add_section(self, title: str, label: str, parent: QtWidgets.QWidget, editor):
        title_widget = QtWidgets.QLabel(title)
        title_widget.setStyleSheet(f'font-weight: 900;font-size:{ui.Size.LargeText(1.0)}px;')

        parent.layout().addSpacing(ui.Size.Margin(1.0))
        parent.layout().addWidget(title_widget, 0)

        group = QtWidgets.QGroupBox('')
        QtWidgets.QFormLayout(group)

        o = ui.Size.Margin(1.0)
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
        self.layout().addWidget(scroll_area)

        parent = QtWidgets.QWidget()
        QtWidgets.QVBoxLayout(parent)

        scroll_area.setFocusProxy(parent)

        scroll_area.setWidget(parent)

        parent.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.MinimumExpanding
        )

        o = ui.Size.Margin(1.0)
        parent.layout().setContentsMargins(o, o, o, o)
        parent.layout().setSpacing(o)

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
