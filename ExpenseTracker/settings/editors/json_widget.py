"""
Custom editor delegates for settings views.

.. seealso:: :mod:`settings.model`, :mod:`settings.view`, :mod:`settings.settings`
"""
import json

from PySide6 import QtWidgets, QtCore



class JSONWidget(QtWidgets.QWidget):
    """
    A widget to preview JSON text in read-only mode.
    Externally, call set_json_text(...) to load and pretty-print JSON.
    get_json_data() returns the last valid JSON object that was set.
    """
    jsonChanged = QtCore.Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFocusPolicy(QtCore.Qt.NoFocus)

        self.text_edit = None
        self._json_data = {}

        self._create_ui()

    def _create_ui(self):
        QtWidgets.QVBoxLayout(self)

        self.text_edit = QtWidgets.QPlainTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.text_edit.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.text_edit.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.text_edit.setFocusPolicy(QtCore.Qt.NoFocus)

        self.layout().addWidget(self.text_edit)


    def set_json_text(self, text):
        """
        Sets text into the editor. Parses as JSON, stores the parsed data, and pretty-prints.
        If parsing fails, the text is displayed as-is, and no JSON data is stored.
        """
        self._json_data = {}
        try:
            data = json.loads(text)
            pretty = json.dumps(data, indent=2)
            self.text_edit.setPlainText(pretty)
            self._json_data = data
            self.jsonChanged.emit(data)
        except Exception:
            self.text_edit.setPlainText(text)
            # Do not overwrite self._json_data if parsing fails

    def get_json_data(self):
        """
        Returns the last valid JSON object parsed from set_json_text.
        If none was parsed successfully, returns an empty dict.
        """
        return self._json_data
