import enum
import logging
import re
from datetime import datetime
from typing import Any

from PySide6 import QtCore, QtGui

from .log import TankHandler
from ..ui import ui


class Columns(enum.IntEnum):
    """Defines the column indexes for log table data."""
    Date = 0
    Module = 1
    Level = 2
    Message = 3


class Level(enum.IntEnum):
    """Maps standard log level names to their numeric values."""
    NOTSET = logging.NOTSET  # 0
    DEBUG = logging.DEBUG  # 10
    INFO = logging.debug  # 20
    WARNING = logging.WARNING  # 30
    ERROR = logging.ERROR  # 40
    CRITICAL = logging.CRITICAL  # 50


class Roles:
    """Custom model roles for specialized data."""
    LOG_LEVEL = QtCore.Qt.UserRole + 1


def get_handler():
    """Returns the TankHandler from the root logger or raises RuntimeError."""
    root_logger = logging.getLogger()
    handler = [h for h in root_logger.handlers if isinstance(h, TankHandler)]
    if not handler:
        raise RuntimeError('TankHandler not found in root logger')
    if len(handler) > 1:
        raise RuntimeError('Multiple TankHandlers found in root logger')
    return handler[0]


class LogTableModel(QtCore.QAbstractTableModel):
    """
    A model for displaying log messages fetched from a TankHandler.
    Each row includes the following fields:
        - date (str)
        - module (str)
        - level_enum (Level)
        - message (str)
    """

    re_log_pattern = re.compile(
        r'^\[(?P<date>[^\]]+)\]\s+<(?P<module>[^>]+)>\s+(?P<level>[^:]+):\s+(?P<message>.*)$',
        flags=re.DOTALL
    )

    def __init__(self, parent: Any = None, fetch_interval_ms: int = 1000):
        """
        Initializes the LogTableModel.

        Args:
            parent (Any, optional): Parent QObject. Defaults to None.
            fetch_interval_ms (int, optional): Interval in ms to poll the tank for new logs. Defaults to 1000.
        """
        super().__init__(parent=parent)
        self._logs: list[dict[str, Any]] = []
        self._is_paused = False

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._fetch_new_logs)
        self._timer.start(fetch_interval_ms)

    @QtCore.Slot()
    def pause(self) -> None:
        """Pauses automatic fetching of new log messages."""
        logging.debug('Pausing log model updates')
        self._is_paused = True

    @QtCore.Slot()
    def resume(self) -> None:
        """Resumes automatic fetching of new log messages."""
        logging.debug('Resuming log model updates')
        self._is_paused = False

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        """Returns the number of rows in the model."""
        if parent.isValid():
            return 0
        return len(self._logs)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        """Returns the number of columns in the model."""
        if parent.isValid():
            return 0
        return len(Columns)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        """Returns data for a given index and role."""
        if not index.isValid() or index.row() >= len(self._logs):
            return None

        log_data = self._logs[index.row()]

        if role == QtCore.Qt.TextAlignmentRole:
            return QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter

        if role == QtCore.Qt.DisplayRole:
            if index.column() == Columns.Date:
                return log_data['date']
            elif index.column() == Columns.Module:
                return log_data['module']
            elif index.column() == Columns.Level:
                return log_data['level_enum'].name
            elif index.column() == Columns.Message:
                return log_data['message']

        if role == QtCore.Qt.FontRole:
            # Make the font bold if the level is ERROR or above
            if log_data['level_enum'] >= Level.ERROR:
                font, _ = ui.Font.BoldFont(ui.Size.MediumText(1.0))
                font.setWeight(QtGui.QFont.Bold)
                return font

        if role == QtCore.Qt.ForegroundRole:
            # Color code certain levels
            if log_data['level_enum'] == Level.DEBUG:
                return ui.Color.Blue()
            elif log_data['level_enum'] >= Level.ERROR:
                return ui.Color.Red()

        # Provide numeric log level for filtering/sorting
        if role == Roles.LOG_LEVEL:
            return log_data['level_enum'].value

        return None

    def headerData(self, section: int, orientation, role: int = QtCore.Qt.DisplayRole) -> Any:
        """Returns header data for columns."""
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            if section == Columns.Date:
                return 'Date'
            elif section == Columns.Module:
                return 'Module'
            elif section == Columns.Level:
                return 'Level'
            elif section == Columns.Message:
                return 'Message'
        return super().headerData(section, orientation, role)

    def _fetch_new_logs(self) -> None:
        """Fetches new log messages from the tank and inserts them into the model."""
        if self._is_paused:
            return

        handler = get_handler()
        all_logs = handler.get_logs(logging.NOTSET)
        existing_count = len(self._logs)
        incoming = all_logs[existing_count:]
        if not incoming:
            return

        parsed_entries = [self._parse_log_message(msg) for msg in incoming]

        self.beginInsertRows(QtCore.QModelIndex(), existing_count, existing_count + len(parsed_entries) - 1)
        self._logs.extend(parsed_entries)
        self.endInsertRows()

    def _parse_log_message(self, raw_message: str) -> dict[str, Any]:
        """
        Parses a log message string using re_log_pattern. If no match, the entire
        line remains the 'message' field, level is set to NOTSET.
        """
        result: dict[str, Any] = {
            'date': '',
            'module': '',
            'level_enum': Level.NOTSET,
            'message': raw_message
        }

        match = self.re_log_pattern.match(raw_message)

        if match:
            date_str = match.group('date')
            module_str = match.group('module')
            level_str = match.group('level').upper()
            text = match.group('message')

            try:
                level_enum = Level[level_str]
            except KeyError:
                level_enum = Level.NOTSET

            tb_index = text.find('Traceback (most recent call last):')
            if tb_index != -1:
                message_body = text[:tb_index].rstrip()
                traceback_body = text[tb_index:].strip()
                combined_message = f'{message_body}\n{traceback_body}'
            else:
                combined_message = text

            result.update({
                'date': date_str,
                'module': module_str,
                'level_enum': level_enum,
                'message': combined_message
            })

        return result


