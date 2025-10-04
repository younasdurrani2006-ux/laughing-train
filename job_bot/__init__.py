"""Job application automation bot package."""

from .bot import JobApplicationBot
from .config import AutomationConfig, load_config

__all__ = ["JobApplicationBot", "AutomationConfig", "load_config"]
