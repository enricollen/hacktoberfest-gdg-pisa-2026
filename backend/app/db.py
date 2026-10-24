"""SQLite + sqlite-vec: relational catalog/sessions and CLIP vectors in a single local file.

Vectors live in vec0 virtual tables partitioned by shop, so KNN search only scans the
catalog of the shop the box comes from.
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
import numpy as np
import sqlite_vec

from app.vision.embedder import EMBEDDING_DIM

SCHEMA = f"""
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS shops (
    id          INTEGER PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    tagline     TEXT NOT NULL DEFAULT '',
    logo_path   TEXT
);

CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY,
    shop_id         INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,   -- Italian, spoken/shown to the customer
    visual_en       TEXT NOT NULL,   -- English visual description, embedded with CLIP text
    chocolate       TEXT NOT NULL,   -- fondente | latte | bianco | ruby | caramello
    flavors         TEXT NOT NULL,   -- JSON list
    allergens       TEXT NOT NULL,   -- JSON list
    tasting_notes   TEXT NOT NULL,
    image_path      TEXT,
    UNIQUE (shop_id, code)
);

CREATE VIRTUAL TABLE IF NOT EXISTS product_image_vec USING vec0(
    product_id INTEGER PRIMARY KEY,
    shop_id INTEGER PARTITION KEY,
    embedding FLOAT[{EMBEDDING_DIM}] distance_metric=cosine
);

CREATE VIRTUAL TABLE IF NOT EXISTS product_text_vec USING vec0(
    product_id INTEGER PRIMARY KEY,
    shop_id INTEGER PARTITION KEY,
    embedding FLOAT[{EMBEDDING_DIM}] distance_metric=cosine
);

CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    shop_id     INTEGER NOT NULL REFERENCES shops(id),
    created_at  TEXT NOT NULL,
    photo_path  TEXT
);

CREATE TABLE IF NOT EXISTS box_items (
    id           INTEGER PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    product_id   INTEGER NOT NULL REFERENCES products(id),
    x1 REAL NOT NULL, y1 REAL NOT NULL, x2 REAL NOT NULL, y2 REAL NOT NULL,
    det_conf     REAL NOT NULL,
    match_score  REAL NOT NULL
);

