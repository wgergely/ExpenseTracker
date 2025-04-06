"""
Main settings GUI. Merges client_secret.json editing with ledger info configuration.

.. seealso:: :mod:`settings.model`, :mod:`settings.editor`
"""

import json

from PySide6 import QtWidgets, QtCore

from .category_editor import CategoryEditor
from .data_mapping_editor import DataMappingEditor
from .editor import JSONWidget
from .header_editor import HeaderEditor
from .model import (
    LedgerSettingsData,
    CLIENT_SECRET_PATH
)
from ..auth import auth, service
from ..ui import ui


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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Force container to match our viewport width after each resize
        if self.widget():
            self.widget().setFixedWidth(self.viewport().width())


class SettingsWidget(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ledger_data = LedgerSettingsData()

        ui.set_stylesheet(self)

        self._create_ui()
        self._connect_signals()

        self.load_existing_secret()

    def sizeHint(self):
        # Return a fixed size hint for the scroll area
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.6)
        )

    def _create_ui(self):
        # Use a custom scroll area that syncs child widget width to itself
        self._scroll_area = SettingsScrollArea(self)

        self.load_disk_btn = QtWidgets.QPushButton('Import JSON')
        self.paste_btn = QtWidgets.QPushButton('Paste from Clipboard')
        self.help_btn = QtWidgets.QPushButton('Help')
        self.save_secret_btn = QtWidgets.QPushButton('Save Client Secret')
        self.authenticate_btn = QtWidgets.QPushButton('Authenticate')

        # Container: holds all content in a vertical layout
        container = QtWidgets.QWidget()
        container_layout = QtWidgets.QVBoxLayout(container)

        # Give the container a horizontal expanding policy, so it grows to fill
        container.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Preferred
        )

        # Margins & spacing
        o = ui.Size.Margin(1.0)
        container_layout.setContentsMargins(o, o, o, o)
        container_layout.setSpacing(o)

        # SECTION 1) CONNECT TO GOOGLE
        connect_label = QtWidgets.QLabel('Connect to Google')
        connect_label.setStyleSheet(f'font-weight: 900;font-size:{ui.Size.LargeText(1.0)}px;')
        container_layout.addWidget(connect_label)

        connect_box = QtWidgets.QGroupBox('')
        connect_form = QtWidgets.QFormLayout(connect_box)
        connect_form.setContentsMargins(o, o, o, o)
        connect_form.setSpacing(o)
        connect_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        connect_form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapAllRows)
        connect_form.setHorizontalSpacing(o)
        connect_form.setVerticalSpacing(o)

        # Row: Pick JSON & Paste from Clipboard
        pick_hbox = QtWidgets.QHBoxLayout()
        pick_hbox.setContentsMargins(0, 0, 0, 0)
        pick_hbox.setSpacing(o)
        pick_hbox.addWidget(self.load_disk_btn, 1)
        pick_hbox.addWidget(self.paste_btn, 1)
        pick_hbox.addWidget(self.help_btn, 0)
        pick_widget = QtWidgets.QWidget()
        pick_widget.setObjectName('wrapper')
        pick_widget.setStyleSheet('#wrapper { background: transparent; }')
        pick_widget.setLayout(pick_hbox)
        connect_form.addRow('Import Client Secret', pick_widget)

        # Row: JSON Preview
        self.json_preview = JSONWidget()
        connect_form.addRow('Preview', self.json_preview)

        container_layout.addWidget(connect_box)

        # SECTION 3) HEADERS
        header_label = QtWidgets.QLabel('Google Spreadsheet')
        header_label.setStyleSheet(f'font-weight: 900;font-size:{ui.Size.LargeText(1.0)}px;')
        container_layout.addWidget(header_label)

        header_box = QtWidgets.QGroupBox('')
        header_form = QtWidgets.QFormLayout(header_box)
        header_form.setContentsMargins(o, o, o, o)
        header_form.setSpacing(o)
        header_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        header_form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapAllRows)
        header_form.setHorizontalSpacing(o)
        header_form.setVerticalSpacing(o)

        # Row: Save + Authenticate
        connect_form.addRow('', self.save_secret_btn)
        connect_form.addRow('', self.authenticate_btn)

        self.ledger_id_edit = QtWidgets.QLineEdit(parent=self)
        self.ledger_id_edit.setText(self.ledger_data.ledger_id)
        self.ledger_id_edit.setPlaceholderText('e.g. 1a2b3c4d5e6f7g8h9i0j')
        header_form.addRow('Google Spreadsheet ID Properties', self.ledger_id_edit)

        self.sheet_name_edit = QtWidgets.QLineEdit(parent=self)
        self.sheet_name_edit.setText(self.ledger_data.sheet_name)
        self.sheet_name_edit.setPlaceholderText('e.g. Sheet1')
        header_form.addRow('Sheet to Use', self.sheet_name_edit)

        self.test_ledger_btn = QtWidgets.QPushButton('Test Access', parent=self)
        header_form.addRow('', self.test_ledger_btn)

        # Add the header editor to the container layout
        container_layout.addWidget(header_box)

        # SECTION 2) HEADER EDITOR

        header_label = QtWidgets.QLabel('Source Columns')
        header_label.setStyleSheet(f'font-weight: 900;font-size:{ui.Size.LargeText(1.0)}px;')
        container_layout.addWidget(header_label)

        header_box = QtWidgets.QGroupBox('')
        header_form = QtWidgets.QFormLayout(header_box)
        header_form.setContentsMargins(o, o, o, o)
        header_form.setSpacing(o)
        header_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        header_form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapAllRows)
        header_form.setHorizontalSpacing(o)
        header_form.setVerticalSpacing(o)

        self.header_editor = HeaderEditor(parent=self)
        header_form.addRow('The source spreadsheet columns', self.header_editor)

        # Add the header editor to the container layout
        container_layout.addWidget(header_box)

        # SECTION 3) DATA MAPPING

        data_mapping_label = QtWidgets.QLabel('Column Mapping')
        data_mapping_label.setStyleSheet(f'font-weight: 900;font-size:{ui.Size.LargeText(1.0)}px;')
        container_layout.addWidget(data_mapping_label)

        data_mapping_box = QtWidgets.QGroupBox('')
        data_mapping_form = QtWidgets.QFormLayout(data_mapping_box)
        data_mapping_form.setContentsMargins(o, o, o, o)
        data_mapping_form.setSpacing(o)
        data_mapping_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        data_mapping_form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapAllRows)
        data_mapping_form.setHorizontalSpacing(o)
        data_mapping_form.setVerticalSpacing(o)

        self.data_mapping_editor = DataMappingEditor(parent=self)
        data_mapping_form.addRow('Map Google Spreadsheet Columns', self.data_mapping_editor)

        # Add the data mapping editor to the container layout
        container_layout.addWidget(data_mapping_box)

        # SECTION 4) CATEGORIES

        category_label = QtWidgets.QLabel('Categories')
        category_label.setStyleSheet(f'font-weight: 900;font-size:{ui.Size.LargeText(1.0)}px;')
        container_layout.addWidget(category_label)

        category_box = QtWidgets.QGroupBox('')
        category_form = QtWidgets.QFormLayout(category_box)
        category_form.setContentsMargins(o, o, o, o)
        category_form.setSpacing(o)
        category_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        category_form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapAllRows)
        category_form.setHorizontalSpacing(o)
        category_form.setVerticalSpacing(o)

        self.category_editor = CategoryEditor(parent=self)
        category_form.addRow('', self.category_editor)

        # Add the header editor to the container layout
        container_layout.addWidget(category_box)

        # Place our container in the custom scroll area
        self._scroll_area.setWidget(container)

        # BOTTOM: CLOSE BUTTON
        btns_layout = QtWidgets.QHBoxLayout()
        close_btn = QtWidgets.QPushButton('Close')
        close_btn.clicked.connect(self.close)
        btns_layout.addStretch(1)
        btns_layout.addWidget(close_btn)
        container_layout.addLayout(btns_layout)

        # Final layout for SettingsWidget
        final_layout = QtWidgets.QVBoxLayout(self)
        final_layout.setContentsMargins(0, 0, 0, 0)
        final_layout.addWidget(self._scroll_area)

    def _connect_signals(self):
        self.load_disk_btn.clicked.connect(self.on_load_secret_from_disk)
        self.paste_btn.clicked.connect(self.on_paste_secret)
        self.save_secret_btn.clicked.connect(self.on_save_secret)
        self.authenticate_btn.clicked.connect(self.on_auth)
        self.help_btn.clicked.connect(self.show_help_dialog)
        self.test_ledger_btn.clicked.connect(self.on_test_sheet_access)

    def load_existing_secret(self):
        """
        If client_secret.json exists, load and display it in the JSON preview.
        """
        if CLIENT_SECRET_PATH.exists():
            with open(CLIENT_SECRET_PATH, 'r', encoding='utf-8') as f:
                text = f.read()
            self.json_preview.set_json_text(text)

    def show_help_dialog(self):
        QtWidgets.QMessageBox.information(
            self,
            'How to set up Google OAuth',
            (
                '1. Go to Google Cloud Console and create a project.\n'
                "2. Under 'APIs & Services', create OAuth client credentials.\n"
                '3. Download the JSON secret or copy it from the console.\n'
                '4. Paste/load that JSON below.\n'
                "Click 'Authenticate' to test your credentials.\n"
            )
        )

    def on_load_secret_from_disk(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Open client_secret.json', '', 'JSON Files (*.json)')
        if path:
            with open(path, 'r', encoding='utf-8') as f:
                text = f.read()
            try:
                json.loads(text)
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, 'Error', f'Invalid JSON:\n{e}')
                return
            self.json_preview.set_json_text(text)

    def on_paste_secret(self):
        clipboard = QtWidgets.QApplication.clipboard()
        text = clipboard.text()
        if not text.strip():
            QtWidgets.QMessageBox.warning(self, 'Error', 'Clipboard is empty.')
            return
        try:
            json.loads(text)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Error', f'Invalid JSON:\n{e}')
            return
        self.json_preview.set_json_text(text)

    def on_save_secret(self):
        """
        Save the currently displayed JSON text to client_secret.json file.
        """
        data = self.json_preview.get_json_data()
        if not data:
            QtWidgets.QMessageBox.warning(self, 'Error', 'No valid JSON to save.')
            return
        try:
            with open(CLIENT_SECRET_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            QtWidgets.QMessageBox.information(self, 'Saved', 'Client secret file saved.')
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Error', f'Failed to write file:\n{e}')

    def on_auth(self):
        """
        Attempt to authenticate using auth.authenticate(force=True).
        Save the client secret first to ensure credentials are current.
        """
        self.on_save_secret()
        try:
            auth.authenticate(force=True)
            QtWidgets.QMessageBox.information(self, 'Success', 'Connection tested successfully.')
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Error', f'Connection failed:\n{e}')

    def on_test_sheet_access(self):
        """
        Attempt to test spreadsheet access using service.get_data(force=False).
        """
        self.update_ledger_data()
        try:
            service.get_data(force=False)
            QtWidgets.QMessageBox.information(self, 'Success', 'Spreadsheet access test successful.')
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Error', f'Spreadsheet access failed:\n{e}')

    def update_ledger_data(self):
        """
        Update the ledger_data from UI fields (spreadsheet id, sheet name)
        then save it to LEDGER_PATH.
        """
        self.ledger_data.ledger_id = self.ledger_id_edit.text()
        self.ledger_data.sheet_name = self.sheet_name_edit.text()
        self.ledger_data.save()
