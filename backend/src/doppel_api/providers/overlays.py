"""Render design-element overlays (scoreboards, stat cards, lower-thirds, ...) to PNG.

These are the broadcast-style graphics the plan references in scene `overlays`.
Templated with Pillow (crisp text, no AI artifacts), styled to match the app's
dark/cyan theme.

Data-driven: each overlay is drawn from a structured `content` dict the planner
fills with the REAL, plan-specific data (team names, scores, stat values, names),
so every overlay is dynamic per plan. When `content` is absent we fall back to
parsing the human `label`/scene text, and finally to a generic card — so it never
fails the build.
"""
import io
import re

from PIL import Image, ImageDraw, ImageFont

_FONT_DIR = "/usr/share/fonts/truetype/dejavu"

# Theme (RGBA) — mirrors web/src/app/globals.css.
_PANEL = (19, 21, 26, 240)
_PANEL_2 = (26, 29, 36, 255)
_BORDER = (255, 255, 255, 30)
_ACCENT = (56, 189, 248, 255)
_PURPLE = (168, 85, 247, 255)
_GREEN = (52, 211, 153, 255)
_WHITE = (237, 237, 237, 255)
_MUTED = (161, 161, 170, 255)
_DIM = (113, 113, 122, 255)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(f"{_FONT_DIR}/{name}", size)
    except OSError:
        return ImageFont.load_default()


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    return int(draw.textlength(text, font=font))


