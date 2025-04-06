"""Editor for setting up a Google Cloud project and Google OAuth client.

This project requires a Client ID to connect to the Google API.

"""
import json
import logging

from PySide6 import QtCore, QtWidgets, QtGui

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


class ImportSecretDialog(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setWindowTitle('Import Google OAuth Client Secret')
        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Maximum
        )

        self.import_button = None
        self.paste_button = None

        ui.set_stylesheet(self)

        self._create_ui()
        self._connect_signals()

    def _create_ui(self):
        QtWidgets.QHBoxLayout(self)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)

        splitter = QtWidgets.QSplitter(self)
        self.layout().addWidget(splitter, 1)

        # Load markdown help file
        help_widget = QtWidgets.QTextBrowser(parent=self)
        help_widget.setFocusPolicy(QtCore.Qt.NoFocus)

        help_widget.document().setIndentWidth(ui.Size.Indicator(4.0))

        help_widget.setOpenExternalLinks(True)
        with settings.paths.gcp_help_path.open('r') as f:
            help_widget.setMarkdown(f.read())
        splitter.addWidget(help_widget)

        # Paste and import buttons
        box = QtWidgets.QGroupBox(parent=self)
        QtWidgets.QVBoxLayout(box)

        self.import_button = QtWidgets.QPushButton('Import', self)
        box.layout().addWidget(self.import_button, 1)

        self.paste_button = QtWidgets.QPushButton('Paste', self)
        box.layout().addWidget(self.paste_button, 1)

        splitter.addWidget(box)

    def _connect_signals(self):
        pass

    def sizeHint(self):
        """
        Returns the size hint for the dialog.
        """
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.0)
        )


class ClientEditor(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.import_secret_button = None
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

        self.import_secret_button = QtWidgets.QPushButton('Import Secret', self)
        self.import_secret_button.setIcon(ui.get_icon('ledger'))
        self.import_secret_button.setToolTip('Import Google OAuth Client Secret')
        self.layout().addRow('', self.import_secret_button)

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
        action = QtGui.QAction('Import Google OAuth Client Secret', self)
        action.setToolTip('Import Google OAuth Client Secret')
        action.setShortcut('Ctrl+I')
        action.setIcon(ui.get_icon('ledger'))
        action.triggered.connect(self.show_import_dialog)

        self.addAction(action)



    def _connect_signals(self):
        def on_section_changed(section):
            if section != 'client_secret':
                return
            self.init_data()

        signals.configSectionChanged.connect(on_section_changed)

        self.import_secret_button.clicked.connect(self.show_import_dialog)

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
    def show_import_dialog(self):
        """
        Shows the import dialog for the Google OAuth client secret.
        """
        dialog = ImportSecretDialog(self)
        dialog.open()