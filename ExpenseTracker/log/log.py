import logging
import sys

from PySide6.QtCore import QtMsgType, qInstallMessageHandler

from ..ui.actions import signals

LOG_LEVEL = logging.DEBUG
LOG_FORMAT = '[%(asctime)s] <%(module)s> %(levelname)s:  %(message)s'
LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'


def set_logging_level(level):
    """
    Sets the logging level for the root logger.

    Args:
        level (int): The logging level to set. Should be one of the standard logging levels.
    """
    if not isinstance(level, int):
        raise ValueError("Logging level must be an integer.")
    if level not in (
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
            logging.CRITICAL,
    ):
        raise ValueError('Invalid logging level. Use one of the standard logging levels, e.g., logging.DEBUG.')

    logging.getLogger().setLevel(level)


def qt_message_handler(mode, context, message):
    """
    Converts Qt messages to standard Python logging.
    """
    logger = logging.getLogger('Qt')

    # Qt message may have newline/stripped formatting
    message = message.strip()

    if mode == QtMsgType.QtDebugMsg:
        logger.debug(message)
    elif mode == QtMsgType.QtInfoMsg:
        logger.info(message)
    elif mode == QtMsgType.QtWarningMsg:
        logger.warning(message)
    elif mode == QtMsgType.QtCriticalMsg:
        logger.error(message)
    elif mode == QtMsgType.QtFatalMsg:
        logger.critical(message)
        sys.exit(1)


def setup_logging():
    """
    Configures the root logger and installs Qt message handler.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL)

    # Clear all handlers to avoid formatting conflicts
    root_logger.handlers.clear()

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATEFMT)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(LOG_LEVEL)
    root_logger.addHandler(stream_handler)

    tank_handler = TankHandler()
    tank_handler.setFormatter(formatter)
    tank_handler.setLevel(LOG_LEVEL)
    root_logger.addHandler(tank_handler)

    # Qt messages will now also be routed through this formatter
    qInstallMessageHandler(qt_message_handler)


class TankHandler(logging.Handler):
    """
    Custom logging handler that stores formatted log messages in an in-memory tank.

    This handler collects log records which can later be browsed and filtered based on
    the logging level.

    Attributes:
        tank (list[tuple[int, str]]): A list of tuples each containing a log level and the
            corresponding formatted log message.
    """

    def __init__(self):
        """
        Initializes the TankHandler with an empty tank.
        """
        super().__init__()
        self.tank = []

    def emit(self, record):
        """
        Converts a log record to a formatted message and stores it in the tank.

        Args:
            record (logging.LogRecord): The log record to be processed.
        """
        try:
            message = self.format(record)
            self.tank.append((record.levelno, message))
            # Auto-show log viewer on errors and criticals
            if record.levelno >= logging.ERROR:
                signals.showLogs.emit()
        except (Exception, KeyboardInterrupt):
            self.handleError(record)

    def get_logs(self, level=logging.NOTSET):
        """
        Returns the list of stored log messages filtered by a minimum logging level.

        Args:
            level (int, optional): The minimum logging level. Defaults to logging.NOTSET.

        Returns:
            list[str]: A list of formatted log messages with a level >= the specified level.
        """
        return [msg for lvl, msg in self.tank if lvl >= level]

    def clear_logs(self):
        """
        Clears all the stored log messages from the tank.
        """
        self.tank.clear()
