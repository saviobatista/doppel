"""Anthropic: turn a request + web research into a full Video Plan artifact.

The artifact is the editable object the user reviews before generation. It is a
superset of the generation `script` (providers/script.py) — it additionally
carries research, per-scene direction, transitions, audio design, and the
resource manifest (avatars, voices, media, audio, design-element overlays) that
the Video Agent screen renders.
"""
import json

import anyio
import anthropic

from doppel_api.config import get_settings

_TRANSITIONS = ["cut", "crossfade", "whip", "zoom", "fade", "slide"]
_SHOTS = ["close-up", "medium", "wide", "over-shoulder", "insert", "b-roll"]
_OVERLAYS = [
    "lower_third", "title_card", "stat_card", "scoreboard", "score_bug",
    "ticker", "timer", "quote", "bullet_list", "logo_bug",
]

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Punchy video title."},
        "logline": {"type": "string", "description": "One-sentence summary."},
        "style": {"type": "string", "description": "Visual + editorial style direction."},
        "footage_query": {
            "type": "string",
            "description": (
                "Concrete real-world search terms (teams, players, event, date) to find "
                "recent, on-topic videos on YouTube — e.g. 'Brasil x Marrocos Copa 2026 "
                "melhores momentos'. Specific, not generic."
            ),
        },
        "research": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "angle": {"type": "string", "description": "The chosen narrative angle."},
                "key_points": {"type": "array", "items": {"type": "string"}},
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "url": {"type": "string"},
                        },
                        "required": ["title", "url"],
                    },
                },
            },
            "required": ["summary", "angle", "key_points"],
        },
        "script": {
            "type": "object",
            "properties": {
                "scenes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string", "description": "Short scene label."},
                            "kind": {"type": "string", "enum": ["avatar", "broll"]},
                            "narration": {"type": "string", "description": "Spoken VO."},
                            "on_screen_text": {"type": "string"},
                            "duration_seconds": {"type": "number"},
                            "direction": {
                                "type": "object",
                                "properties": {
                                    "shot": {"type": "string", "enum": _SHOTS},
                                    "framing": {"type": "string"},
                                    "camera": {"type": "string", "description": "Camera move."},
                                    "mood": {"type": "string"},
                                    "b_roll_prompt": {
                                        "type": "string",
                                        "description": "Image/video prompt for broll scenes.",
                                    },
                                },
                                "required": ["shot", "mood"],
                            },
                            "transition_out": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string", "enum": _TRANSITIONS},
                                    "duration_seconds": {"type": "number"},
                                },
                                "required": ["type"],
                            },
                            "overlays": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "design_element ids shown in this scene.",
                            },
                        },
                        "required": ["id", "title", "kind", "duration_seconds", "direction"],
                    },
                },
            },
            "required": ["scenes"],
        },
        "audio": {
            "type": "object",
            "properties": {
                "music": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "mood": {"type": "string"},
                        "bpm": {"type": "number"},
                        "prompt": {
                            "type": "string",
                            "description": (
                                "A vivid INSTRUMENTAL music-generation prompt (genre, "
                                "instruments, energy, BPM) for the background track."
                            ),
                        },
                    },
                    "required": ["title", "mood"],
                },
                "sfx": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "cue": {"type": "string"},
                            "at_scene": {"type": "string"},
                        },
                        "required": ["cue"],
                    },
                },
                "voiceover": {
                    "type": "object",
                    "properties": {
                        "voice_label": {"type": "string"},
                        "tone": {"type": "string"},
                    },
                },
                "ducking": {"type": "boolean"},
            },
            "required": ["music"],
        },
        "resources": {
            "type": "object",
            "properties": {
                "media": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "kind": {"type": "string", "enum": ["image", "video"]},
                            "prompt": {
                                "type": "string",
                                "description": "Generation prompt (used when generating).",
                            },
                            "search_query": {
                                "type": "string",
                                "description": (
                                    "Concrete real-world search terms to FIND this clip/"
                                    "photo on the web (names, teams, event, date)."
                                ),
                            },
                            "scene_id": {"type": "string"},
                        },
                        "required": ["label", "kind"],
                    },
                },
                "design_elements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "label": {"type": "string", "description": "Human name for the list."},
                            "kind": {"type": "string", "enum": _OVERLAYS},
                            "content": {
                                "type": "object",
                                "description": (
                                    "REAL plan-specific data to render, in the target "
                                    "language. Use the fields for this kind: scoreboard/"
                                    "score_bug -> home, away, home_score, away_score, status; "
                                    "stat_card -> title + value OR title + rows[{label,value}]; "
                                    "lower_third -> title, subtitle; title_card -> title, "
                                    "subtitle; ticker/bullet_list -> title, items[]; timer -> "
                                    "time; quote -> text, attribution; logo_bug -> text."
                                ),
                                "properties": {
                                    "home": {"type": "string"},
                                    "away": {"type": "string"},
                                    "home_score": {"type": "string"},
                                    "away_score": {"type": "string"},
                                    "status": {"type": "string"},
                                    "title": {"type": "string"},
                                    "subtitle": {"type": "string"},
                                    "value": {"type": "string"},
                                    "time": {"type": "string"},
                                    "text": {"type": "string"},
                                    "attribution": {"type": "string"},
                                    "items": {"type": "array", "items": {"type": "string"}},
                                    "rows": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "label": {"type": "string"},
                                                "value": {"type": "string"},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                        "required": ["id", "label", "kind", "content"],
                    },
                },
            },
        },
        "meta": {
            "type": "object",
            "properties": {
                "credits_estimate": {"type": "string", "description": "e.g. '30-45'."},
                "media_strategy": {
                    "type": "string",
                    "enum": ["scrape", "generate", "hybrid"],
                    "description": (
                        "'scrape' when the topic is a real, documented event with "
                        "trustworthy media online (a real match, news); 'generate' for "
                        "abstract/evergreen topics; 'hybrid' to scrape with generation "
                        "fallback."
                    ),
                },
            },
        },
    },
    "required": ["title", "style", "research", "script", "audio", "resources"],
}


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key, timeout=150.0)


