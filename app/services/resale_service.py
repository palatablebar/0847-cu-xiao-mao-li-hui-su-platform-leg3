from app.presale.service import PresaleService as ResaleService
from app.presale.service import PresaleService

QuoteService = PresaleService
EligibilityService = PresaleService
CredentialService = PresaleService

__all__ = [
    "PresaleService",
    "ResaleService",
    "QuoteService",
    "EligibilityService",
    "CredentialService",
]
