"""
Main settings GUI. Merges client_secret.json editing with ledger info configuration.

.. seealso:: :mod:`settings.model`, :mod:`settings.editor`
"""

import json
from PySide6 import QtWidgets, QtCore

from .editor import JsonPreviewWidget
from .model import (
    LedgerSettingsData,
    CLIENT_SECRET_PATH
)
from ..auth import auth, service
from ..ui import ui
from .header_editor import HeaderEditor
from .data_mapping_editor import DataMappingEditor

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
    """
    The main widget that displays:
    1) Connect to Google / Client Secret form
    2) Ledger Info form (spreadsheet ID, sheet name)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ledger_data = LedgerSettingsData()
        ui.set_stylesheet(self)
        self._create_ui()
        self._connect_signals()

    def sizeHint(self):
        # Return a fixed size hint for the scroll area
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.6)
        )

    def _create_ui(self):
        # Use a custom scroll area that syncs child widget width to itself
        self._scroll_area = SettingsScrollArea(self)

        # Container: holds all content in a vertical layout
        container = QtWidgets.QWidget()
        container_layout = QtWidgets.QVBoxLayout(container)

        # Give the container a horizontal expanding policy, so it grows to fill
        container.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Preferred
        )

        # Margins & spacing
        margin_size = ui.Size.Margin(1.5)
        container_layout.setContentsMargins(margin_size, margin_size, margin_size, margin_size)
        container_layout.setSpacing(margin_size)

        # SECTION 1) CONNECT TO GOOGLE
        connect_label = QtWidgets.QLabel('Connect to Google')
        connect_label.setStyleSheet('font-weight: bold;')
        container_layout.addWidget(connect_label)

        connect_box = QtWidgets.QGroupBox('')
        connect_form = QtWidgets.QFormLayout(connect_box)
        connect_form.setHorizontalSpacing(margin_size * 3)

        # Row: Pick JSON & Paste from Clipboard
        pick_hbox = QtWidgets.QHBoxLayout()
        self.load_disk_btn = QtWidgets.QPushButton('Pick JSON')
        self.paste_btn = QtWidgets.QPushButton('Paste from Clipboard')
        self.help_btn = QtWidgets.QPushButton('Help')
        pick_hbox.addWidget(self.load_disk_btn, 1)
        pick_hbox.addWidget(self.paste_btn, 1)
        pick_hbox.addWidget(self.help_btn, 0)
        pick_widget = QtWidgets.QWidget()
        pick_widget.setLayout(pick_hbox)
        connect_form.addRow('Select Secret', pick_widget)

        # Row: JSON Preview
        self.json_preview = JsonPreviewWidget()
        connect_form.addRow('Client Secret JSON', self.json_preview)

        # Row: Save + Authenticate
        action_hbox = QtWidgets.QHBoxLayout()
        self.save_secret_btn = QtWidgets.QPushButton('Save Client Secret')
        self.authenticate_btn = QtWidgets.QPushButton('Authenticate')
        action_hbox.addWidget(self.save_secret_btn)
        action_hbox.addWidget(self.authenticate_btn)
        action_widget = QtWidgets.QWidget()
        action_widget.setLayout(action_hbox)
        connect_form.addRow('', action_widget)

        container_layout.addWidget(connect_box)

        # SECTION 2) LEDGER INFO
        ledger_label = QtWidgets.QLabel('Ledger Info')
        ledger_label.setStyleSheet('font-weight: bold;')
        container_layout.addWidget(ledger_label)

        ledger_box = QtWidgets.QGroupBox('')
        ledger_form = QtWidgets.QFormLayout(ledger_box)
        ledger_form.setHorizontalSpacing(margin_size * 3)

        self.ledger_id_edit = QtWidgets.QLineEdit()
        self.ledger_id_edit.setText(self.ledger_data.ledger_id)
        ledger_form.addRow('Spreadsheet ID', self.ledger_id_edit)

        self.sheet_name_edit = QtWidgets.QLineEdit()
        self.sheet_name_edit.setText(self.ledger_data.sheet_name)
        ledger_form.addRow('Sheet Name', self.sheet_name_edit)

        self.test_ledger_btn = QtWidgets.QPushButton('Test Sheet Access')
        ledger_form.addRow('Actions', self.test_ledger_btn)

        container_layout.addWidget(ledger_box)

        # BOTTOM: CLOSE BUTTON
        btns_layout = QtWidgets.QHBoxLayout()
        close_btn = QtWidgets.QPushButton('Close')
        close_btn.clicked.connect(self.close)
        btns_layout.addStretch(1)
        btns_layout.addWidget(close_btn)
        container_layout.addLayout(btns_layout)

        # SECTION 3) HEADERS
        header_label = QtWidgets.QLabel('Header Editor')
        header_label.setStyleSheet('font-weight: bold;')
        container_layout.addWidget(header_label)

        header_box = QtWidgets.QGroupBox('')
        header_form = QtWidgets.QFormLayout(header_box)
        header_form.setHorizontalSpacing(margin_size * 3)

        self.header_editor = HeaderEditor(self)
        header_form.addRow('Spreadsheet Columns', self.header_editor)

        self.data_mapping_editor = DataMappingEditor(self)
        header_form.addRow('Columns Map', self.data_mapping_editor)

        # Add the header editor to the container layout
        container_layout.addWidget(header_box)


        # Place our container in the custom scroll area
        self._scroll_area.setWidget(container)



        # Final layout for SettingsWidget
        final_layout = QtWidgets.QVBoxLayout(self)
        final_layout.addWidget(self._scroll_area)
        self.setLayout(final_layout)

        self.load_existing_secret()

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
