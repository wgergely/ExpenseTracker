def parent():
    from . import main
    return main.main_widget

def show():
    """Show the main widget."""
    from . import main
    return main.show_main_widget()
