"""
Smoke tests for UI components of ExpenseTracker.
Verifies each UI class can be instantiated without error, and any QActions on widgets can be triggered.
"""
import unittest

from PySide6 import QtGui, QtWidgets

from ExpenseTracker.ui import ui
from tests.base import BaseTestCase


class UIBaseTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()

        if not QtWidgets.QApplication.instance():
            self.app = QtWidgets.QApplication([])
        ui.apply_theme()

    def tearDown(self):
        super().tearDown()

@unittest.skip("Skipping UI tests")
class TestBaseChart(UIBaseTestCase):
    def test_ChartSlice_and_ChartModel_init(self):
        from ExpenseTracker.ui.basechart import ChartSlice, ChartModel
        color = QtGui.QColor(0, 0, 0)
        sl = ChartSlice('cat', '$0.00', 0.0, color, 'icon', 0, 1)
        self.assertEqual(sl.category, 'cat')
        model = ChartModel()
        self.assertIsNotNone(model)

    def test_BaseChartView_init_and_actions(self):
        from ExpenseTracker.ui.basechart import BaseChartView
        view = BaseChartView(None)
        for action in view.actions():
            # trigger any actions to ensure they do not error
            action.trigger()

@unittest.skip("Skipping UI tests")
class TestDockableWidget(UIBaseTestCase):
    def test_DockableWidget_init(self):
        from ExpenseTracker.ui.dockable_widget import DockableWidget
        dock = DockableWidget('title', None)
        self.assertIsNotNone(dock)

@unittest.skip("Skipping UI tests")
class TestMainUI(UIBaseTestCase):
    def test_TitleLabel_init(self):
        from ExpenseTracker.ui.main import TitleLabel
        self.assertIsNotNone(TitleLabel(None))

    def test_TitleBar_init(self):
        from ExpenseTracker.ui.main import TitleBar
        self.assertIsNotNone(TitleBar(None))

    def test_ResizableMainWidget_init(self):
        from ExpenseTracker.ui.main import ResizableMainWidget
        self.assertIsNotNone(ResizableMainWidget(None))

    def test_MainWindow_init(self):
        from ExpenseTracker.ui.main import MainWindow
        self.assertIsNotNone(MainWindow(None))


@unittest.skip("Skipping UI tests")
class TestStatusIndicator(UIBaseTestCase):
    def test_StatusIndicator_init(self):
        from ExpenseTracker.ui.main import StatusIndicator
        self.assertIsNotNone(StatusIndicator(None))


@unittest.skip("Skipping UI tests")
class TestPaletteComponents(UIBaseTestCase):
    def test_palette_models_and_views(self):
        from ExpenseTracker.ui.palette import (
            PaletteModel, PaletteItemDelegate, PaletteView,
            IconModel, IconItemDelegate, IconPickerView,
            CategoryPreview, CategoryIconColorEditorDialog,
        )
        PaletteModel()
        PaletteItemDelegate(None)
        PaletteView(None)
        IconModel()
        IconItemDelegate(None)
        IconPickerView(None)
        CategoryPreview(None)
        CategoryIconColorEditorDialog('cat', None)


@unittest.skip("Skipping UI tests")
class TestUIStyling(UIBaseTestCase):
    def test_FontDatabase_init(self):
        from ExpenseTracker.ui.ui import FontDatabase
        self.assertIsNotNone(FontDatabase())


@unittest.skip("Skipping UI tests")
class TestYearMonthWidgets(UIBaseTestCase):
    def test_YearMonthPopup_init(self):
        from ExpenseTracker.ui.yearmonth import YearMonthPopup
        popup = YearMonthPopup(None, initial_year=2021, min_date='2021-01', max_date='2021-12')
        self.assertIsNotNone(popup)

    def test_YearMonthSelector_init(self):
        from ExpenseTracker.ui.yearmonth import YearMonthSelector
        self.assertIsNotNone(YearMonthSelector(None))

    def test_RangeSelectorBar_init(self):
        from ExpenseTracker.ui.yearmonth import RangeSelectorBar
        self.assertIsNotNone(RangeSelectorBar(None))


@unittest.skip("Skipping UI tests")
class TestLogView(UIBaseTestCase):
    def test_LogTableView_init(self):
        from ExpenseTracker.log.view import LogTableView
        self.assertIsNotNone(LogTableView(None))

    def test_LogDockWidget_init(self):
        from ExpenseTracker.log.view import LogDockWidget
        self.assertIsNotNone(LogDockWidget(None))


