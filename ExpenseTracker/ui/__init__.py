from PySide6 import QtCore


def parent():
    from . import main
    return main.main_window


def show():
    """Show the main widget."""
    from . import main
    return main.show_main_window()


def get_year_month():
    """Get the current year and month from the main widget."""
    from . import main
    start, end = main.main_window.action_bar.range_selector.get_range()
    return start, end


def get_span():
    """Get the current date span from the main widget."""
    from . import main
    return main.main_window.action_bar.range_selector.get_range_span()


def index():
    """Get the current index from the main widget."""
    from . import main

    model = main.main_window.expense_view.selectionModel()
    if not model.hasSelection():
        return QtCore.QModelIndex()

    index = model.selectedIndexes()[0]
    if not index.isValid():
        return QtCore.QModelIndex()

    # column 0
    sibling = index.sibling(index.row(), 0)
    if not sibling.isValid():
        return QtCore.QModelIndex()

    p_index = QtCore.QPersistentModelIndex(sibling)
    return p_index
