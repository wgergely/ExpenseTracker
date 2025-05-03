"""ExpenseTracker: desktop application for tracking and analyzing expenses from Google Sheets.

This package provides:
    - Core services for authentication, data synchronization, and local caching
    - Data analytics APIs (get_data, get_trends) and Qt table models for summaries and transactions
    - A modern PySide6-based UI with custom views, delegates, and charts (pie, trends)
    - Settings management, including schema validation, editors, and presets
    - In-app logging with real-time log viewer

Use exec_() to launch the application.
"""

import os
import pathlib

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
    app = app.Application(sys.argv)
    main.show()
    sys.exit(app.exec())
