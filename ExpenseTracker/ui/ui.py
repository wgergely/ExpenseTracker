import functools
import os
import pathlib

from PySide6 import QtWidgets

STYLESHEET_PATH = pathlib.Path(os.path.dirname(__file__)).parent / 'config' / 'stylesheet.qss'


@functools.cache
def _load_stylesheet() -> str:
    """
    Load the stylesheet from the specified path.

    Returns:
        str: The contents of the stylesheet file.

    """
    try:
        with open(STYLESHEET_PATH, 'r') as file:
            return file.read()
    except FileNotFoundError:
        print(f'Stylesheet file not found at {STYLESHEET_PATH}')
        return ''


def set_stylesheet(widget: QtWidgets.QWidget) -> None:
    """
    Set the stylesheet for the given QApplication instance.

    Args:
        widget (QtWidgets.QWidget): The widget to apply the stylesheet to.

    """
    app = QtWidgets.QApplication.instance()
    if not app:
        raise RuntimeError(
            'No QApplication instance found. Please create an instance before calling set_stylesheet().')
    stylesheet = _load_stylesheet()
    widget.setStyleSheet(stylesheet)
