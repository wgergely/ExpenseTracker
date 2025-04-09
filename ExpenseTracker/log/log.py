import logging
import sys
from PySide6.QtCore import QtMsgType, qInstallMessageHandler

LOG_LEVEL = logging.DEBUG
LOG_FORMAT = '[%(asctime)s] <%(module)s> %(levelname)s:  %(message)s'
LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'

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

    stream_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATEFMT)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(LOG_LEVEL)

    root_logger.addHandler(stream_handler)

    # Qt messages will now also be routed through this formatter
    qInstallMessageHandler(qt_message_handler)