def _fit(draw, text: str, font_fn, max_w: int, start: int, min_size: int = 16):
    """Largest font (from `start` down to min_size) that fits `text` in `max_w`."""
    size = start
    while size > min_size:
        if _text_w(draw, text, font_fn(size)) <= max_w:
            return font_fn(size)
        size -= 2
    return font_fn(min_size)


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for w in text.split():
        trial = f"{cur} {w}".strip()
        if _text_w(draw, trial, font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _panel(size: tuple[int, int], radius: int = 22, accent=_ACCENT, accent_bar: bool = False):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w, h = size
    d.rounded_rectangle([1, 1, w - 2, h - 2], radius=radius, fill=_PANEL, outline=_BORDER, width=2)
    if accent_bar:
        d.rounded_rectangle([0, 0, 8, h], radius=4, fill=accent)
    return img, d


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _strip_prefix(label: str) -> str:
    """Drop a leading "Kind — " / "Kind: " descriptor, keep the real content."""
    for sep in (" — ", " – ", " - "):  # noqa: RUF001 (real em/en dashes in labels)
        if sep in label:
            return label.split(sep, 1)[1].strip()
    return label.strip()


def _split2(text: str, sep: str) -> tuple[str, str]:
    parts = text.split(sep, 1)
    return parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")


def _get(content: dict, *keys: str, default: str = "") -> str:
    for k in keys:
        v = content.get(k)
        if v not in (None, "", []):
            return str(v)
    return default


def _abbr(name: str) -> str:
    name = name.strip()
    return (name[:3]).upper() if name else "—"


# --- layouts -----------------------------------------------------------------

_SCORE_RE = re.compile(r"(.+?)\s*(\d+)\s*[x×X]\s*(\d+)\s*(.+)")  # noqa: RUF001 (score glyph)


def _parse_score(text: str) -> tuple[str, str, str, str] | None:
    m = _SCORE_RE.search(text)
    if m:
        return m.group(1).strip(), m.group(2), m.group(3), m.group(4).strip()
    return None


def _scoreboard(label: str, c: dict) -> bytes:
    home, away = _get(c, "home"), _get(c, "away")
    hs, as_ = _get(c, "home_score", "hs"), _get(c, "away_score", "as")
    if not (home and away):
        parsed = _parse_score(_get(c, "title") or _strip_prefix(label))
        if parsed:
            home, hs, as_, away = parsed
    home, away = home or "Time A", away or "Time B"
    hs, as_ = hs or "0", as_ or "0"
    status = _get(c, "status", default="AO VIVO")

    w, h = 760, 200
    img, d = _panel((w, h), accent_bar=True)
    d.text((40, h / 2 + 8), home, font=_fit(d, home, lambda s: _font(s, True), 230, 34),
           fill=_WHITE, anchor="lm")
    d.text((w - 40, h / 2 + 8), away, font=_fit(d, away, lambda s: _font(s, True), 230, 34),
           fill=_WHITE, anchor="rm")
    d.text((w / 2, h / 2 + 8), f"{hs}  {as_}", font=_font(72, bold=True), fill=_ACCENT,
           anchor="mm")
    if status:
        d.text((w / 2, 34), status.upper(), font=_font(16, bold=True), fill=_PURPLE, anchor="mm")
    return _png(img)


def _score_bug(label: str, c: dict) -> bytes:
    home, away = _get(c, "home"), _get(c, "away")
    hs, as_ = _get(c, "home_score", "hs"), _get(c, "away_score", "as")
    if not (home and away):
        parsed = _parse_score(_get(c, "title", "text") or _strip_prefix(label))
        if parsed:
            home, hs, as_, away = parsed
    text = (
        f"{_abbr(home)} {hs or 0} - {as_ or 0} {_abbr(away)}"
        if home and away
        else _get(c, "text", "title") or _strip_prefix(label)
    )
    w, h = 560, 120
    img, d = _panel((w, h), radius=18, accent_bar=True)
    d.ellipse([34, h / 2 - 7, 48, h / 2 + 7], fill=_GREEN)
    d.text((64, h / 2), text, font=_fit(d, text, lambda s: _font(s, True), w - 96, 40, 20),
           fill=_WHITE, anchor="lm")
    return _png(img)


def _lower_third(label: str, c: dict) -> bytes:
    title = _get(c, "title", "name")
    sub = _get(c, "subtitle", "role", "detail")
    if not title:
        title, sub2 = _split2(_strip_prefix(label), ":")
        sub = sub or sub2
    w, h = 920, 180
    img, d = _panel((w, h), accent_bar=True)
    tf = _fit(d, title, lambda s: _font(s, True), w - 80, 48)
    d.text((44, 70 if sub else 95), title, font=tf, fill=_WHITE, anchor="lm")
    if sub:
        d.text((46, 122), sub, font=_fit(d, sub, _font, w - 80, 28), fill=_ACCENT, anchor="lm")
    return _png(img)


def _stat_card(label: str, c: dict) -> bytes:
    title = _get(c, "title", "stat")
    rows = c.get("rows") if isinstance(c.get("rows"), list) else []
    value = _get(c, "value")
    if not title:
        title, value2 = _split2(_strip_prefix(label), ":")
        value = value or value2
    w, h = 620, 320
    img, d = _panel((w, h))
    d.text((40, 46), title.upper(), font=_fit(d, title.upper(), _font, w - 80, 28, 15),
           fill=_MUTED, anchor="lm")
    d.line([40, 82, w - 40, 82], fill=_BORDER, width=2)
    if rows:
        y = 120
        for row in rows[:4]:
            rl = str(row.get("label", "")) if isinstance(row, dict) else str(row)
            rv = str(row.get("value", "")) if isinstance(row, dict) else ""
            d.text((40, y), rl, font=_fit(d, rl, _font, w - 200, 30, 16), fill=_WHITE, anchor="lm")
            d.text((w - 40, y), rv, font=_font(30, bold=True), fill=_ACCENT, anchor="rm")
            y += 50
    else:
        value = value or title
        d.text((w / 2, h / 2 + 30), value,
               font=_fit(d, value, lambda s: _font(s, True), w - 80, 66, 22), fill=_ACCENT,
               anchor="mm")
    return _png(img)


def _title_card(label: str, c: dict) -> bytes:
    title = _get(c, "title", "text") or _strip_prefix(label)
    sub = _get(c, "subtitle")
    w, h = 1000, 320
    img, d = _panel((w, h))
    bf = _font(60, bold=True)
    lines = _wrap(d, title, bf, w - 120)[:3]
    block = len(lines) * 70 + (40 if sub else 0)
    y = (h - block) / 2 + 35
    for ln in lines:
        d.text((w / 2, y), ln, font=bf, fill=_WHITE, anchor="mm")
        y += 70
    if sub:
        d.text((w / 2, y + 4), sub, font=_fit(d, sub, _font, w - 160, 30), fill=_ACCENT,
               anchor="mm")
    else:
        d.rounded_rectangle([w / 2 - 40, h - 46, w / 2 + 40, h - 40], radius=3, fill=_ACCENT)
    return _png(img)


def _ticker(label: str, c: dict) -> bytes:
    items = c.get("items") if isinstance(c.get("items"), list) else None
    text = "    •    ".join(str(i) for i in items) if items else (
        _get(c, "text", "title") or _strip_prefix(label)
    )
    w, h = 1000, 110
    img, d = _panel((w, h), radius=14)
    d.rounded_rectangle([0, 0, 150, h], radius=14, fill=_ACCENT)
    d.text((75, h / 2), "AGORA", font=_font(22, bold=True), fill=_PANEL, anchor="mm")
    d.text((175, h / 2), text, font=_fit(d, text, _font, w - 200, 30, 18), fill=_WHITE, anchor="lm")
    return _png(img)


def _timer(label: str, c: dict) -> bytes:
    t = _get(c, "time", "value", "text") or _strip_prefix(label)
    w, h = 360, 150
    img, d = _panel((w, h), accent_bar=True)
    d.text((w / 2 + 4, h / 2), t, font=_fit(d, t, lambda s: _font(s, True), w - 80, 72, 28),
           fill=_ACCENT, anchor="mm")
    return _png(img)


def _quote(label: str, c: dict) -> bytes:
    text = _get(c, "text", "quote", "title") or _strip_prefix(label)
    who = _get(c, "attribution", "author", "subtitle")
    w, h = 900, 320
    img, d = _panel((w, h), accent_bar=True)
    d.text((44, 30), "\u201c", font=_font(90, bold=True), fill=_ACCENT, anchor="lt")
    lines = _wrap(d, text, _font(34, bold=True), w - 110)[:4]
    y = 110
    for ln in lines:
        d.text((56, y), ln, font=_font(34, bold=True), fill=_WHITE, anchor="lm")
        y += 46
    if who:
        d.text((56, h - 40), f"\u2014 {who}", font=_font(24), fill=_ACCENT, anchor="lm")
    return _png(img)


def _bullet_list(label: str, c: dict) -> bytes:
    title = _get(c, "title")
    items = c.get("items") if isinstance(c.get("items"), list) else []
    if not items:
        items = [_strip_prefix(label)]
    w, h = 760, 120 + min(len(items), 5) * 56
    img, d = _panel((w, h))
    y = 44
    if title:
        d.text((40, y), title.upper(), font=_font(24, bold=True), fill=_MUTED, anchor="lm")
        y += 52
    for it in items[:5]:
        d.ellipse([42, y - 5, 52, y + 5], fill=_ACCENT)
        d.text((68, y), str(it), font=_fit(d, str(it), _font, w - 100, 30, 18), fill=_WHITE,
               anchor="lm")
        y += 50
    return _png(img)


def _logo_bug(label: str, c: dict) -> bytes:
    text = _get(c, "text", "title") or _strip_prefix(label)
    w, h = 420, 110
    img, d = _panel((w, h), radius=18, accent_bar=True)
    d.text((40, h / 2), text, font=_fit(d, text, lambda s: _font(s, True), w - 70, 36, 20),
           fill=_WHITE, anchor="lm")
    return _png(img)


def _generic(label: str, kind: str, c: dict) -> bytes:
    body = _get(c, "title", "text") or _strip_prefix(label)
    w, h = 700, 200
    img, d = _panel((w, h), accent_bar=True)
    tag = kind.replace("_", " ").upper()
    d.rounded_rectangle([40, 34, 40 + _text_w(d, tag, _font(15, True)) + 24, 64], radius=8,
                        fill=_PANEL_2, outline=_ACCENT, width=1)
    d.text((52, 49), tag, font=_font(15, bold=True), fill=_ACCENT, anchor="lm")
    y = 96
    for ln in _wrap(d, body, _font(30, bold=True), w - 80)[:3]:
        d.text((40, y), ln, font=_font(30, bold=True), fill=_WHITE, anchor="lm")
        y += 38
    return _png(img)


_LAYOUTS = {
    "scoreboard": _scoreboard,
    "score_bug": _score_bug,
    "lower_third": _lower_third,
    "stat_card": _stat_card,
    "title_card": _title_card,
    "ticker": _ticker,
    "timer": _timer,
    "quote": _quote,
    "bullet_list": _bullet_list,
    "logo_bug": _logo_bug,
}


def render(kind: str, label: str, content: dict | None = None) -> bytes:
    """Render an overlay to PNG bytes from its structured `content` (with label
    fallback). Unknown kinds get a generic labeled card."""
    c = content or {}
    fn = _LAYOUTS.get(kind)
    if fn:
        return fn(label, c)
    return _generic(label, kind, c)
