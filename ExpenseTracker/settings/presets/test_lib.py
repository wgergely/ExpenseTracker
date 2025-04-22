import shutil
import tempfile
import unittest
from pathlib import Path


class TestPresetItem(unittest.TestCase):
    def setUp(self):
        """
        Backup any existing /tmp/ExpenseTracker, then remove it so each test has a clean slate.
        """
        self.temp_dir = Path(tempfile.gettempdir())
        self.expense_tracker_dir = self.temp_dir / 'ExpenseTracker'
        self.backup_dir = self.temp_dir / 'ExpenseTracker_backup'

        if self.expense_tracker_dir.exists():
            if self.backup_dir.exists():
                shutil.rmtree(self.backup_dir)
            shutil.move(str(self.expense_tracker_dir), str(self.backup_dir))

    def tearDown(self):
        """
        Remove test's ExpenseTracker dir and restore any backup.
        """
        if self.expense_tracker_dir.exists():
            shutil.rmtree(self.expense_tracker_dir)

        if self.backup_dir.exists():
            shutil.move(str(self.backup_dir), str(self.expense_tracker_dir))


class TestPresetAPI(unittest.TestCase):
    def setUp(self):
        """
        Backup any existing /tmp/ExpenseTracker, then remove it so each test has a clean slate.
        """
        self.temp_dir = Path(tempfile.gettempdir())
        self.expense_tracker_dir = self.temp_dir / 'ExpenseTracker'
        self.backup_dir = self.temp_dir / 'ExpenseTracker_backup'

        if self.expense_tracker_dir.exists():
            if self.backup_dir.exists():
                shutil.rmtree(self.backup_dir)
            shutil.move(str(self.expense_tracker_dir), str(self.backup_dir))

    def tearDown(self):
        """
        Remove test's ExpenseTracker dir and restore any backup.
        """
        if self.expense_tracker_dir.exists():
            shutil.rmtree(self.expense_tracker_dir)

        if self.backup_dir.exists():
            shutil.move(str(self.backup_dir), str(self.expense_tracker_dir))
