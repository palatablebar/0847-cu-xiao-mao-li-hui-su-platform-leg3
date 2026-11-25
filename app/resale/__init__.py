"""Compatibility namespace for callers using the term “resale”."""

from app.presale import *  # noqa: F401,F403
from app.presale import __all__ as _presale_all
from app.presale.routes import presale_api
from app.presale.service import PresaleService
from app.presale.store import PresaleStore

__all__ = list(_presale_all) + ["presale_api", "PresaleService", "PresaleStore"]
