"""
ExpenseTracker: desktop application for tracking and analyzing expenses from Google Sheets.

This package provides:

- :mod:`ExpenseTracker.core` – Core services for authentication, data synchronization, and local caching.
- :mod:`ExpenseTracker.data` – Data analytics APIs (:func:`ExpenseTracker.data.data.get_data`, :func:`ExpenseTracker.data.data.get_trends`) and Qt table models for summaries and transactions.
- :mod:`ExpenseTracker.ui` – A modern PySide6-based UI with custom views, delegates, and charts (pie, trends).
- :mod:`ExpenseTracker.settings` – Settings management, including schema validation, editors, and presets.
- :mod:`ExpenseTracker.log` – In-app logging with real-time log viewer.

Use :func:`ExpenseTracker.exec_` to launch the application.
"""

import os
import pathlib
import sys

from PySide6 import QtCore

# Fail on Python < 3.11
if not (sys.version_info.major == 3 and sys.version_info.minor >= 11):
    raise RuntimeError('ExpenseTracker requires Python 3.11 or higher.')

__version__ = '0.0.0'
__author__ = 'Gergely Wootsch'
__license__ = 'GPL-3.0'
__copyright__ = 'Copyright (C) 2025 Gergely Wootsch'
__description__ = 'ExpenseTracker: desktop application for tracking and analyzing personal expenses from Google Sheets.'
__url__ = 'https://github.com/wgergely/ExpenseTracker'
__email__ = 'hello+ExpenseTracker@gergely-wootsch.com'


# Use internally shipped font directory for Qt font loading
font_dir = pathlib.Path(__file__).parent / 'config' / 'font'
os.environ.setdefault('QT_QPA_FONTDIR', str(font_dir))

from .log import log

log.setup_logging()

    

def exec_() -> None:
    """Launch the ExpenseTracker GUI application and enter its event loop.

    Initializes the QApplication, shows the main window, and starts the Qt event loop.
    """
    import sys
    from .ui import app
    from .ui import main
    from .ui.actions import signals
    app = app.Application(sys.argv)
    main.show()

    # Ask componentes to load their data
    QtCore.QTimer.singleShot(100, signals.initializationRequested)

    sys.exit(app.exec())


if __name__ == '__main__':
    exec_()
