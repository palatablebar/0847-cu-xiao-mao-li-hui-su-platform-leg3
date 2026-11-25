"""Promotion presale/resale eligibility bounded context."""

from app.presale.policy import (
    QuoteValidationError,
    actual_is_within_range,
    can_continue_sale,
    can_resell,
    evaluate_actual,
    evaluate_quote,
    entire_range_meets_floor,
    is_eligible,
    quote_fingerprint,
    shipment_margin,
)
from app.presale.service import PresaleService
from app.presale.store import PresaleStore

__all__ = [
    "PresaleService",
    "PresaleStore",
    "QuoteValidationError",
    "actual_is_within_range",
    "can_continue_sale",
    "can_resell",
    "entire_range_meets_floor",
    "evaluate_actual",
    "evaluate_quote",
    "is_eligible",
    "quote_fingerprint",
    "shipment_margin",
]


def __getattr__(name: str):
    if name.startswith("_"):
        raise AttributeError(name)
    from app.presale import policy as policy_module
    from app.presale import service as service_module
    if hasattr(service_module, name):
        return getattr(service_module, name)
    return getattr(policy_module, name)