@unittest.skip("Skipping UI tests")
class TestDataView(UIBaseTestCase):
    def test_DoughnutView_and_Dock_init(self):
        from ExpenseTracker.data.view.doughnut import DoughnutView, DoughnutDockWidget
        self.assertIsNotNone(DoughnutView(None))
        self.assertIsNotNone(DoughnutDockWidget(None))

    def test_PieChartView_and_Dock_init(self):
        from ExpenseTracker.data.view.piechart import PieChartView, PieChartDockWidget
        self.assertIsNotNone(PieChartView(None))
        self.assertIsNotNone(PieChartDockWidget(None))

    def test_ExpenseView_and_Dock_init(self):
        from ExpenseTracker.data.view.expense import ExpenseView, ExpenseDockWidget
        self.assertIsNotNone(ExpenseView(None))
        self.assertIsNotNone(ExpenseDockWidget(None))

    def test_TrendGraph_and_Dock_init(self):
        from ExpenseTracker.data.view.trends import TrendGraph, TrendDockWidget
        self.assertIsNotNone(TrendGraph(None))
        self.assertIsNotNone(TrendDockWidget(None))

    def test_TransactionsView_and_Widget_init(self):
        from ExpenseTracker.data.view.transaction import TransactionsView, TransactionsWidget
        self.assertIsNotNone(TransactionsView(None))
        self.assertIsNotNone(TransactionsWidget(None))


@unittest.skip("Skipping UI tests")
class TestSettingsEditors(UIBaseTestCase):
    def test_CategoryEditor_and_delegate_init(self):
        from ExpenseTracker.settings.editors.category_editor import CategoryEditor, CategoryItemDelegate
        self.assertIsNotNone(CategoryEditor(None))
        self.assertIsNotNone(CategoryItemDelegate(None))

    def test_ClientEditor_and_preview_and_dialog_init(self):
        from ExpenseTracker.settings.editors.client_editor import ClientEditor, JsonPreviewWidget, ImportSecretDialog
        self.assertIsNotNone(ClientEditor(None))
        self.assertIsNotNone(JsonPreviewWidget(None))
        self.assertIsNotNone(ImportSecretDialog(None))

    def test_DataMappingEditor_and_delegate_init(self):
        from ExpenseTracker.settings.editors.data_mapping_editor import DataMappingEditor, DataMappingDelegate
        self.assertIsNotNone(DataMappingEditor(None))
        self.assertIsNotNone(DataMappingDelegate(None))

    def test_HeaderEditor_and_delegate_init(self):
        from ExpenseTracker.settings.editors.header_editor import HeaderEditor, HeaderItemDelegate
        self.assertIsNotNone(HeaderEditor(None))
        self.assertIsNotNone(HeaderItemDelegate(None))

    def test_MetadataEditors_init(self):
        from ExpenseTracker.settings.editors.metadata_editor import (
            BaseComboBoxEditor, LocaleEditor, EnumEditor,
            SummaryModeEditor, ThemeEditor, BooleanEditor
        )
        self.assertIsNotNone(BaseComboBoxEditor(None))
        self.assertIsNotNone(LocaleEditor(None))
        self.assertIsNotNone(EnumEditor(None))
        self.assertIsNotNone(SummaryModeEditor(None))
        self.assertIsNotNone(ThemeEditor(None))
        self.assertIsNotNone(BooleanEditor(None))

    def test_SpreadsheetEditor_init(self):
        from ExpenseTracker.settings.editors.spreadsheet_editor import SpreadsheetEditor
        self.assertIsNotNone(SpreadsheetEditor(None))

    def test_settings_views_init(self):
        from ExpenseTracker.settings.editors.views import TableView, TreeView, ListView
        self.assertIsNotNone(TableView(None))
        self.assertIsNotNone(TreeView(None))
        self.assertIsNotNone(ListView(None))


@unittest.skip("Skipping UI tests")
class TestPresetsView(UIBaseTestCase):
    def test_PresetsDockWidget_init(self):
        from ExpenseTracker.settings.presets.view import PresetsDockWidget
        self.assertIsNotNone(PresetsDockWidget(None))


@unittest.skip("Skipping UI tests")
class TestSettingsView(UIBaseTestCase):
    def test_SettingsDockWidget_init(self):
        from ExpenseTracker.settings.settings import SettingsDockWidget
        self.assertIsNotNone(SettingsDockWidget(None))


if __name__ == '__main__':
    unittest.main()