-- Append-only log of what each person tasted and said: the shop's feedback goldmine.
CREATE TABLE IF NOT EXISTS tastings (
    id            INTEGER PRIMARY KEY,
    session_id    TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    participant   TEXT NOT NULL,
    box_item_id   INTEGER NOT NULL REFERENCES box_items(id),
    rating        INTEGER,
    comment       TEXT,
    created_at    TEXT NOT NULL
);
"""

PRODUCT_COLUMNS = (
    "id, shop_id, code, name, description, visual_en, chocolate, flavors, allergens, "
    "tasting_notes, image_path"
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _product(row: aiosqlite.Row) -> dict[str, Any]:
    p = dict(row)
    p["flavors"] = json.loads(p["flavors"])
    p["allergens"] = json.loads(p["allergens"])
    return p


class Database:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    @classmethod
    async def connect(cls, path: Path) -> "Database":
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(path)
        conn.row_factory = aiosqlite.Row
        await conn.enable_load_extension(True)
        await conn.load_extension(sqlite_vec.loadable_path())
        await conn.enable_load_extension(False)
        await conn.executescript(SCHEMA)
        await conn.commit()
        return cls(conn)

    async def close(self) -> None:
        await self.conn.close()

    # --- shops & catalog -------------------------------------------------------------------

    async def upsert_shop(self, slug: str, name: str, tagline: str, logo_path: str | None) -> int:
        cur = await self.conn.execute(
            """INSERT INTO shops (slug, name, tagline, logo_path) VALUES (?, ?, ?, ?)
               ON CONFLICT (slug) DO UPDATE SET name = excluded.name,
                   tagline = excluded.tagline, logo_path = excluded.logo_path
               RETURNING id""",
            (slug, name, tagline, logo_path),
        )
        (shop_id,) = await cur.fetchone()
        await self.conn.commit()
        return shop_id

    async def get_shop(self, slug: str) -> dict[str, Any] | None:
        cur = await self.conn.execute("SELECT * FROM shops WHERE slug = ?", (slug,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_shop_by_id(self, shop_id: int) -> dict[str, Any] | None:
        cur = await self.conn.execute("SELECT * FROM shops WHERE id = ?", (shop_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def upsert_product(
        self,
        shop_id: int,
        product: dict[str, Any],
        image_embedding: np.ndarray | None,
        text_embedding: np.ndarray,
    ) -> int:
        cur = await self.conn.execute(
            """INSERT INTO products (shop_id, code, name, description, visual_en, chocolate,
                   flavors, allergens, tasting_notes, image_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (shop_id, code) DO UPDATE SET name = excluded.name,
                   description = excluded.description, visual_en = excluded.visual_en,
                   chocolate = excluded.chocolate, flavors = excluded.flavors,
                   allergens = excluded.allergens, tasting_notes = excluded.tasting_notes,
                   image_path = excluded.image_path
               RETURNING id""",
            (
                shop_id,
                product["code"],
                product["name"],
                product["description"],
                product["visual_en"],
                product["chocolate"],
                json.dumps(product["flavors"], ensure_ascii=False),
                json.dumps(product["allergens"], ensure_ascii=False),
                product["tasting_notes"],
                product.get("image_path"),
            ),
        )
        (product_id,) = await cur.fetchone()
        for table, vec in (
            ("product_image_vec", image_embedding),
            ("product_text_vec", text_embedding),
        ):
            # vec0 has no UPSERT: replace by delete + insert.
            await self.conn.execute(f"DELETE FROM {table} WHERE product_id = ?", (product_id,))
            if vec is not None:
                await self.conn.execute(
                    f"INSERT INTO {table} (product_id, shop_id, embedding) VALUES (?, ?, ?)",
                    (product_id, shop_id, vec.astype(np.float32).tobytes()),
                )
        await self.conn.commit()
        return product_id

    async def list_products(self, shop_id: int) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            f"SELECT {PRODUCT_COLUMNS} FROM products WHERE shop_id = ? ORDER BY code", (shop_id,)
        )
        return [_product(r) for r in await cur.fetchall()]

    async def knn(
        self, table: str, shop_id: int, query: np.ndarray, k: int
    ) -> list[tuple[int, float]]:
        """Return (product_id, cosine similarity) of the k nearest products of a shop."""
        assert table in ("product_image_vec", "product_text_vec")
        cur = await self.conn.execute(
            f"""SELECT product_id, distance FROM {table}
                WHERE embedding MATCH ? AND k = ? AND shop_id = ?""",
            (query.astype(np.float32).tobytes(), k, shop_id),
        )
        return [(pid, 1.0 - dist) for pid, dist in await cur.fetchall()]

    # --- sessions --------------------------------------------------------------------------

    async def create_session(self, session_id: str, shop_id: int) -> None:
        await self.conn.execute(
            "INSERT INTO sessions (id, shop_id, created_at) VALUES (?, ?, ?)",
            (session_id, shop_id, now_iso()),
        )
        await self.conn.commit()

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        cur = await self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def replace_box_items(
        self, session_id: str, photo_path: str, items: Sequence[dict[str, Any]]
    ) -> list[int]:
        await self.conn.execute("DELETE FROM box_items WHERE session_id = ?", (session_id,))
        await self.conn.execute(
            "UPDATE sessions SET photo_path = ? WHERE id = ?", (photo_path, session_id)
        )
        ids = []
        for it in items:
            cur = await self.conn.execute(
                """INSERT INTO box_items (session_id, product_id, x1, y1, x2, y2, det_conf,
                       match_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                (session_id, it["product_id"], *it["bbox"], it["det_conf"], it["match_score"]),
            )
            (item_id,) = await cur.fetchone()
            ids.append(item_id)
        await self.conn.commit()
        return ids

    async def list_box_items(self, session_id: str) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            f"""SELECT b.id AS item_id, b.x1, b.y1, b.x2, b.y2, b.det_conf, b.match_score,
                       {", ".join("p." + c for c in PRODUCT_COLUMNS.split(", "))}
                FROM box_items b JOIN products p ON p.id = b.product_id
                WHERE b.session_id = ? ORDER BY b.id""",
            (session_id,),
        )
        return [_product(r) for r in await cur.fetchall()]

    async def log_tasting(
        self,
        session_id: str,
        participant: str,
        box_item_id: int,
        rating: int | None,
        comment: str | None,
    ) -> None:
        await self.conn.execute(
            """INSERT INTO tastings (session_id, participant, box_item_id, rating, comment,
                   created_at) VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, participant, box_item_id, rating, comment, now_iso()),
        )
        await self.conn.commit()
