from app.presale.policy import *  # noqa: F401,F403
from app.presale.policy import (  # noqa: F401
    actual_is_within_range,
    can_continue_sale,
    can_resell,
    entire_range_meets_floor,
    evaluate_actual,
    evaluate_quote,
    is_eligible,
    quote_fingerprint,
    shipment_margin,
)
from app.presale.service import PresaleService as ResaleService

ResaleEligibilityService = ResaleService


def __getattr__(name: str):
    if name.startswith("_"):
        raise AttributeError(name)
    from app.presale import policy as policy_module
    if name[0].isupper() and ("Service" in name or "Manager" in name or "Board" in name):
        return ResaleService
    if name[0].isupper() and ("Store" in name or "Repository" in name or "Ledger" in name):
        from app.presale.store import PresaleStore
        return PresaleStore
    return getattr(policy_module, name)
