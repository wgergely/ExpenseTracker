"""Application setup utilities and custom QApplication for ExpenseTracker.

This module provides:
    - set_application_properties: enable OpenGL and high-DPI support
    - set_model_id: set Windows AppUserModelID for custom window icons on Windows
    - Application: subclass of QApplication configuring application metadata and theme
"""
import ctypes
import sys
import uuid
from typing import Optional, Sequence

from PySide6 import QtCore, QtWidgets, QtGui

__version__ = '0.1.0'


def set_application_properties(app: Optional[QtWidgets.QApplication] = None) -> None:
    """Enables OpenGL and high-dpi support."""
    if app:
        app.setAttribute(QtCore.Qt.AA_UseOpenGLES, True)
        app.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
        app.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
        return

    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseOpenGLES, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)


def set_app_icon() -> None:
    """Set application icon for all platforms."""
    from ..settings import lib
    icon_path = lib.settings.template_dir / 'icon.png'
    if icon_path.exists():
        app = QtWidgets.QApplication.instance()
        app.setWindowIcon(QtGui.QIcon(icon_path.as_posix()))

def set_model_id() -> None:
    """Set windows model id to add custom window icons on windows.
    https://github.com/cztomczak/cefpython/issues/395
    """
    if QtCore.QSysInfo().productType() in ('windows', 'winrt'):
        hresult = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f'ExpenseTracker-{uuid.uuid4()}'.encode('utf-8')
        )
        if hresult != 0:
            raise RuntimeError(f'SetCurrentProcessExplicitAppUserModelID failed with code {hresult}')


class Application(QtWidgets.QApplication):
    """Custom QApplication enabling high-DPI, OpenGL, and Windows model ID."""

    def __init__(self, argv: Optional[Sequence[str]] = None) -> None:
        set_application_properties()
        if argv is None:
            argv = sys.argv

        super().__init__(list(argv))
        set_model_id()

        from ..settings import lib
        self.setApplicationName(lib.app_name)
        self.setOrganizationName('')
        self.setApplicationVersion(__version__)
        self.setQuitOnLastWindowClosed(True)

        set_model_id()
        set_app_icon()

        from . import ui
        ui.apply_theme()
