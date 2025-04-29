import ctypes
import uuid

from PySide6 import QtCore, QtWidgets


def set_application_properties(app=None):
    """Enables OpenGL and high-dpi support.

    """
    if app:
        app.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
        return

    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseOpenGLES, True)
    QtWidgets.QApplication.setAttribute(
        QtCore.Qt.AA_EnableHighDpiScaling, True
    )
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)


def set_model_id():
    """Set windows model id to add custom window icons on windows.
    https://github.com/cztomczak/cefpython/issues/395

    """
    if QtCore.QSysInfo().productType() in ('windows', 'winrt'):
        hresult = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f'ExpenseTracker-{uuid.uuid4()}'.encode('utf-8')
        )
        # An identifier that's globally unique for all apps running on Windows
        assert hresult == 0, "SetCurrentProcessExplicitAppUserModelID failed"
