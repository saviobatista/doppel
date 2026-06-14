"""Research for the Video Agent — real, cited sources, fast.

Three backends (config `research_mode`):
  - "claude_mcp"  : Claude calls the hosted SerpAPI MCP server itself (the user's
                    preferred flow) via Anthropic's MCP connector.
  - "serpapi_rest": one direct SerpAPI Google call we parse (fastest path).
  - "anthropic"   : model-only briefing (no web), used as last-resort fallback.

`research_mode` picks the primary; on failure we degrade claude_mcp -> serpapi_rest
-> anthropic so a build is never blocked. Returns {"text", "sources"} and never raises.
"""
import json
import re
from datetime import UTC, datetime

import anyio
import anthropic
import httpx

from doppel_api.config import get_settings

_MAX_SOURCES = 12
_MCP_BETA = "mcp-client-2025-11-20"
_URL_RE = re.compile(r"https?://[^\s\"'<>]+")


def _today() -> str:
    return datetime.now(UTC).strftime("%A, %d %B %Y")  # e.g. "Sunday, 14 June 2026"


def _locale(language: str) -> tuple[str, str]:
    if language.startswith("pt"):
        return "pt", "br"
    if language.startswith("es"):
        return "es", "mx"
    return "en", "us"


def _system(language: str) -> str:
    return (
        f"You are a research assistant for a short-form video studio. Today is {_today()} "
        "(UTC) — resolve relative dates like 'ontem'/'hoje'/'yesterday' accordingly. Search "
        "the web for the most current, concrete facts the creator needs (names, numbers, "
        "scores, dates, quotes). Do AT MOST two searches, then write a tight briefing in "
        f"{language}: the key talking points and the single strongest narrative angle. Be fast."
    )




# --- sources extraction ------------------------------------------------------

def _sources_from_serp(data: dict) -> list[dict]:
    out, seen = [], set()

    def add(title: str, link: str) -> None:
        if link and link not in seen:
            seen.add(link)
            out.append({"title": title or link, "url": link})

    for it in (data.get("organic_results") or [])[:10]:
        add(it.get("title", ""), it.get("link", ""))
    for it in (data.get("top_stories") or [])[:5]:
        add(it.get("title", ""), it.get("link", ""))
    return out


# --- claude + serpapi MCP connector ------------------------------------------

def _claude_mcp(prompt: str, language: str) -> dict:
    settings = get_settings()
    # Per-call timeout is tight and the loop is short so MCP can't stack to minutes.
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=60.0)
    mcp_url = f"https://mcp.serpapi.com/{settings.serpapi_key}/mcp"
    messages: list[dict] = [{"role": "user", "content": prompt}]

    text_parts: list[str] = []
    sources: list[dict] = []
    seen: set[str] = set()

    for _ in range(2):  # bound pause_turn continuations
        resp = client.beta.messages.create(
            model=settings.anthropic_research_model,
            max_tokens=1500,
            system=_system(language),
            messages=messages,
            mcp_servers=[{"type": "url", "url": mcp_url, "name": "serpapi"}],
            tools=[{"type": "mcp_toolset", "mcp_server_name": "serpapi"}],
            betas=[_MCP_BETA],
        )
        for block in resp.content:
            btype = getattr(block, "type", None)
            if btype == "text" and getattr(block, "text", "").strip():
                text_parts.append(block.text.strip())
            elif btype == "mcp_tool_result" and not getattr(block, "is_error", False):
                for part in getattr(block, "content", []) or []:
                    raw = getattr(part, "text", "") or ""
                    found: list[dict] = []
                    try:
                        found = _sources_from_serp(json.loads(raw))
                    except (ValueError, TypeError):
                        found = [{"title": u, "url": u} for u in _URL_RE.findall(raw)]
                    for s in found:
                        if s["url"] not in seen:
                            seen.add(s["url"])
                            sources.append(s)
        if resp.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})

    return {"text": "\n\n".join(text_parts), "sources": sources[:_MAX_SOURCES]}


# --- direct serpapi REST (fastest) -------------------------------------------

def _agent_search_query(prompt: str, language: str) -> str:
    """The agent builds the web-search query itself: given today's date + the brief,
    Claude returns ONE concise query, resolving relative dates ('ontem'/'hoje') to
    absolute ones. Falls back to the raw brief on error."""
    try:
        client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key, timeout=30.0)
        resp = client.messages.create(
            model=get_settings().anthropic_model,
            max_tokens=80,
            system=(
                f"Today is {_today()} (UTC). You are building a web search. Given the user's "
                f"video brief, output ONE concise Google query in {language} that finds the "
                "specific real event/topic, resolving relative dates ('ontem','hoje','semana "
                "passada') to absolute dates. Output ONLY the query text — no quotes or labels."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        q = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        return q or prompt
    except Exception as exc:
        print(f"agent search-query build failed, using raw brief: {exc!r}")
        return f"{prompt} ({_today()})"


def _serpapi_rest(prompt: str, language: str) -> dict:
    settings = get_settings()
    hl, gl = _locale(language)
    query = _agent_search_query(prompt, language)
    print(f"research search query: {query!r}")
    with httpx.Client(timeout=30) as c:
        r = c.get("https://serpapi.com/search.json", params={
            "engine": "google", "q": query, "api_key": settings.serpapi_key,
            "hl": hl, "gl": gl, "num": "10",
        })
        r.raise_for_status()
        data = r.json()
    lines: list[str] = [f"(search: {query})"]
    kg = data.get("knowledge_graph") or {}
    if kg.get("description"):
        lines.append(kg["description"])
    ab = data.get("answer_box") or {}
    if ab.get("snippet") or ab.get("answer"):
        lines.append(str(ab.get("snippet") or ab.get("answer")))
    for it in (data.get("organic_results") or [])[:10]:
        if it.get("snippet"):
            lines.append(f"- {it.get('title', '')}: {it['snippet']}")
    return {"text": "\n".join(lines), "sources": _sources_from_serp(data)[:_MAX_SOURCES]}


# --- model-only fallback -----------------------------------------------------

def _anthropic_only(prompt: str, language: str) -> dict:
    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key, timeout=90.0)
    resp = client.messages.create(
        model=get_settings().anthropic_research_model,
        max_tokens=1000,
        system=_system(language) + " You have no web access; use general knowledge.",
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    return {"text": text.strip(), "sources": []}


async def research(prompt: str, *, language: str = "pt-BR") -> dict:
    """Return {"text": briefing, "sources": [{title, url}]}. Never raises."""
    settings = get_settings()
    has_key = bool(settings.serpapi_key)
    # Ordered fallback chain starting at the configured primary.
    chain: list = []
    if settings.research_mode == "claude_mcp" and has_key:
        chain = [("claude_mcp", _claude_mcp), ("serpapi_rest", _serpapi_rest),
                 ("anthropic", _anthropic_only)]
    elif settings.research_mode == "serpapi_rest" and has_key:
        chain = [("serpapi_rest", _serpapi_rest), ("anthropic", _anthropic_only)]
    else:
        chain = [("anthropic", _anthropic_only)]

    for name, fn in chain:
        try:
            out = await anyio.to_thread.run_sync(lambda f=fn: f(prompt, language))
            if out.get("text") or out.get("sources"):
                return out
        except Exception as exc:
            print(f"research[{name}] failed: {exc!r}")
    return {"text": "", "sources": []}
