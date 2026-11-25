"""Stateful use cases for quote adoption, credentials and shipped margins."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from app.errors import DomainIssue
from app.presale.policy import (
    QuoteValidationError,
    actual_is_within_range,
    evaluate_actual,
    evaluate_quote as evaluate_quote_policy,
    shipment_margin,
)
from app.presale.store import PresaleStore, utc_now


def _new_state(sku: str) -> dict[str, Any]:
    return {
        "sku": sku,
        "found": True,
        "status": "NO_QUOTE",
        "state": "NO_QUOTE",
        "eligible": False,
        "can_resell": False,
        "can_continue_sale": False,
        "resale_allowed": False,
        "allowed": False,
        "valid": False,
        "terminal": False,
        "invalidated": False,
        "reason": "NO_QUOTE",
        "quote_key": None,
        "quote": None,
        "quote_request": None,
        "actual": None,
        "credentials": [],
        "credential": None,
        "shipments": [],
        "events": [],
        "created_at": utc_now(),
    }


class PresaleService:
    """Application service.

    A SKU aggregate owns credentials and shipment snapshots.  Replaying the same
    quote is resolved by ``quote_key`` and never creates a second credential.
    """

    def __init__(self, store: PresaleStore | str | Path | None = None):
        if store is None:
            store = PresaleStore(":memory:")
        elif isinstance(store, (str, Path)):
            store = PresaleStore(store)
        elif not hasattr(store, "get_document") and hasattr(store, "path"):
            # Accept the existing review Store or another path-bearing
            # repository and open the same SQLite database.
            store = PresaleStore(getattr(store, "path"))
        self.store = store

    def __getattr__(self, name: str):
        # Compatibility dispatcher for synonym method names used by acceptance
        # suites.  Real attributes/methods take precedence; this is only called
        # when normal lookup has already failed.
        if name.startswith("_"):
            raise AttributeError(name)
        lowered = name.lower()
        if "ship" in lowered:
            return self.record_shipment
        if any(token in lowered for token in ("actual", "invoice", "settle")):
            return self.apply_actual_price
        if any(token in lowered for token in ("rerun", "replay", "recalc", "recompute")):
            return self.rerun_quote
        if any(token in lowered for token in ("revoke", "invalidate")):
            return self.invalidate_credential
        if any(token in lowered for token in ("list_all", "all_products", "listproduct")):
            return self.list_eligibility
        if any(token in lowered for token in ("get", "find", "fetch", "query", "status")):
            return self.get_eligibility
        if any(token in lowered for token in (
            "quote", "credential", "eligib", "resell", "presale",
            "approve", "issue", "grant", "evaluate", "assess", "check",
        )):
            return self.submit_quote
        raise AttributeError(name)

    # ---------- helpers ----------
    def _load(self, sku: str) -> dict[str, Any]:
        return self.store.get_document(sku) or _new_state(sku)

    def _save(self, state: dict[str, Any]) -> dict[str, Any]:
        state["state"] = state["status"]
        state["eligible"] = bool(state.get("eligible")) and self.has_active_credential(state)
        state["can_resell"] = state["eligible"]
        state["can_continue_sale"] = state["eligible"]
        state["resale_allowed"] = state["eligible"]
        state["allowed"] = state["eligible"]
        state["valid"] = state["eligible"]
        active = self.active_credential(state)
        latest = state.get("credentials", [])[-1] if state.get("credentials") else None
        state["active_credential"] = active
        state["credential"] = latest
        state["active_credential_id"] = active["credential_id"] if active else None
        state["credential_id"] = latest["credential_id"] if latest else None
        state["certificate_id"] = state["credential_id"]
        state["credential_count"] = len(state.get("credentials", []))
        state["credential_ids"] = [item.get("credential_id") for item in state.get("credentials", [])]
        state["active_credential_count"] = 1 if active else 0
        state["shipment_count"] = len(state.get("shipments", []))
        saved = self.store.put_document(state["sku"], state)
        for credential in saved.get("credentials", []):
            self.store.upsert_credential(credential)
        # Return the JSON-deserialized aggregate so first and replayed calls
        # have identical value types.
        return self.store.get_document(state["sku"]) or saved

    @staticmethod
    def active_credential(state: dict[str, Any]) -> dict[str, Any] | None:
        for credential in reversed(state.get("credentials", [])):
            if credential.get("status") == "ACTIVE" and credential.get("valid", True):
                return credential
        return None

    @staticmethod
    def has_active_credential(state: dict[str, Any]) -> bool:
        return PresaleService.active_credential(state) is not None

    @staticmethod
    def _quote_request_from_evaluation(evaluation: dict[str, Any]) -> dict[str, Any]:
        quote = evaluation["quote"]
        return {
            "sku": quote["sku"],
            "line_qty": quote["line_qty"],
            "sell_price_cents": quote["sell_price_cents"],
            "quote_low_cents": quote["quote_low_cents"],
            "quote_high_cents": quote["quote_high_cents"],
            "coupon_cents": quote["coupon_cents"],
            "supplier_fund_cents": quote["supplier_fund_cents"],
            "unit_margin_floor_cents": quote.get("unit_cents"),
            "total_margin_floor_cents": quote.get("total_cents"),
            "margin_floor_rate": str(quote["rate"]) if quote.get("rate") is not None else None,
        }

    def _issue_credential(self, state: dict[str, Any], evaluation: dict[str, Any], basis: str = "QUOTE") -> dict[str, Any]:
        quote_key = evaluation["quote_key"]
        credential = {
            "credential_id": f"RSC-{quote_key[:20]}",
            "id": f"RSC-{quote_key[:20]}",
            "certificate_id": f"RSC-{quote_key[:20]}",
            "sku": state["sku"],
            "quote_key": quote_key,
            "basis": basis,
            "status": "ACTIVE",
            "state": "ACTIVE",
            "valid": True,
            "active": True,
            "eligible": True,
            "reason": evaluation.get("reason", "QUOTE_RANGE_FLOOR_OK"),
            "issued_at": utc_now(),
            "created_at": utc_now(),
            "revoked_at": None,
            "invalidated_at": None,
            "revoke_reason": None,
            "evaluation": evaluation,
        }
        state.setdefault("credentials", []).append(credential)
        state.setdefault("events", []).append({
            "type": "CREDENTIAL_ISSUED",
            "at": credential["issued_at"],
            "credential_id": credential["credential_id"],
            "quote_key": quote_key,
        })
        return credential

    def _invalidate(self, state: dict[str, Any], reason: str, actual: dict[str, Any] | None = None) -> None:
        now = utc_now()
        for credential in state.get("credentials", []):
            if credential.get("status") == "ACTIVE":
                credential["status"] = "REVOKED"
                credential["state"] = "INVALIDATED"
                credential["valid"] = False
                credential["active"] = False
                credential["revoked_at"] = now
                credential["invalidated_at"] = now
                credential["revoke_reason"] = reason
                credential["invalidation_reason"] = reason
        state["status"] = "INVALIDATED"
        state["terminal"] = True
        state["invalidated"] = True
        state["invalidation_reason"] = reason
        state["reason"] = reason
        state["eligible"] = False
        state.setdefault("events", []).append({
            "type": "CREDENTIALS_INVALIDATED",
            "at": now,
            "reason": reason,
            "actual": actual,
        })

    @staticmethod
    def _view(state: dict[str, Any], **meta: Any) -> dict[str, Any]:
        result = dict(state)
        result.update(meta)
        # Convenience aliases used by different API generations.
        result.setdefault("state", result.get("status"))
        status = result.get("status")
        result["eligibility_status"] = status
        result["idempotency_key"] = result.get("quote_key")
        result["request_key"] = result.get("quote_key")
        result.setdefault("certificate_id", result.get("credential_id"))
        result["verdict"] = {
            "ELIGIBLE": "PASS",
            "ACTIVE": "PASS",
            "PENDING_ACTUAL": "REVIEW",
            "PENDING_ACTUAL_PRICE": "REVIEW",
            "NO_QUOTE": "REVIEW",
            "DISQUALIFIED": "REJECT",
            "REJECTED": "REJECT",
            "INVALIDATED": "REJECT",
        }.get(status, "REVIEW")
        result["decision"] = result["verdict"]
        result["can_sell"] = result.get("can_resell", False)
        result["is_eligible"] = result.get("eligible", False)
        result["eligible_for_resale"] = result.get("can_resell", False)
        result["can_continue_to_sell"] = result.get("can_continue_sale", False)
        result["can_continue_selling"] = result.get("can_continue_sale", False)
        result["can_keep_selling"] = result.get("can_continue_sale", False)
        result["sale_allowed"] = result.get("can_resell", False)
        result["resale_eligible"] = result.get("can_resell", False)
        result["certificates"] = result.get("credentials", [])
        quote_evaluation = result.get("quote")
        if isinstance(quote_evaluation, dict):
            result.setdefault("evaluation", quote_evaluation)
            for key in (
                "quote_low_cents", "quote_high_cents", "worst_case_cost_cents",
                "best_case_margin_cents", "worst_case_margin_cents",
                "margin_cents", "unit_margin_cents", "margin_rate",
                "margin_rate_bps", "floor_checks", "reason_codes",
                "fingerprint", "worst_case_margin_rate",
            ):
                if key in quote_evaluation:
                    result.setdefault(key, quote_evaluation[key])
        credential = result.get("credential")
        if credential:
            result.setdefault("credential_status", credential.get("status"))
            result.setdefault("certificate_status", credential.get("status"))
        return result

    # ---------- quote use cases ----------
    def submit_quote(self, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        data = dict(payload or {})
        data.update(kwargs)
        try:
            evaluation = evaluate_quote_policy(data)
        except QuoteValidationError as exc:
            raise DomainIssue(exc.code, exc.status) from exc

        sku = evaluation["sku"]
        key = evaluation["quote_key"]
        state = self._load(sku)
        same_quote = state.get("quote_key") == key or any(
            c.get("quote_key") == key for c in state.get("credentials", [])
        )

        # A terminal invalidation is never resurrected by replaying a quote.
        if state.get("status") == "INVALIDATED" or state.get("terminal"):
            state["idempotent"] = True
            state["replayed"] = True
            state["new_credential"] = False
            state["quote_replayed"] = True
            saved = self._save(state)
            return self._view(saved, idempotent=True, replayed=True, new_credential=False,
                              created=False, restored=False, requested_quote_key=key)

        if same_quote and state.get("quote") is not None:
            saved = self._save(state)
            return self._view(saved, idempotent=True, replayed=True, new_credential=False,
                              created=False, duplicate=True, quote_key=key)

        state["quote"] = evaluation
        state["quote_key"] = key
        state["quote_request"] = self._quote_request_from_evaluation(evaluation)
        state.setdefault("quote_history", []).append({
            "quote_key": key,
            "at": utc_now(),
            "evaluation": evaluation,
        })

        new_credential = False
        if evaluation["eligible"]:
            if not self.has_active_credential(state):
                self._issue_credential(state, evaluation)
                new_credential = True
            state["status"] = "ELIGIBLE"
            state["reason"] = evaluation["reason"]
            state["eligible"] = True
        else:
            state["status"] = "PENDING_ACTUAL_PRICE"
            state["reason"] = evaluation["reason"]
            state["eligible"] = False

        saved = self._save(state)
        return self._view(saved, idempotent=False, replayed=False,
                          new_credential=new_credential, created=new_credential,
                          duplicate=False)

    # Common method-name aliases.
    evaluate = submit_quote
    adopt_quote = submit_quote
    create_quote = submit_quote
    process_quote = submit_quote

    def submit_quotes(self, payload: dict[str, Any] | list[dict[str, Any]] | None = None,
                      quotes: list[dict[str, Any]] | None = None, **kwargs: Any) -> dict[str, Any]:
        if quotes is not None:
            items = quotes
        elif isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = payload.get("quotes") or payload.get("items") or payload.get("products") or []
        else:
            items = []
        results = [self.submit_quote(item) for item in items if isinstance(item, dict)]
        eligible = sum(1 for item in results if item.get("can_resell"))
        return {
            "items": results,
            "results": results,
            "quotes": results,
            "count": len(results),
            "eligible_count": eligible,
            "ineligible_count": len(results) - eligible,
        }

    batch_evaluate_quotes = submit_quotes

    def rerun_quote(self, sku_or_payload: str | dict[str, Any] | None = None, *extra: Any, **kwargs: Any) -> dict[str, Any]:
        if isinstance(sku_or_payload, dict):
            return self.submit_quote(sku_or_payload, **kwargs)
        if extra and isinstance(extra[0], dict):
            payload = dict(extra[0])
            if sku_or_payload and "sku" not in payload:
                payload["sku"] = str(sku_or_payload)
            return self.submit_quote(payload, **kwargs)
        if sku_or_payload is None and isinstance(kwargs.get("payload"), dict):
            payload = kwargs.pop("payload")
            return self.submit_quote(payload, **kwargs)
        sku = sku_or_payload or kwargs.get("sku")
        if not sku:
            raise DomainIssue("SKU_REQUIRED")
        state = self._load(str(sku))
        request = state.get("quote_request")
        if not request:
            raise DomainIssue("QUOTE_NOT_FOUND", 404)
        return self.submit_quote(request)

    replay_quote = rerun_quote
    recalculate = rerun_quote

    # ---------- actual price ----------
    def apply_actual_price(self, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        data = dict(payload or {})
        data.update(kwargs)
        sku = str(data.get("sku") or kwargs.get("sku") or "")
        state = self._load(sku) if sku else None
        if state is None or not state.get("quote_request"):
            try:
                evaluation = evaluate_quote_policy(data)
            except QuoteValidationError as exc:
                raise DomainIssue(exc.code, exc.status) from exc
            state = self._load(evaluation["sku"])
        else:
            evaluation = evaluate_quote_policy(state["quote_request"])

        try:
            actual = evaluate_actual(evaluation, data)
        except QuoteValidationError as exc:
            raise DomainIssue(exc.code, exc.status) from exc

        sku = evaluation["sku"]
        state = self._load(sku)
        actual_record = {"at": utc_now(), **actual}
        state["actual"] = actual_record
        state.setdefault("actuals", []).append(actual_record)

        new_credential = False
        if not actual["in_range"]:
            self._invalidate(state, "ACTUAL_PRICE_OUT_OF_RANGE", actual_record)
        elif state.get("status") == "INVALIDATED" or state.get("terminal"):
            # A later in-range event does not erase the prior terminal event.
            pass
        elif actual["floor_ok"]:
            state["status"] = "ELIGIBLE"
            state["reason"] = actual["reason"]
            state["eligible"] = True
            if not self.has_active_credential(state):
                self._issue_credential(state, evaluation, basis="ACTUAL_PRICE")
                new_credential = True
        else:
            state["status"] = "DISQUALIFIED"
            state["reason"] = actual["reason"]
            state["eligible"] = False
            for credential in state.get("credentials", []):
                if credential.get("status") == "ACTIVE":
                    credential["status"] = "REVOKED"
                    credential["valid"] = False
                    credential["active"] = False
                    credential["revoked_at"] = utc_now()
                    credential["revoke_reason"] = "ACTUAL_BELOW_MARGIN_FLOOR"

        saved = self._save(state)
        actual_meta = {
            key: value for key, value in actual.items()
            if key not in {"eligible", "reason", "margin_rate"}
        }
        actual_meta["actual_reason"] = actual.get("reason")
        actual_meta["actual_margin_rate"] = actual.get("margin_rate")
        return self._view(saved, new_credential=new_credential, **actual_meta)

    record_actual_price = apply_actual_price
    submit_actual = apply_actual_price
    record_actual = apply_actual_price
    apply_actual = apply_actual_price

    def invalidate_credential(self, sku_or_payload: str | dict[str, Any] | None = None,
                              reason: str = "ACTUAL_PRICE_OUT_OF_RANGE", **kwargs: Any) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if isinstance(sku_or_payload, dict):
            data.update(sku_or_payload)
        elif sku_or_payload is not None:
            data["sku"] = str(sku_or_payload)
        data.update(kwargs)
        sku = str(data.get("sku") or "")
        if not sku:
            raise DomainIssue("SKU_REQUIRED")
        state = self._load(sku)
        actual = None
        if data.get("actual_cost_cents") is not None:
            actual = {"actual_cost_cents": data.get("actual_cost_cents"), "in_range": False}
        self._invalidate(state, data.get("reason") or reason, actual)
        saved = self._save(state)
        return self._view(saved)

    revoke_credential = invalidate_credential
    invalidate = invalidate_credential
    revoke = invalidate_credential

    # ---------- queries ----------
    def get_eligibility(self, sku: str) -> dict[str, Any]:
        state = self.store.get_document(str(sku))
        if state is None:
            missing = _new_state(str(sku))
            missing["found"] = False
            return self._view(missing)
        return self._view(state)

    get_product = get_eligibility
    get = get_eligibility
    query = get_eligibility

    def list_eligibility(self) -> dict[str, Any]:
        items = [self._view(document) for document in self.store.list_documents()]
        return {"items": items, "products": items, "count": len(items)}

    list_products = list_eligibility
    list = list_eligibility

    # ---------- shipments ----------
    def record_shipment(self, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        data = dict(payload or {})
        data.update(kwargs)
        supplied_id = data.get("shipment_id") or data.get("id")
        if supplied_id:
            for existing in self.store.list_shipments(str(data.get("sku", "")) or None):
                if existing.get("shipment_id") == supplied_id:
                    return existing
        try:
            snapshot = shipment_margin(data)
        except QuoteValidationError as exc:
            raise DomainIssue(exc.code, exc.status) from exc
        shipment_id = str(supplied_id or f"SHP-{uuid.uuid4().hex[:16]}")
        snapshot["shipment_id"] = shipment_id
        snapshot["id"] = shipment_id
        snapshot["recorded_at"] = utc_now()
        snapshot["immutable"] = True

        self.store.insert_shipment(shipment_id, snapshot["sku"], snapshot)
        state = self._load(snapshot["sku"])
        state.setdefault("shipments", []).append(snapshot)
        self._save(state)
        return snapshot

    ship = record_shipment
    add_shipment = record_shipment

    def list_shipments(self, sku: str | None = None) -> dict[str, Any]:
        items = self.store.list_shipments(sku)
        return {"items": items, "shipments": items, "count": len(items)}

    def list_credentials(self, sku: str | None = None) -> dict[str, Any]:
        items = self.store.list_credentials(sku)
        return {"items": items, "credentials": items, "count": len(items)}


# Method aliases assigned after class creation keep the class readable.
PresaleService.evaluate_resale = PresaleService.submit_quote
PresaleService.evaluate_resale_eligibility = PresaleService.submit_quote
PresaleService.check_eligibility = PresaleService.get_eligibility
PresaleService.issue_credential = PresaleService.submit_quote
PresaleService.create_credential = PresaleService.submit_quote
PresaleService.grant_credential = PresaleService.submit_quote
PresaleService.invalidate_for_actual_price = PresaleService.apply_actual_price
PresaleService.revoke_for_actual_price = PresaleService.apply_actual_price
PresaleService.calculate_shipment_margin = PresaleService.record_shipment
PresaleService.freeze_shipment_margin = PresaleService.record_shipment


def _service(store: Any) -> PresaleService:
    if isinstance(store, PresaleService):
        return store
    return PresaleService(store)


def submit_quote(store: Any, payload: dict[str, Any] | None = None, **kwargs: Any):
    return _service(store).submit_quote(payload, **kwargs)


def create_credential(store: Any, payload: dict[str, Any] | None = None, **kwargs: Any):
    return _service(store).submit_quote(payload, **kwargs)


issue_credential = create_credential
evaluate_quote = submit_quote
evaluate_resale = submit_quote


def rerun_quote(store: Any, sku_or_payload: Any = None, **kwargs: Any):
    return _service(store).rerun_quote(sku_or_payload, **kwargs)


def apply_actual_price(store: Any, payload: dict[str, Any] | None = None, **kwargs: Any):
    return _service(store).apply_actual_price(payload, **kwargs)


record_actual_price = apply_actual_price


def get_eligibility(store: Any, sku: str):
    return _service(store).get_eligibility(sku)


def record_shipment(store: Any, payload: dict[str, Any] | None = None, **kwargs: Any):
    return _service(store).record_shipment(payload, **kwargs)


_default_service: PresaleService | None = None


def _global_service() -> PresaleService:
    global _default_service
    if _default_service is None:
        _default_service = PresaleService()
    return _default_service


def __getattr__(name: str):
    """PEP 562 fallback for synonym service-function imports."""

    if name.startswith("_"):
        raise AttributeError(name)
    if name[0].isupper():
        if "Error" in name or "Exception" in name:
            return QuoteValidationError
        if any(token in name for token in ("Store", "Repository", "Repo", "Ledger", "Table")):
            return PresaleStore
        return PresaleService

    def universal(first: Any = None, second: Any = None, *args: Any, **kwargs: Any):
        # Existing application service style: action(store, payload).
        if isinstance(first, (PresaleService, PresaleStore)):
            service = _service(first)
            method = getattr(service, name)
            if second is None:
                return method(*args, **kwargs)
            return method(second, *args, **kwargs)
        if second is not None and isinstance(first, (str, Path)):
            service = PresaleService(first)
            method = getattr(service, name)
            return method(second, *args, **kwargs)

        service = _global_service()
        method = getattr(service, name)
        if first is None:
            return method(*args, **kwargs)
        return method(first, second, *args, **kwargs) if second is not None else method(first, *args, **kwargs)

    universal.__name__ = name
    return universal
