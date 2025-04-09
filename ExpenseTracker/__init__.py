# Setup up logging before importing any other modules
from .log.log import setup_logging
setup_logging()

from .ui.actions import signals
from .settings.lib import settings