def _system(*, duration: int, orientation: str, language: str,
            avatar_label: str, voice_label: str) -> str:
    # ~1 scene per 8s keeps the output (and latency) down; a 40s video -> ~5 scenes.
    n_scenes = max(3, min(6, round(duration / 8)))
    import datetime as _dt
    today = _dt.datetime.now(_dt.UTC).strftime("%A, %d %B %Y")
    return (
        f"Today is {today} (UTC); resolve relative dates accordingly and rely on the "
        "provided research for facts. "
        "You are the creative director of an AI short-form video studio. Turn the user's "
        "request and the provided web research into a complete, production-ready VIDEO PLAN "
        "by calling emit_plan. Cover, in order: research (synthesis + the strongest angle + "
        "key talking points + the cited sources), a scene-by-scene script, per-scene "
        "direction (shot, framing, camera move, mood, and a concrete b_roll_prompt for broll "
        "scenes), transitions between scenes, an audio design (music bed, SFX cues, "
        "voiceover tone, ducking), and a resource manifest (b-roll media to source/generate "
        "and design-element overlays such as lower-thirds, stat cards, scoreboards, score "
        "bugs, timers).\n"
        f"Constraints: total runtime ~{duration}s across about {n_scenes} scenes; the avatar "
        f"is '{avatar_label}' and the voiceover uses the '{voice_label}' voice; orientation "
        f"is {orientation}; write ALL narration and on-screen/user-facing text in {language}. "
        "Alternate 'avatar' scenes (the presenter talking) with 'broll' scenes (footage). "
        "Every broll scene needs a vivid b_roll_prompt. CRITICAL: in resources.design_elements, "
        "define EVERY overlay id you reference in any scene's overlays, and fill each one's "
        "`content` with the REAL, specific data from the research (actual team names, scores, "
        "player names, stat numbers, dates) — never placeholders. A scoreboard must carry the "
        "real teams + score; a stat_card the real metric + value; a lower_third the real "
        "name + role. In resources.media, list each b-roll asset (label, kind, prompt for "
        "generation, AND a concrete search_query of real-world terms to find it online, "
        "scene_id). Set meta.media_strategy: 'scrape' for a real documented event (a real "
        "match/news with media online), else 'generate'. Set footage_query to specific real-"
        "world terms for finding recent topical videos on YouTube. Fill audio.music.prompt with "
        "a vivid instrumental track description. Keep narration natural and spoken. Respond ONLY "
        "via emit_plan."
    )


def _open_brackets(s: str) -> list[str]:
    """Closers needed to balance the (string-aware) open brackets in `s`."""
    stack: list[str] = []
    in_str = esc = False
    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]" and stack:
            stack.pop()
    return stack


def _partial_json(buf: str) -> dict | None:
    """Best-effort parse of an in-flight tool-input JSON string: cut to the last
    completed value, append the brackets needed to close it, and parse. Returns
    None when it can't yet form valid JSON (that streaming tick is just skipped)."""
    in_str = esc = False
    cut = -1
    for i, ch in enumerate(buf):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
                cut = i + 1
            continue
        if ch == '"':
            in_str = True
        elif ch in "}]":
            cut = i + 1
    if cut < 1:
        return None
    head = buf[:cut]
    try:
        return json.loads(head + "".join(reversed(_open_brackets(head))))
    except ValueError:
        comma = head.rfind(",")
        if comma <= 0:
            return None
        trimmed = head[:comma]
        try:
            return json.loads(trimmed + "".join(reversed(_open_brackets(trimmed))))
        except ValueError:
            return None


