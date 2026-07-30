"""
llm_client.py
-------------
The agent's two LLM calls, kept deliberately separate rather than one
"do everything" prompt:

  1. generate_sql()      question + schema  -> one SQLite SELECT statement
  2. generate_insight()  question + the ACTUAL query results -> a short
                          natural-language summary + a chart recommendation

Splitting them matters: step 2 is grounded in the real returned rows, not
in what the model expects the data to look like, which is what keeps the
"insight" from being a hallucinated guess. Both calls request a narrow,
parseable output (either bare SQL or a small JSON object) rather than a
free-form chat reply, since this is a backend service, not a chat window.

Model: defaults to claude-sonnet-5. Swap to claude-haiku-4-5-20251001 in
settings.py if you want faster/cheaper responses for a live classroom demo
-- SQL generation from a well-described schema doesn't need the biggest model.
"""

from __future__ import annotations

import json
import os

from anthropic import Anthropic

DEFAULT_MODEL = os.environ.get("DATA_AGENT_MODEL", "claude-sonnet-5")

_client = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Get a key from "
                "https://console.anthropic.com and set it in backend/.env "
                "(see .env.example)."
            )
        _client = Anthropic(api_key=api_key)
    return _client


SQL_SYSTEM_PROMPT = """You are a SQL generator for a SQLite database. Given a table \
schema and a user's question in plain English, output EXACTLY ONE SQLite SELECT \
statement that answers it.

Rules:
- Output ONLY the SQL statement. No markdown fences, no explanation, no comments.
- Only SELECT statements. Never modify data or schema.
- Use only the table and columns given in the schema below.
- If the question cannot be answered from this schema, output:
  SELECT 'UNSUPPORTED' AS error LIMIT 1

Schema:
{schema_block}
"""

INSIGHT_SYSTEM_PROMPT = """You turn query results into a short, useful takeaway for a \
non-technical reader, and recommend how to chart them.

Respond with ONLY a JSON object (no markdown fences) shaped exactly like:
{{
  "summary": "one to two plain-English sentences describing what the data shows",
  "chart_type": "bar" | "line" | "pie" | "table" | "none",
  "x_key": "column name to use for the x-axis/labels, or null",
  "y_key": "column name to use for the y-axis/values, or null"
}}

Pick "line" for trends over a time/sequence column, "bar" for comparisons across \
categories, "pie" only for a small number of categories that sum to a meaningful \
whole, "table" when the result is better read as rows, and "none" if there's \
nothing chartable (e.g. a single number or empty result).
"""


def generate_sql(question: str, schema_block: str) -> str:
    client = get_client()
    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=400,
        system=SQL_SYSTEM_PROMPT.format(schema_block=schema_block),
        messages=[{"role": "user", "content": question}],
    )
    sql = response.content[0].text.strip()
    # Defensive cleanup in case the model wraps output in a code fence anyway.
    sql = sql.strip("`").replace("sql\n", "", 1) if sql.startswith("```") else sql
    return sql.strip()


def generate_insight(question: str, sql: str, result_records: list[dict]) -> dict:
    client = get_client()
    payload = {
        "question": question,
        "sql_used": sql,
        "row_count": len(result_records),
        "sample_rows": result_records[:20],  # cap what we send back to the model
    }
    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=500,
        system=INSIGHT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fail soft: the chat turn still returns the data even if the model's
        # JSON was malformed -- an academic demo shouldn't 500 on this.
        return {
            "summary": "Here are the results for your question.",
            "chart_type": "table",
            "x_key": None,
            "y_key": None,
        }
