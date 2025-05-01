"""Client editor: dialogs and preview for Google OAuth client secrets.

Provides:
    - JsonPreviewWidget: displays current client_secret.json in formatted view
    - ImportSecretDialog: dialog to import or paste OAuth client secret
"""
import json
import logging

from PySide6 import QtCore, QtWidgets, QtGui

from ...core import auth
from ...settings.lib import settings
from ...ui import ui
from ...ui.actions import signals


class JsonPreviewWidget(QtWidgets.QPlainTextEdit):
    """Widget to display and preview JSON content of the client secret configuration."""
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setReadOnly(True)
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setContextMenuPolicy(QtCore.Qt.NoContextMenu)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Maximum
        )

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


class ImportSecretDialog(QtWidgets.QDialog):
    """Dialog for importing or pasting Google OAuth client secret data."""
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setWindowTitle('Import Google OAuth Client Secret')
        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Maximum
        )

        self.import_button = None
        self.paste_button = None

        self._create_ui()
        self._connect_signals()

    def _create_ui(self):
        QtWidgets.QHBoxLayout(self)

        o = ui.Size.Margin(1.0)
        self.layout().setContentsMargins(o, o, o, o)
        self.layout().setSpacing(0)

        splitter = QtWidgets.QSplitter(self)
        self.layout().addWidget(splitter, 1)

        # Load markdown help file
        help_widget = QtWidgets.QTextBrowser(parent=self)
        help_widget.setFocusPolicy(QtCore.Qt.NoFocus)

        help_widget.document().setIndentWidth(ui.Size.Indicator(4.0))

        help_widget.setOpenExternalLinks(True)
        with settings.gcp_help_path.open('r') as f:
            help_widget.setMarkdown(f.read())
        splitter.addWidget(help_widget)

        # Paste and import buttons
        box = QtWidgets.QGroupBox(parent=self)
        QtWidgets.QVBoxLayout(box)

        box.layout().addStretch(1)

        self.import_button = QtWidgets.QPushButton('Import', self)
        box.layout().addWidget(self.import_button, 1)

        self.paste_button = QtWidgets.QPushButton('Paste', self)
        box.layout().addWidget(self.paste_button, 1)

        box.layout().addStretch(1)

        splitter.addWidget(box)

    def _connect_signals(self):
        self.import_button.clicked.connect(self.import_secret)
        self.paste_button.clicked.connect(self.paste_secret)

    def sizeHint(self):
        """
        Returns the size hint for the dialog.
        """
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.5),
            ui.Size.DefaultHeight(1.3)
        )

    @QtCore.Slot()
    def import_secret(self):
        """
        Imports the Google OAuth client secret from a file.
        """
        file_dialog = QtWidgets.QFileDialog(self)
        file_dialog.setWindowTitle('Import Google OAuth Client Secret')
        file_dialog.setFileMode(QtWidgets.QFileDialog.ExistingFiles)
        file_dialog.setNameFilter('JSON files (*.json)')
        file_dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptOpen)

        # Default to the user downloads directory
        downloads_dir = QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.DownloadLocation
        )
        file_dialog.setDirectory(downloads_dir)

        if file_dialog.exec_() != QtWidgets.QDialog.Accepted:
            logging.warning('File dialog was canceled.')
            return

        files = file_dialog.selectedFiles()
        if not files:
            logging.warning('No files selected.')
            return

        file_path = files[0]
        with open(file_path, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                error_msg = f'Failed to parse JSON from {file_path}.'
                logging.error(error_msg)
                QtWidgets.QMessageBox.critical(
                    self,
                    'Error',
                    error_msg
                )
                return

        try:
            settings.set_section('client_secret', data)
        except Exception as e:
            error_msg = f'Failed to set client secret data: {e}'
            logging.error(error_msg)
            QtWidgets.QMessageBox.critical(
                self,
                'Error',
                error_msg
            )
            return

        self.accept()

    @QtCore.Slot()
    def paste_secret(self):
        """
        Pastes the Google OAuth client secret from the clipboard.
        """
        clipboard = QtWidgets.QApplication.clipboard()
        mime_data = clipboard.mimeData()

        if not mime_data.hasText():
            logging.warning('Clipboard does not contain text.')
            QtWidgets.QMessageBox.warning(
                self,
                'Warning',
                'Clipboard does not contain text.'
            )
            return

        text = mime_data.text()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            error_msg = 'Failed to parse JSON from clipboard.'
            logging.error(error_msg)
            QtWidgets.QMessageBox.critical(
                self,
                'Error',
                error_msg
            )
            return

        try:
            settings.set_section('client_secret', data)
        except Exception as e:
            error_msg = f'Failed to set client secret data: {e}'
            logging.error(error_msg)
            QtWidgets.QMessageBox.critical(
                self,
                'Error',
                error_msg
            )
            return

        self.accept()


class ClientEditor(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.import_secret_button = None
        self.client_id_preview = None
        self.project_id_preview = None
        self.client_secret_preview = None
        self.json_preview = None
        self.auth_button = None

        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Maximum
        )

        self._create_ui()
        self._init_actions()
        self._connect_signals()

        QtCore.QTimer.singleShot(150, self.init_data)

    def _create_ui(self):
        QtWidgets.QFormLayout(self)
        self.layout().setContentsMargins(0, 0, 0, 0)
        o = ui.Size.Indicator(1.0)
        self.layout().setSpacing(o)

        self.import_secret_button = QtWidgets.QPushButton('Import Secret', self)
        self.import_secret_button.setIcon(ui.get_icon('btn_ledger'))
        self.import_secret_button.setToolTip('Import Google OAuth Client Secret')
        self.layout().addRow('', self.import_secret_button)

        self.client_id_preview = QtWidgets.QLineEdit(self)
        self.client_id_preview.setPlaceholderText('Client ID not found')
        self.client_id_preview.setReadOnly(True)
        self.client_id_preview.setFocusPolicy(QtCore.Qt.NoFocus)
        self.client_id_preview.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
        self.layout().addRow('Client ID', self.client_id_preview)

        self.project_id_preview = QtWidgets.QLineEdit(self)
        self.project_id_preview.setPlaceholderText('Project ID not found')
        self.project_id_preview.setReadOnly(True)
        self.project_id_preview.setFocusPolicy(QtCore.Qt.NoFocus)
        self.project_id_preview.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
        self.layout().addRow('Project ID', self.project_id_preview)

        self.client_secret_preview = QtWidgets.QLineEdit(self)
        self.client_secret_preview.setPlaceholderText('Client Secret not found')
        self.client_secret_preview.setReadOnly(True)
        self.client_secret_preview.setFocusPolicy(QtCore.Qt.NoFocus)
        self.client_secret_preview.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
        self.layout().addRow('Client Secret', self.client_secret_preview)

        self.json_preview = JsonPreviewWidget(self)
        self.layout().addRow('JSON', self.json_preview)

        self.auth_button = QtWidgets.QPushButton('Authenticate', self)
        self.auth_button.setIcon(ui.get_icon('btn_authenticate'))
        self.auth_button.setToolTip('Authenticate with Google API')
        self.layout().addRow('', self.auth_button)

    def _init_actions(self):
        action = QtGui.QAction('Import Google OAuth Client Secret', self)

        action.setToolTip('Import Google OAuth Client Secret')
        action.setShortcut('Ctrl+I')
        action.setIcon(ui.get_icon('btn_ledger'))
        action.triggered.connect(self.show_import_dialog)

        self.addAction(action)

    def _connect_signals(self):
        def on_section_changed(section):
            if section != 'client_secret':
                return
            self.init_data()

        signals.configSectionChanged.connect(on_section_changed)

        self.import_secret_button.clicked.connect(self.show_import_dialog)
        self.auth_button.clicked.connect(self.authenticate)

    def init_data(self):
        """
        Initializes the data in the editor.
        """
        try:
            data = settings.get_section('client_secret')
        except:
            logging.error('Failed to load client secret data.')
            self.client_id_preview.setText('')
            self.project_id_preview.setText('')
            self.client_secret_preview.setText('')
            return

        self.client_id_preview.setText(data['installed'].get('client_id', ''))
        self.project_id_preview.setText(data['installed'].get('project_id', ''))
        self.client_secret_preview.setText(data['installed'].get('client_secret', ''))

    @QtCore.Slot()
    def show_import_dialog(self):
        """
        Shows the import dialog for the Google OAuth client secret.
        """
        dialog = ImportSecretDialog(self)
        dialog.open()

    @QtCore.Slot()
    def authenticate(self):
        """
        Starts the authentication process.
        """
        auth.authenticate()
