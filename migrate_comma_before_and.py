#!/usr/bin/env python3
"""One-off migration: remove commas that precede 'and' in stored CMS copy."""

import os
import sqlite3
import re

DB_PATH = os.environ.get("DB_PATH", "chf_archive.db")
COMMA_BEFORE_AND_RE = re.compile(r",\s+and\b", re.IGNORECASE)


def strip_comma_before_and(text):
    if not isinstance(text, str) or not text:
        return text
    return COMMA_BEFORE_AND_RE.sub(" and", text)


def migrate():
    if not os.path.exists(DB_PATH):
        print(f"No database found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    changed = 0

    cur.execute("SELECT path, value FROM site_content")
    for row in cur.fetchall():
        old_value = row["value"] or ""
        new_value = strip_comma_before_and(old_value)
        if new_value != old_value:
            cur.execute(
                "UPDATE site_content SET value = ? WHERE path = ?",
                (new_value, row["path"]),
            )
            changed += 1

    for column in ("label", "title", "description", "ctaText"):
        cur.execute(f"SELECT id, {column} AS value FROM categories")
        for row in cur.fetchall():
            old_value = row["value"] or ""
            new_value = strip_comma_before_and(old_value)
            if new_value != old_value:
                cur.execute(
                    f"UPDATE categories SET {column} = ? WHERE id = ?",
                    (new_value, row["id"]),
                )
                changed += 1

    for column in ("title", "titleLine1", "titleLine2", "subtitle", "breadcrumb"):
        cur.execute(f"SELECT slug, {column} AS value FROM pages")
        for row in cur.fetchall():
            old_value = row["value"] or ""
            new_value = strip_comma_before_and(old_value)
            if new_value != old_value:
                cur.execute(
                    f"UPDATE pages SET {column} = ? WHERE slug = ?",
                    (new_value, row["slug"]),
                )
                changed += 1

    cur.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'home_trends_section'"
    )
    if cur.fetchone():
        for column in (
            "badge_label",
            "title_line1",
            "title_highlight",
            "title_connector",
            "title_line3",
            "description",
        ):
            cur.execute(f"SELECT id, {column} AS value FROM home_trends_section")
            for row in cur.fetchall():
                old_value = row["value"] or ""
                new_value = strip_comma_before_and(old_value)
                if new_value != old_value:
                    cur.execute(
                        f"UPDATE home_trends_section SET {column} = ? WHERE id = ?",
                        (new_value, row["id"]),
                    )
                    changed += 1

    conn.commit()
    conn.close()
    print(f"Updated {changed} stored content field(s).")


if __name__ == "__main__":
    migrate()
