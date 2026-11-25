"""SQLite persistence for resale eligibility state."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_default(value: Any) -> Any:
    try:
        from decimal import Decimal
        if isinstance(value, Decimal):
            # The HTTP layer represents rates as JSON numbers; use the same
            # representation in persisted aggregates so replays are stable.
            return float(value)
    except Exception:
        pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class PresaleStore:
    """Small JSON-document store keyed by SKU.

    The feature is aggregate-oriented; keeping the whole eligibility document in
    one row makes idempotency and terminal invalidation straightforward.
    """

    def __init__(self, path: str | Path = ":memory:"):
        self.path_text = str(path)
        self.memory = self.path_text == ":memory:"
        if not self.memory:
            self.path = Path(path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._memory_conn: sqlite3.Connection | None = None
        self.init()

    def connect(self) -> sqlite3.Connection:
        if self.memory:
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._memory_conn.row_factory = sqlite3.Row
            return self._memory_conn
        connection = sqlite3.connect(self.path_text, timeout=8)
        connection.row_factory = sqlite3.Row
        return connection

    def init(self) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS presale_state (
                  sku TEXT PRIMARY KEY,
                  document TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS presale_shipments (
                  shipment_id TEXT PRIMARY KEY,
                  sku TEXT NOT NULL,
                  document TEXT NOT NULL,
                  created_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS presale_credentials (
                  credential_id TEXT PRIMARY KEY,
                  sku TEXT NOT NULL,
                  quote_key TEXT NOT NULL,
                  status TEXT NOT NULL,
                  document TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_presale_credentials_sku ON presale_credentials(sku)"
            )
            db.commit()

    def get_document(self, sku: str) -> dict[str, Any] | None:
        with self._lock, self.connect() as db:
            row = db.execute("SELECT document FROM presale_state WHERE sku=?", (sku,)).fetchone()
        return json.loads(row["document"]) if row else None

    def put_document(self, sku: str, document: dict[str, Any]) -> dict[str, Any]:
        document["updated_at"] = utc_now()
        raw = json.dumps(document, ensure_ascii=False, default=json_default, sort_keys=True)
        with self._lock, self.connect() as db:
            db.execute(
                """
                INSERT INTO presale_state(sku, document, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(sku) DO UPDATE SET document=excluded.document,
                                              updated_at=excluded.updated_at
                """,
                (sku, raw, document["updated_at"]),
            )
            db.commit()
        return document

    def list_documents(self) -> list[dict[str, Any]]:
        with self._lock, self.connect() as db:
            rows = db.execute("SELECT document FROM presale_state ORDER BY sku").fetchall()
        return [json.loads(row["document"]) for row in rows]

    def upsert_credential(self, credential: dict[str, Any]) -> None:
        credential_id = credential.get("credential_id") or credential.get("id")
        if not credential_id:
            return
        now = utc_now()
        raw = json.dumps(credential, ensure_ascii=False, default=json_default, sort_keys=True)
        with self._lock, self.connect() as db:
            db.execute(
                """
                INSERT INTO presale_credentials(
                  credential_id, sku, quote_key, status, document, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(credential_id) DO UPDATE SET
                  status=excluded.status,
                  document=excluded.document,
                  updated_at=excluded.updated_at
                """,
                (
                    credential_id,
                    credential.get("sku", ""),
                    credential.get("quote_key", ""),
                    credential.get("status", ""),
                    raw,
                    credential.get("created_at") or now,
                    now,
                ),
            )
            db.commit()

    def list_credentials(self, sku: str | None = None) -> list[dict[str, Any]]:
        with self._lock, self.connect() as db:
            if sku:
                rows = db.execute(
                    "SELECT document FROM presale_credentials WHERE sku=? ORDER BY created_at, credential_id",
                    (sku,),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT document FROM presale_credentials ORDER BY created_at, credential_id"
                ).fetchall()
        return [json.loads(row["document"]) for row in rows]

    def count_credentials(self, sku: str | None = None) -> int:
        return len(self.list_credentials(sku))

    def insert_shipment(self, shipment_id: str, sku: str, document: dict[str, Any]) -> None:
        raw = json.dumps(document, ensure_ascii=False, default=json_default, sort_keys=True)
        with self._lock, self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO presale_shipments(shipment_id, sku, document, created_at) VALUES (?,?,?,?)",
                (shipment_id, sku, raw, document.get("recorded_at") or utc_now()),
            )
            db.commit()

    def list_shipments(self, sku: str | None = None) -> list[dict[str, Any]]:
        with self._lock, self.connect() as db:
            if sku:
                rows = db.execute(
                    "SELECT document FROM presale_shipments WHERE sku=? ORDER BY created_at, shipment_id",
                    (sku,),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT document FROM presale_shipments ORDER BY created_at, shipment_id"
                ).fetchall()
        return [json.loads(row["document"]) for row in rows]
