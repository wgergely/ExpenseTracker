"""Editor for setting up a Google Cloud project and Google OAuth client.

This project requires a Client ID to connect to the Google API.

"""
import json
import logging

from PySide6 import QtCore, QtWidgets

from ...settings.lib import settings
from ...ui import ui
from ...ui.actions import signals


class JsonPreviewWidget(QtWidgets.QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setReadOnly(True)
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

        self._connect_signals()

        QtCore.QTimer.singleShot(150, self.init_data)

    def _connect_signals(self):
        @QtCore.Slot(str)
        def on_section_changed(section):
            if section != 'client_secret':
                return
            self.init_data()

        signals.configSectionChanged.connect(on_section_changed)

    @QtCore.Slot()
    def init_data(self) -> None:
        """
        Sets text into the editor. Parses as JSON, stores the parsed data, and pretty-prints.
        If parsing fails, the text is displayed as-is, and no JSON data is stored.
        """
        data = settings.get_section('client_secret')

        try:
            display_str = json.dumps(data, indent=4, ensure_ascii=False)
            self.setPlainText(display_str)
        except:
            self.setPlainText('Failed to parse JSON: Invalid data.')


class ClientEditor(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.client_id_preview = None
        self.project_id_preview = None
        self.client_secret_preview = None
        self.json_preview = None

        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Maximum
        )

        ui.set_stylesheet(self)

        self._create_ui()
        self._init_actions()
        self._connect_signals()

        QtCore.QTimer.singleShot(150, self.init_data)

    def _create_ui(self):
        QtWidgets.QFormLayout(self)
        self.layout().setContentsMargins(0, 0, 0, 0)
        o = ui.Size.Indicator(1.0)
        self.layout().setSpacing(o)

        self.client_id_preview = QtWidgets.QLineEdit(self)
        self.client_id_preview.setPlaceholderText('Client ID not found')
        self.client_id_preview.setReadOnly(True)
        self.client_id_preview.setFocusPolicy(QtCore.Qt.NoFocus)
        self.layout().addRow('Client ID', self.client_id_preview)

        self.project_id_preview = QtWidgets.QLineEdit(self)
        self.project_id_preview.setPlaceholderText('Project ID not found')
        self.project_id_preview.setReadOnly(True)
        self.project_id_preview.setFocusPolicy(QtCore.Qt.NoFocus)
        self.layout().addRow('Project ID', self.project_id_preview)

        self.client_secret_preview = QtWidgets.QLineEdit(self)
        self.client_secret_preview.setPlaceholderText('Client Secret not found')
        self.client_secret_preview.setReadOnly(True)
        self.client_secret_preview.setFocusPolicy(QtCore.Qt.NoFocus)
        self.layout().addRow('Client Secret', self.client_secret_preview)

        self.json_preview = JsonPreviewWidget(self)
        self.layout().addRow('JSON', self.json_preview)

    def _init_actions(self):
        pass

    def _connect_signals(self):
        def on_section_changed(section):
            if section != 'client_secret':
                return
            self.init_data()

        signals.configSectionChanged.connect(on_section_changed)

    def init_data(self):
        """
        Initializes the data in the editor.
        """
        try:
            data = settings.get_section('client_secret')
        except:
            logging.error('Failed to load client secret data.')
            data = {}

        if not data or 'installed' not in data:
            self.client_id_preview.setText('')
            self.project_id_preview.setText('')
            self.client_secret_preview.setText('')
            return

        self.client_id_preview.setText(data['installed'].get('client_id', ''))
        self.project_id_preview.setText(data['installed'].get('project_id', ''))
        self.client_secret_preview.setText(data['installed'].get('client_secret', ''))

    @QtCore.Slot()
    def parse_clipboard(self):
        """
        Parses the clipboard data as JSON and updates the preview.
        """
        clipboard = QtWidgets.QApplication.clipboard()
        if not clipboard:
            return

        if not clipboard.mimeData().hasText():
            logging.warning('Clipboard does not contain text data.')
            QtWidgets.QMessageBox.warning(
                self,
                'Clipboard Error',
                'Clipboard does not contain text data.'
            )

            return

        raw_str = clipboard.text()

        try:
            data = json.loads(raw_str)
        except json.JSONDecodeError:
            logging.warning('Clipboard data is not valid JSON.')
            QtWidgets.QMessageBox.warning(
                self,
                'Clipboard Error',
                'Clipboard data is not valid JSON.'
            )
            return
        except TypeError:
            logging.warning('Clipboard data is not valid JSON.')
            QtWidgets.QMessageBox.warning(
                self,
                'Clipboard Error',
                'Clipboard data is not valid JSON.'
            )
            return
        except (ValueError, KeyError, AttributeError, RuntimeError):
            logging.warning('Clipboard data is not valid JSON.')
            QtWidgets.QMessageBox.warning(
                self,
                'Clipboard Error',
                'Clipboard data is not valid JSON.'
            )
            return

        for k in ('client_id', 'project_id', 'client_secret'):
            if k not in data:
                logging.warning(f'Clipboard data is valid but could not find "{k}".')
                QtWidgets.QMessageBox.warning(
                    self,
                    'Unexpected Data',
                    f'Found valid JSON but the "{k}" field seems to be missing.'
                )
                return

        settings.set_section('client_secret', data)