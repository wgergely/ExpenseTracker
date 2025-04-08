"""Config editor for ledger.json's "spreadsheet" section.

"""
import logging
import re

from PySide6 import QtCore, QtGui, QtWidgets

from .. import lib
from ...ui import actions
from ...ui import ui
from ...ui.actions import signals


class SpreadsheetEditor(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.id_editor = None
        self.worksheet_editor = None
        self.description_editor = None

        self.text_changed_timer = QtCore.QTimer(self)
        self.text_changed_timer.setSingleShot(True)
        self.text_changed_timer.setInterval(QtWidgets.QApplication.keyboardInputInterval())

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

        self.id_editor = QtWidgets.QLineEdit(self)
        self.id_editor.setPlaceholderText('e.g. "1a2b3c4d5e6f7g8h9i0j"')
        self.layout().addRow('Spreadsheet Id', self.id_editor)

        self.worksheet_editor = QtWidgets.QLineEdit(self)
        self.worksheet_editor.setPlaceholderText('e.g. "Sheet1"')
        self.layout().addRow('Worksheet', self.worksheet_editor)

        self.description_editor = QtWidgets.QLineEdit(self)
        self.description_editor.setPlaceholderText('e.g. private expenses')
        self.layout().addRow('Description', self.description_editor)

        self.layout().setAlignment(QtCore.Qt.AlignTop)

    def _init_actions(self):
        action = QtGui.QAction('Open Spreadsheet', self)
        action.setShortcut('Ctrl+Shift+O')
        action.setToolTip('Open spreadsheet in browser')
        action.setIcon(ui.get_icon('btn_ledger'))
        action.triggered.connect(actions.open_spreadsheet)
        self.addAction(action)
        self.id_editor.addAction(action, QtWidgets.QLineEdit.TrailingPosition)

        @QtCore.Slot()
        def reload_action():
            lib.settings.reload_section('spreadsheet')
            self.init_data()

        action = QtGui.QAction('Refresh', self)
        action.setShortcut('Ctrl+R')
        action.setStatusTip('Reload spreadsheet config')
        action.triggered.connect(reload_action)
        self.addAction(action)

        @QtCore.Slot()
        def reset_action():
            lib.settings.revert_section('spreadsheet')
            self.init_data()

        action = QtGui.QAction('Reset', self)
        action.setShortcut('Ctrl+Shift+R')
        action.setStatusTip('Reset spreadsheet config')
        action.setIcon(ui.get_icon('btn_reload'))
        action.triggered.connect(reset_action)
        self.addAction(action)

    def _connect_signals(self):
        @QtCore.Slot(str)
        def on_section_changed(section):
            if section != 'spreadsheet':
                return
            pass

        signals.configSectionChanged.connect(on_section_changed)

        self.id_editor.textChanged.connect(self.text_changed_timer.start)
        self.worksheet_editor.textChanged.connect(self.text_changed_timer.start)
        self.description_editor.textChanged.connect(self.text_changed_timer.start)

        self.text_changed_timer.timeout.connect(self.verify_id)
        self.text_changed_timer.timeout.connect(self.save_section)

    @QtCore.Slot()
    def save_section(self):
        data = self.get_current_section_data()
        lib.settings.set_section('spreadsheet', data)

    @QtCore.Slot()
    def get_current_section_data(self):
        return {
            'id': self.id_editor.text(),
            'worksheet': self.worksheet_editor.text(),
            'description': self.description_editor.text(),
        }

    @QtCore.Slot()
    def init_data(self):
        """
        Initialize the data in the editor.
        """
        data = lib.settings.get_section('spreadsheet')
        if not data:
            logging.warning('No data found in the spreadsheet section.')

        for k in data.keys():
            editor = getattr(self, f'{k}_editor', None)
            if not editor:
                logging.warning(f'Editor for "{k}" not found.')
                continue

            editor.blockSignals(True)
            editor.setText(data.get(k, ''))
            editor.blockSignals(False)

    @QtCore.Slot()
    def verify_id(self):
        """
        Verify the spreadsheet ID.
        """
        id_text = self.id_editor.text()
        if not id_text:
            return

        id_re = r'(?:(?:https?://)?docs\.google\.com/spreadsheets/d/|/d/)([a-zA-Z0-9\-_]+)'
        match = re.search(id_re, id_text)
        result = match.group(1) if match else None
        if not result:
            return

        logging.info(f'Extracted ID: {result}')
        self.id_editor.setText(result)
