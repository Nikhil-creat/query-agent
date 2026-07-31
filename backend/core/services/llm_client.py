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

Provider: supports two backends, switched with the LLM_PROVIDER env var:
  - "anthropic" (default) -- Claude, via ANTHROPIC_API_KEY
  - "gemini"              -- Google Gemini, via GEMINI_API_KEY. Google AI
                              Studio (aistudio.google.com) gives a genuinely
                              free, no-credit-card API key -- use this if
                              you don't want to set up Anthropic billing.
Nothing else in the pipeline (sql_guard, views, schema_utils) needs to
change based on which provider is active; both paths return the same
plain string / dict shapes.
"""

from __future__ import annotations

import json
import os

PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").lower()

DEFAULT_MODEL = os.environ.get(
    "DATA_AGENT_MODEL",
    "claude-sonnet-5" if PROVIDER == "anthropic" else "gemini-2.5-flash",
)

_client = None


def get_client():
    """Returns a cached client for whichever provider is configured."""
    global _client
    if _client is not None:
        return _client

    if PROVIDER == "gemini":
        from google import genai

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Get a free key (no card needed) "
                "from https://aistudio.google.com and set it in backend/.env "
                "(see .env.example)."
            )
        _client = genai.Client(api_key=api_key)
    else:
        from anthropic import Anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Get a key from "
                "https://platform.claude.com and set it in backend/.env "
                "(see .env.example). Or set LLM_PROVIDER=gemini in .env to "
                "use the free Google Gemini backend instead -- no card needed."
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


def _call_model(system_prompt: str, user_content: str, max_tokens: int) -> str:
    """Provider-agnostic single-turn call. Returns the raw text response."""
    client = get_client()

    if PROVIDER == "gemini":
        from google.genai import types

        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens,
            ),
        )
        return (response.text or "").strip()

    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text.strip()


def generate_sql(question: str, schema_block: str) -> str:
    sql = _call_model(
        SQL_SYSTEM_PROMPT.format(schema_block=schema_block), question, max_tokens=400
    )
    sql = sql.strip("`").replace("sql\n", "", 1) if sql.startswith("```") else sql
    return sql.strip()


def generate_insight(question: str, sql: str, result_records: list[dict]) -> dict:
    payload = {
        "question": question,
        "sql_used": sql,
        "row_count": len(result_records),
        "sample_rows": result_records[:20],
    }
    text = _call_model(
        INSIGHT_SYSTEM_PROMPT, json.dumps(payload, default=str), max_tokens=500
    )
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "summary": "Here are the results for your question.",
            "chart_type": "table",
            "x_key": None,
            "y_key": None,
        }
