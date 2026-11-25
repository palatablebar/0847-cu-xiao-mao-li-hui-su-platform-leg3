import os

from flask import Flask, jsonify, render_template
from werkzeug.exceptions import RequestEntityTooLarge

from app.catalog import SPEC
from app.config import MAX_FILE, ROOT
from app.errors import DomainIssue, error_response
from app.presale.routes import presale_api
from app.presale.service import PresaleService
from app.presale.store import PresaleStore
from app.review.store import Store
from app.routes import api


def create_app(database=None):
    app = Flask(__name__)
    database_path = database or os.getenv("WORKBENCH_DB", str(ROOT / "instance" / "workbench.sqlite3"))
    app.config["MAX_CONTENT_LENGTH"] = MAX_FILE + 64 * 1024
    app.extensions["runs"] = Store(database_path)
    presale_store = PresaleStore(database_path)
    app.extensions["presale_store"] = presale_store
    app.extensions["presale"] = PresaleService(presale_store)
    app.register_error_handler(DomainIssue, error_response)
    app.register_error_handler(RequestEntityTooLarge, lambda _: error_response(DomainIssue("FILE_TOO_LARGE", 413)))
    app.register_blueprint(api)
    app.register_blueprint(presale_api)

    @app.get("/")
    def home():
        return render_template("index.html", p=SPEC)

    @app.get("/healthz")
    def health():
        return jsonify(status="ok")

    return app


app = create_app()