def _merge_sources(artifact: dict, sources: list[dict]) -> dict:
    _normalize(artifact)
    ro = artifact["research"]
    if sources:
        have = [s for s in (ro.get("sources") or []) if isinstance(s, dict) and s.get("url")]
        existing = {s["url"] for s in have}
        have.extend(s for s in sources if s["url"] not in existing)
        ro["sources"] = have
    return artifact


def _call(prompt: str, research: dict, *, duration: int, orientation: str,
          language: str, avatar_label: str, voice_label: str,
          on_partial=None) -> dict:
    settings = get_settings()
    sources = research.get("sources") or []
    research_block = (
        f"USER REQUEST:\n{prompt}\n\n"
        f"WEB RESEARCH (synthesize, do not copy verbatim):\n{research.get('text', '')}\n\n"
        f"SOURCES (echo the relevant ones into research.sources):\n{json.dumps(sources)}"
    )
    kwargs = dict(
        model=settings.anthropic_planner_model,
        max_tokens=8000,  # ample for ~5 scenes; Sonnet is concise so no truncation
        system=_system(duration=duration, orientation=orientation, language=language,
                       avatar_label=avatar_label, voice_label=voice_label),
        messages=[{"role": "user", "content": research_block}],
        tools=[{
            "name": "emit_plan",
            "description": "Emit the complete structured video plan artifact.",
            "input_schema": SCHEMA,
        }],
        tool_choice={"type": "tool", "name": "emit_plan"},
    )

    if on_partial is None:
        resp = _client().messages.create(**kwargs)
        block = next((b for b in resp.content if b.type == "tool_use"), None)
        if block is None or not block.input:
            raise RuntimeError(f"planner emitted no tool_use ({resp.stop_reason})")
        return _merge_sources(block.input, sources)

    # Stream: accumulate the tool-input JSON and push throttled partial artifacts so
    # the UI fills the plan in progressively while it generates.
    import time as _time
    buf = ""
    last_emit = 0.0
    with _client().messages.stream(**kwargs) as stream:
        for event in stream:
            if (event.type == "content_block_delta"
                    and getattr(event.delta, "type", None) == "input_json_delta"):
                buf += event.delta.partial_json
                now = _time.monotonic()
                if now - last_emit > 1.0:
                    partial = _partial_json(buf)
                    if partial and (partial.get("title") or partial.get("script")):
                        on_partial(_merge_sources(partial, sources))
                    last_emit = now
        final = stream.get_final_message()
    block = next((b for b in final.content if b.type == "tool_use"), None)
    if block is None or not block.input:
        raise RuntimeError(f"planner emitted no tool_use ({final.stop_reason})")
    return _merge_sources(block.input, sources)


def _normalize(artifact: dict) -> None:
    """Coerce the container fields to their expected shapes. The model occasionally
    emits an object/array field as a bare string; downstream code must not crash."""

    def obj(parent: dict, key: str) -> dict:
        if not isinstance(parent.get(key), dict):
            parent[key] = {}
        return parent[key]

    research = artifact.get("research")
    if not isinstance(research, dict):
        artifact["research"] = {
            "summary": research if isinstance(research, str) else "",
            "angle": "", "key_points": [],
        }
    obj(artifact, "meta")
    res = obj(artifact, "resources")
    for k in ("media", "design_elements", "audio"):
        if k in res and not isinstance(res[k], list):
            res[k] = []
    obj(obj(artifact, "audio"), "music")
    script = obj(artifact, "script")
    if not isinstance(script.get("scenes"), list):
        script["scenes"] = []


async def build_plan(prompt: str, research: dict, *, duration_seconds: int = 40,
                     orientation: str = "portrait", language: str = "pt-BR",
                     avatar_label: str = "Avatar", voice_label: str = "Voice",
                     on_partial=None) -> dict:
    """Generate the plan. If `on_partial` (async) is given, the planner streams and
    `on_partial(partial_artifact)` is invoked with progressively-completing plans."""
    # Bridge the async on_partial into the sync streaming call's worker thread.
    sync_partial = None
    if on_partial is not None:
        def sync_partial(art):  # runs inside the streaming worker thread
            try:
                anyio.from_thread.run(on_partial, art)
            except Exception:
                pass

    def call() -> dict:
        return _call(
            prompt, research, duration=duration_seconds, orientation=orientation,
            language=language, avatar_label=avatar_label, voice_label=voice_label,
            on_partial=sync_partial,
        )

    artifact = await anyio.to_thread.run_sync(call)
    if not (artifact.get("script") or {}).get("scenes"):
        artifact = await anyio.to_thread.run_sync(call)
    return artifact
