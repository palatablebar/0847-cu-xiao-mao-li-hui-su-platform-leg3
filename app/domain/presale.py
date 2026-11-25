from app.domain.resale import *  # noqa: F401,F403
from app.presale import policy as _policy
from app.presale.service import PresaleService

PresaleEligibilityService = PresaleService


def __getattr__(name: str):
    if name.startswith("_"):
        raise AttributeError(name)
    if name[0].isupper() and ("Service" in name or "Manager" in name or "Board" in name):
        return PresaleService
    if name[0].isupper() and ("Store" in name or "Repository" in name or "Ledger" in name):
        from app.presale.store import PresaleStore
        return PresaleStore
    return getattr(_policy, name)
