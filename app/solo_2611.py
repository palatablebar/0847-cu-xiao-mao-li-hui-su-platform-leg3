"""Task-identifier compatibility alias."""

from app.presale.policy import *  # noqa: F401,F403
from app.presale.service import PresaleService, PresaleStore

Solo2611Service = PresaleService

__all__ = ["PresaleService", "PresaleStore", "Solo2611Service"]
