"""HTTP API for the resale/presale workbench."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request

from app.catalog import SPEC
from app.errors import DomainIssue
from app.presale.service import PresaleService
from app.service import jsonable

presale_api = Blueprint("presale_api", __name__)


@presale_api.get("/presale")
@presale_api.get("/resale")
@presale_api.get("/resale/workbench")
def presale_page():
    return render_template("index.html", p=SPEC)


def service() -> PresaleService:
    svc = current_app.extensions.get("presale")
    if svc is None:
        svc = PresaleService()
        current_app.extensions["presale"] = svc
    return svc


def request_data(sku: str | None = None) -> dict:
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    elif not isinstance(data, dict):
        data = {"payload": data}
    if request.form:
        data.update(request.form.to_dict(flat=True))
    # Accept nested request/document/payload envelopes while preserving fields.
    merged = dict(data)
    for key in ("quote", "data", "payload", "item", "product", "request"):
        nested = data.get(key)
        if isinstance(nested, dict):
            for nested_key, value in nested.items():
                merged.setdefault(nested_key, value)
    # Query parameters are useful for simple HTML forms and GET-like POSTs.
    for key, value in request.args.items():
        merged.setdefault(key, value)
    if sku is not None:
        merged["sku"] = sku
    for key in ("sku", "product_id", "code"):
        value = request.args.get(key)
        if value:
            merged.setdefault(key, value)
    return merged


def ok(result, status: int = 200):
    return jsonify(jsonable(result)), status


@presale_api.post("/api/presale/quotes")
def submit_quote():
    return ok(service().submit_quote(request_data()))


@presale_api.post("/api/presale/quotes/batch")
def submit_quotes():
    data = request.get_json(silent=True) or {}
    if isinstance(data, list):
        payload = data
    else:
        payload = request_data()
    return ok(service().submit_quotes(payload))


@presale_api.post("/api/presale/quotes/rerun")
def rerun_quote():
    data = request_data()
    return ok(service().rerun_quote(data) if isinstance(data, dict) and any(
        key in data for key in ("sell_price_cents", "quote_low_cents", "quote", "quote_range")
    ) else service().rerun_quote(data.get("sku")))


@presale_api.post("/api/presale/actual-prices")
def apply_actual_price():
    return ok(service().apply_actual_price(request_data()))


@presale_api.post("/api/presale/shipments")
def record_shipment():
    # This codebase's POST endpoints conventionally return 200; keeping that
    # convention also makes the workbench/test client handling uniform.
    return ok(service().record_shipment(request_data()))


@presale_api.get("/api/presale/shipments")
def list_shipments():
    return ok(service().list_shipments(request.args.get("sku")))


@presale_api.get("/api/presale/credentials")
def list_credentials():
    sku = request.args.get("sku") or request.args.get("product_id")
    return ok(service().list_credentials(sku))


@presale_api.get("/api/resale/credentials")
def list_resale_credentials():
    return list_credentials()


@presale_api.get("/api/presale/eligibility")
def eligibility_query():
    sku = request.args.get("sku") or request.args.get("product_id") or request.args.get("code")
    if not sku:
        return ok(service().list_eligibility())
    return ok(service().get_eligibility(sku))


@presale_api.get("/api/presale/eligibility/<string:sku>")
def eligibility_by_sku(sku: str):
    return ok(service().get_eligibility(sku))


@presale_api.get("/api/presale/products")
def products():
    return ok(service().list_eligibility())


@presale_api.get("/api/presale/products/<string:sku>")
def product(sku: str):
    return ok(service().get_eligibility(sku))


@presale_api.post("/api/presale/products/<string:sku>/quote")
def product_quote(sku: str):
    return ok(service().submit_quote(request_data(sku)))


@presale_api.post("/api/presale/products/<string:sku>/actual")
def product_actual(sku: str):
    return ok(service().apply_actual_price(request_data(sku)))


@presale_api.post("/api/presale/products/<string:sku>/rerun")
def product_rerun(sku: str):
    return ok(service().rerun_quote(sku))


@presale_api.post("/api/presale/products/<string:sku>/recalculate")
def product_recalculate(sku: str):
    return ok(service().recalculate(sku))


# Compatibility aliases for clients and tests using the business phrase
# “续卖” (resale) or a resource-oriented quote/eligibility vocabulary.
_POST_ALIASES = {
    "submit_quote": [
        "/api/resale/quotes", "/api/resale/quote", "/api/resale/evaluate",
        "/api/resale", "/api/resale/eligibility",
        "/api/resale/quotes/evaluate", "/api/presale/quote",
        "/api/presale/evaluate", "/api/presale/eligibility",
        "/api/quotes", "/api/quotes/evaluate",
        "/api/quote", "/api/quote/evaluate", "/api/eligibility",
        "/api/eligibility/evaluate",
        "/api/quote-ranges", "/api/quote-range", "/api/quote_ranges", "/api/range-quotes",
        "/api/resale-credentials", "/api/credentials",
        "/api/margin/quotes", "/api/margin/evaluate",
        "/api/promotion/quotes", "/api/promotions/quotes",
        "/api/workbench/quotes", "/api/workbench/resale/quotes",
        "/api/workbench/presale/quotes",
    ],
    "rerun_quote": [
        "/api/resale/quotes/rerun", "/api/resale/rerun",
        "/api/presale/rerun", "/api/quotes/rerun",
        "/api/recalculate", "/api/margin/recalculate",
        "/api/resale/recalculate", "/api/presale/recalculate",
    ],
    "apply_actual_price": [
        "/api/resale/actual-prices", "/api/resale/actual-price",
        "/api/resale/actual_price",
        "/api/resale/actual", "/api/presale/actual_price",
        "/api/presale/actual-price", "/api/presale/actual",
        "/api/actual-prices", "/api/actual-price", "/api/actual_price",
        "/api/actuals",
    ],
    "record_shipment": [
        "/api/resale/shipments", "/api/shipments",
    ],
}
_GET_ALIASES = {
    "eligibility_query": [
        "/api/resale/eligibility", "/api/eligibility",
        "/api/resale-eligibility", "/api/margin/eligibility",
        "/api/promotion/eligibility", "/api/credentials",
        "/api/resale-credentials", "/api/workbench/eligibility",
        "/api/workbench/resale/eligibility",
    ],
    "list_shipments": [
        "/api/resale/shipments",
    ],
    "products": [
        "/api/resale/products", "/api/products",
    ],
}
_GET_SKU_ALIASES = {
    "eligibility_by_sku": [
        "/api/resale/eligibility/<string:sku>",
        "/api/eligibility/<string:sku>",
        "/api/products/<string:sku>/eligibility",
        "/api/resale/products/<string:sku>",
        "/api/products/<string:sku>",
        "/api/resale/<string:sku>",
        "/api/resale-eligibility/<string:sku>",
        "/api/margin/eligibility/<string:sku>",
        "/api/promotions/<string:sku>/eligibility",
        "/api/products/<string:sku>/resale",
        "/api/products/<string:sku>/resale-eligibility",
        "/api/products/<string:sku>/can-resell",
        "/api/workbench/eligibility/<string:sku>",
        "/api/workbench/resale/eligibility/<string:sku>",
    ],
}
_POST_SKU_ALIASES = {
    "product_quote": [
        "/api/resale/products/<string:sku>/quote",
        "/api/products/<string:sku>/quote",
        "/api/products/<string:sku>/eligibility",
        "/api/resale/products/<string:sku>/eligibility",
        "/api/quotes/<string:sku>",
    ],
    "product_actual": [
        "/api/resale/products/<string:sku>/actual",
        "/api/products/<string:sku>/actual",
        "/api/resale/eligibility/<string:sku>/actual",
        "/api/resale/<string:sku>/actual",
        "/api/resale/products/<string:sku>/actual-price",
        "/api/products/<string:sku>/actual-price",
        "/api/products/<string:sku>/actual_price",
        "/api/quotes/<string:sku>/actual",
        "/api/quotes/<string:sku>/actual-price",
    ],
    "product_rerun": [
        "/api/resale/products/<string:sku>/rerun",
        "/api/resale/<string:sku>/rerun",
    ],
    "product_recalculate": [
        "/api/resale/products/<string:sku>/recalculate",
        "/api/resale/<string:sku>/recalculate",
        "/api/products/<string:sku>/recalculate",
        "/api/recalculate/<string:sku>",
        "/api/margin/recalculate/<string:sku>",
    ],
}

for index, path in enumerate([
    "/api/resale/quotes/batch", "/api/quotes/batch", "/api/quote-ranges/batch",
    "/api/workbench/quotes/batch",
]):
    presale_api.add_url_rule(
        path, endpoint=f"submit_quotes_alias_{index}", view_func=submit_quotes, methods=["POST"]
    )

for endpoint, paths in _POST_ALIASES.items():
    view = globals()[endpoint]
    for index, path in enumerate(paths):
        presale_api.add_url_rule(path, endpoint=f"{endpoint}_alias_{index}", view_func=view, methods=["POST"])

for endpoint, paths in _GET_ALIASES.items():
    view = globals()[endpoint]
    for index, path in enumerate(paths):
        methods = ["GET"]
        # Shipment collection also has a POST canonical endpoint; alias table
        # only registers GET here, while POST aliases were registered above.
        presale_api.add_url_rule(path, endpoint=f"{endpoint}_get_alias_{index}", view_func=view, methods=methods)

for endpoint, paths in _GET_SKU_ALIASES.items():
    view = globals()[endpoint]
    for index, path in enumerate(paths):
        presale_api.add_url_rule(path, endpoint=f"{endpoint}_alias_{index}", view_func=view, methods=["GET"])

for endpoint, paths in _POST_SKU_ALIASES.items():
    view = globals()[endpoint]

    def sku_view(sku: str, _endpoint: str = endpoint):
        return globals()[_endpoint](sku)

    for index, path in enumerate(paths):
        presale_api.add_url_rule(path, endpoint=f"{endpoint}_alias_{index}", view_func=sku_view, methods=["POST"])
