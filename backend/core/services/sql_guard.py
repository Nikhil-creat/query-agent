"""
sql_guard.py
------------
The single most important safety component in this project: the LLM
generates SQL from free-text user input, and that SQL is about to be
executed against a real database. That is a textbook injection surface
even though the "attacker" is our own model rather than a malicious user
-- an ambiguous question, a bug in the prompt, or an adversarial dataset
name could all produce SQL we didn't intend.

Policy: only a single read-only SELECT statement is ever allowed to run.
Everything else is rejected before it reaches the database, not caught
after the fact.
"""

from __future__ import annotations

import re

# Statement types that must never execute, no matter how the query is phrased.
_FORBIDDEN_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE",
    "TRUNCATE", "ATTACH", "DETACH", "PRAGMA", "VACUUM", "REINDEX",
    "GRANT", "REVOKE",
)


class SqlRejected(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql


def validate_select_only(sql: str) -> str:
    """Returns the cleaned SQL if it passes, otherwise raises SqlRejected."""
    if not sql or not sql.strip():
        raise SqlRejected("Model returned an empty query.")

    cleaned = _strip_comments(sql).strip()

    # Reject multiple statements chained with ';' (a single trailing ';' is fine).
    body = cleaned[:-1] if cleaned.endswith(";") else cleaned
    if ";" in body:
        raise SqlRejected("Multiple statements are not allowed.")

    if not re.match(r"^\s*SELECT\b", body, flags=re.IGNORECASE):
        raise SqlRejected("Only SELECT statements are allowed.")

    upper = body.upper()
    for kw in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", upper):
            raise SqlRejected(f"Query contains a disallowed keyword: {kw}.")

    return body


def enforce_row_limit(sql: str, max_rows: int = 500) -> str:
    """Appends a LIMIT if the model didn't include one, so one bad query
    can't try to pull an entire large table into memory / the response.
    """
    if re.search(r"\bLIMIT\s+\d+", sql, flags=re.IGNORECASE):
        return sql
    return f"{sql.rstrip().rstrip(';')} LIMIT {max_rows}"
