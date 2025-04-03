"""
Custom editor delegates for settings views.

.. seealso:: :mod:`settings.model`, :mod:`settings.view`, :mod:`settings.settings`
"""
import json

from PySide6 import QtWidgets, QtGui, QtCore

HEADER_TYPES = ["string", "int", "float", "date"]


class HeaderTypeDelegate(QtWidgets.QItemDelegate):
    """
    Delegate to edit header 'type' via a combo box.
    """

    def createEditor(self, parent, option, index):
        combo = QtWidgets.QComboBox(parent)
        combo.addItems(HEADER_TYPES)
        return combo

    def setEditorData(self, editor, index):
        value = index.model().data(index, QtCore.Qt.EditRole)
        idx = editor.findText(value)
        if idx >= 0:
            editor.setCurrentIndex(idx)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), QtCore.Qt.EditRole)


class ColorDelegate(QtWidgets.QItemDelegate):
    """
    Delegate to pick a color with a dialog.
    """

    def createEditor(self, parent, option, index):
        # We'll trigger a color dialog in setModelData instead of using inline widgets.
        return None

    def setEditorData(self, editor, index):
        pass

    def setModelData(self, editor, model, index):
        old_val = index.model().data(index, QtCore.Qt.EditRole)
        new_color = QtWidgets.QColorDialog.getColor(QtGui.QColor(old_val))
        if new_color.isValid():
            model.setData(index, new_color.name(), QtCore.Qt.EditRole)
        else:
            model.setData(index, old_val, QtCore.Qt.EditRole)


class JsonPreviewWidget(QtWidgets.QWidget):
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