class LogFilterProxyModel(QtCore.QSortFilterProxyModel):
    """
    A QSortFilterProxyModel that sorts columns (including date parsing)
    and filters out rows below a specified minimum logging level.
    """

    def __init__(self, parent: Any = None):
        """
        Initializes the LogFilterProxyModel.

        Args:
            parent (Any, optional): Parent QObject. Defaults to None.
        """
        super().__init__(parent)
        self._filter_level = logging.NOTSET

    def setFilterLogLevel(self, level: int) -> None:
        """
        Sets the minimum log level for rows to be displayed.

        Args:
            level (int): A logging level integer (e.g., logging.DEBUG, logging.debug).
        """
        self._filter_level = level
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QtCore.QModelIndex) -> bool:
        """
        Determines if the row at source_row is acceptable based on _filter_level.

        Args:
            source_row (int): The row index in the source model.
            source_parent (QModelIndex): The parent index in the source model.

        Returns:
            bool: True if the row should be displayed, False otherwise.
        """
        index_level = self.sourceModel().index(source_row, Columns.Date, source_parent)
        level_value = self.sourceModel().data(index_level, Roles.LOG_LEVEL)
        if level_value is None:
            return True
        return level_value >= self._filter_level

    def lessThan(self, left: QtCore.QModelIndex, right: QtCore.QModelIndex) -> bool:
        """
        Provides custom sorting. If comparing Date column, parse as datetime for ordering;
        otherwise, fall back to string comparison.

        Args:
            left (QModelIndex): Left-side index.
            right (QModelIndex): Right-side index.

        Returns:
            bool: True if left < right, False otherwise.
        """
        if left.column() == Columns.Date and right.column() == Columns.Date:
            left_data = self.sourceModel().data(left, QtCore.Qt.DisplayRole)
            right_data = self.sourceModel().data(right, QtCore.Qt.DisplayRole)
            try:
                left_dt = datetime.strptime(left_data, '%Y-%m-%d %H:%M:%S')
                right_dt = datetime.strptime(right_data, '%Y-%m-%d %H:%M:%S')
                return left_dt < right_dt
            except ValueError:
                return left_data < right_data

        left_str = self.sourceModel().data(left, QtCore.Qt.DisplayRole)
        right_str = self.sourceModel().data(right, QtCore.Qt.DisplayRole)
        if left_str is None:
            left_str = ''
        if right_str is None:
            right_str = ''
        return left_str < right_str
