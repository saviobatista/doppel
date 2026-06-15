"""Render design-element overlays (scoreboards, stat cards, lower-thirds, ...) to PNG.

These are the broadcast-style graphics the plan references in scene `overlays`.
Templated with Pillow (crisp text, no AI artifacts) but **theme-driven**: every
plan emits an `overlay_style` (palette, typography, treatment, corners) that the
planner derives from the requested look, so the same kind renders very
differently per video — vibrant green/yellow bold-sports here, moody neon there.

Data-driven too: each overlay's structured `content` carries the REAL plan data
(team names, scores, stat values). When `content` is absent we parse the human
`label`, and finally fall back to a generic card — so it never fails the build.

Depth comes from gradient/glass fills, a soft drop shadow and (for the neon
treatment) an accent glow, composited on a padded transparent canvas.
"""
import io
import os
import re
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RGBA = tuple[int, int, int, int]

_DEJAVU = "/usr/share/fonts/truetype/dejavu"
_APP = "/usr/share/fonts/truetype/app"
_LIBERATION = "/usr/share/fonts/truetype/liberation"

# Font roles -> ordered candidate paths (first that exists wins; DejaVu always
# exists as the final fallback). The bold display fonts are fetched in the image
# build; if a download was skipped the renderer degrades gracefully.
_FONT_ROLES: dict[str, list[str]] = {
    "heavy": [
        f"{_APP}/Anton-Regular.ttf",
        f"{_APP}/BebasNeue-Regular.ttf",
        f"{_APP}/ArchivoBlack-Regular.ttf",
        f"{_DEJAVU}/DejaVuSans-Bold.ttf",
    ],
    "strong": [
        f"{_APP}/ArchivoBlack-Regular.ttf",
        f"{_APP}/Oswald[wght].ttf",
        f"{_LIBERATION}/LiberationSans-Bold.ttf",
        f"{_DEJAVU}/DejaVuSans-Bold.ttf",
    ],
    "clean": [
        f"{_LIBERATION}/LiberationSans-Bold.ttf",
        f"{_DEJAVU}/DejaVuSans-Bold.ttf",
    ],
    "clean_reg": [
        f"{_LIBERATION}/LiberationSans-Regular.ttf",
        f"{_DEJAVU}/DejaVuSans.ttf",
    ],
}

_font_path_cache: dict[str, str] = {}
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _role_path(role: str) -> str:
    if role not in _font_path_cache:
        chosen = f"{_DEJAVU}/DejaVuSans-Bold.ttf"
        for p in _FONT_ROLES.get(role, []):
            if os.path.exists(p):
                chosen = p
                break
        _font_path_cache[role] = chosen
    return _font_path_cache[role]


def _rfont(role: str, size: int) -> ImageFont.FreeTypeFont:
    key = (role, size)
    if key not in _font_cache:
        try:
            _font_cache[key] = ImageFont.truetype(_role_path(role), size)
        except OSError:
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


# --- theme -------------------------------------------------------------------

_DEFAULT = {
    "primary": "#38bdf8",
    "accent": "#38bdf8",
    "secondary": "#a855f7",
    "bg": "#13151a",
    "bg2": "#1a1d24",
    "text": "#ededed",
    "muted": "#a1a1aa",
    "treatment": "gradient",
    "corner": "rounded",
    "font": "bold",
}

_CORNER = {"sharp": 6, "rounded": 24, "pill": 48}
# (display_role, body_role) per font preference.
_FONTS = {
    "heavy": ("heavy", "strong"),
    "condensed": ("heavy", "strong"),
    "sport": ("heavy", "strong"),
    "bold": ("strong", "clean"),
    "clean": ("clean", "clean_reg"),
    "minimal": ("clean", "clean_reg"),
}


def _hex(value: str, default: RGBA, alpha: int = 255) -> RGBA:
    s = str(value or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) == 6:
        try:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), alpha)
        except ValueError:
            return default
    return default


@dataclass
class Theme:
    primary: RGBA
    accent: RGBA
    secondary: RGBA
    bg: RGBA
    bg2: RGBA
    text: RGBA
    muted: RGBA
    border: RGBA
    treatment: str
    corner: int
    display_role: str
    body_role: str

    def display(self, size: int) -> ImageFont.FreeTypeFont:
        return _rfont(self.display_role, size)

    def body(self, size: int) -> ImageFont.FreeTypeFont:
        return _rfont(self.body_role, size)


def theme_from(style: dict | None, accent_override: str | None = None) -> Theme:
    s = {**_DEFAULT, **(style or {})}
    accent = _hex(accent_override or s["accent"], _hex(_DEFAULT["accent"], (56, 189, 248, 255)))
    display_role, body_role = _FONTS.get(str(s.get("font", "bold")), ("strong", "clean"))
    text = _hex(s["text"], (237, 237, 237, 255))
    return Theme(
        primary=_hex(s["primary"], (56, 189, 248, 255)),
        accent=accent,
        secondary=_hex(s["secondary"], (168, 85, 247, 255)),
        bg=_hex(s["bg"], (19, 21, 26, 255)),
        bg2=_hex(s["bg2"], (26, 29, 36, 255)),
        text=text,
        muted=_hex(s["muted"], (161, 161, 170, 255)),
        border=(text[0], text[1], text[2], 38),
        treatment=str(s.get("treatment", "gradient")),
        corner=_CORNER.get(str(s.get("corner", "rounded")), 24),
        display_role=display_role,
        body_role=body_role,
    )


_THEME_DEFAULT = theme_from(None)

# --- drawing helpers ---------------------------------------------------------

_PAD = 44  # transparent margin around the panel for shadow / glow


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    return int(draw.textlength(text, font=font))


def _fit(draw, text: str, font_fn, max_w: int, start: int, min_size: int = 16):
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


def _v_gradient(size: tuple[int, int], top: RGBA, bottom: RGBA) -> Image.Image:
    _w, h = size
    grad = Image.new("RGBA", (1, max(1, h)))
    for y in range(max(1, h)):
        t = y / max(1, h - 1)
        grad.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(4)))
    return grad.resize(size)


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    w, h = size
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    return mask


def _panel(size: tuple[int, int], theme: Theme, accent: RGBA | None = None,
           accent_bar: bool = False):
    """A themed card surface (gradient/glass/solid) + border + optional accent bar.
    Returns (panel_image, draw) at the panel's own size — layouts draw on top."""
    w, h = size
    acc = accent or theme.accent
    radius = min(theme.corner, h // 2)

    if theme.treatment in ("gradient", "neon"):
        fill = _v_gradient(size, theme.bg2, theme.bg)
    elif theme.treatment == "glass":
        fill = Image.new("RGBA", size, (theme.bg[0], theme.bg[1], theme.bg[2], 205))
    else:  # solid / outline
        fill = Image.new("RGBA", size, theme.bg)

    img = Image.new("RGBA", size, (0, 0, 0, 0))
    img.paste(fill, (0, 0), _rounded_mask(size, radius))
    d = ImageDraw.Draw(img)

    # top sheen for depth
    d.line([radius, 2, w - radius, 2], fill=(255, 255, 255, 36), width=2)
    # border (brighter accent edge for outline/neon)
    edge = (acc[0], acc[1], acc[2], 150) if theme.treatment in ("outline", "neon") else theme.border
    d.rounded_rectangle([1, 1, w - 2, h - 2], radius=radius, outline=edge, width=2)

    if accent_bar:
        bar = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(bar).rounded_rectangle([0, 0, 12, h - 1], radius=6, fill=acc)
        img.alpha_composite(Image.composite(bar, Image.new("RGBA", size, (0, 0, 0, 0)),
                                            _rounded_mask(size, radius)))
        d = ImageDraw.Draw(img)
    return img, d


def _finish(panel: Image.Image, theme: Theme, accent: RGBA | None = None) -> bytes:
    """Composite the panel onto a padded canvas with a soft drop shadow (and an
    accent glow for the neon treatment), then encode PNG."""
    acc = accent or theme.accent
    w, h = panel.size
    radius = min(theme.corner, h // 2)
    canvas = Image.new("RGBA", (w + 2 * _PAD, h + 2 * _PAD), (0, 0, 0, 0))

    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [_PAD, _PAD + 10, _PAD + w, _PAD + h + 10], radius=radius, fill=(0, 0, 0, 170))
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(20)))

    if theme.treatment == "neon":
        glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle(
            [_PAD - 2, _PAD - 2, _PAD + w + 2, _PAD + h + 2], radius=radius,
            outline=(acc[0], acc[1], acc[2], 220), width=7)
        canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(12)))

    canvas.alpha_composite(panel, (_PAD, _PAD))
    buf = io.BytesIO()
    canvas.save(buf, "PNG")
    return buf.getvalue()


def _chip(d: ImageDraw.ImageDraw, xy, text: str, font, fg: RGBA, bg: RGBA, pad: int = 12):
    x, y = xy
    tw = _text_w(d, text, font)
    asc, desc = font.getmetrics()
    th = asc + desc
    d.rounded_rectangle([x, y, x + tw + 2 * pad, y + th + 10], radius=(th + 10) // 2, fill=bg)
    d.text((x + pad, y + 5), text, font=font, fill=fg)
    return x + tw + 2 * pad


# --- parsing helpers ---------------------------------------------------------

def _strip_prefix(label: str) -> str:
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


_SCORE_RE = re.compile(r"(.+?)\s*(\d+)\s*[x×X]\s*(\d+)\s*(.+)")  # noqa: RUF001 (score glyph)


def _parse_score(text: str) -> tuple[str, str, str, str] | None:
    m = _SCORE_RE.search(text)
    if m:
        return m.group(1).strip(), m.group(2), m.group(3), m.group(4).strip()
    return None


# --- layouts -----------------------------------------------------------------

def _scoreboard(label: str, c: dict, t: Theme) -> bytes:
    home, away = _get(c, "home"), _get(c, "away")
    hs, as_ = _get(c, "home_score", "hs"), _get(c, "away_score", "as")
    if not (home and away):
        parsed = _parse_score(_get(c, "title") or _strip_prefix(label))
        if parsed:
            home, hs, as_, away = parsed
    home, away = home or "Time A", away or "Time B"
    hs, as_ = hs or "0", as_ or "0"
    status = _get(c, "status", default="AO VIVO")

    w, h = 780, 220
    img, d = _panel((w, h), t, accent_bar=True)
    # status pill (top center) with live dot
    sf = t.body(18)
    su = status.upper()
    pill_w = _text_w(d, su, sf) + 64
    px = (w - pill_w) / 2
    sec = (t.secondary[0], t.secondary[1], t.secondary[2], 230)
    d.rounded_rectangle([px, 20, px + pill_w, 56], radius=18, fill=sec)
    d.ellipse([px + 18, 31, px + 32, 45], fill=(239, 68, 68, 255))
    d.text((px + 42, 38), su, font=sf, fill=t.text, anchor="lm")
    # teams + big score
    d.text((44, h / 2 + 22), home.upper(), font=_fit(d, home.upper(), t.body, 240, 40, 22),
           fill=t.text, anchor="lm")
    d.text((w - 44, h / 2 + 22), away.upper(), font=_fit(d, away.upper(), t.body, 240, 40, 22),
           fill=t.text, anchor="rm")
    d.text((w / 2, h / 2 + 26), f"{hs} : {as_}", font=t.display(86), fill=t.accent, anchor="mm")
    return _finish(img, t)


def _score_bug(label: str, c: dict, t: Theme) -> bytes:
    home, away = _get(c, "home"), _get(c, "away")
    hs, as_ = _get(c, "home_score", "hs"), _get(c, "away_score", "as")
    if not (home and away):
        parsed = _parse_score(_get(c, "title", "text") or _strip_prefix(label))
        if parsed:
            home, hs, as_, away = parsed
    w, h = 560, 124
    img, d = _panel((w, h), t, accent_bar=True)
    if home and away:
        x = 36
        d.ellipse([x, h / 2 - 7, x + 14, h / 2 + 7], fill=(52, 211, 153, 255))
        x += 30
        d.text((x, h / 2), _abbr(home), font=t.display(40), fill=t.text, anchor="lm")
        d.text((w / 2, h / 2), f"{hs or 0} - {as_ or 0}", font=t.display(46),
               fill=t.accent, anchor="mm")
        d.text((w - 36, h / 2), _abbr(away), font=t.display(40), fill=t.text, anchor="rm")
    else:
        txt = _get(c, "text", "title") or _strip_prefix(label)
        d.text((40, h / 2), txt, font=_fit(d, txt, t.display, w - 80, 40, 20),
               fill=t.text, anchor="lm")
    return _finish(img, t)


def _lower_third(label: str, c: dict, t: Theme) -> bytes:
    title = _get(c, "title", "name")
    sub = _get(c, "subtitle", "role", "detail")
    if not title:
        title, sub2 = _split2(_strip_prefix(label), ":")
        sub = sub or sub2
    w, h = 940, 190
    img, d = _panel((w, h), t, accent_bar=True)
    tf = _fit(d, title.upper(), t.display, w - 90, 60, 30)
    d.text((46, 74 if sub else 100), title.upper(), font=tf, fill=t.text, anchor="lm")
    if sub:
        d.text((48, 132), sub, font=_fit(d, sub, t.body, w - 90, 30), fill=t.accent, anchor="lm")
    return _finish(img, t)


def _stat_card(label: str, c: dict, t: Theme) -> bytes:
    title = _get(c, "title", "stat")
    rows = c.get("rows") if isinstance(c.get("rows"), list) else []
    value = _get(c, "value")
    if not title:
        title, value2 = _split2(_strip_prefix(label), ":")
        value = value or value2
    n = min(len(rows), 4)
    w, h = 640, (118 + n * 54 + 28) if rows else 300
    img, d = _panel((w, h), t)
    d.text((40, 50), title.upper(), font=_fit(d, title.upper(), t.body, w - 80, 30, 16),
           fill=t.muted, anchor="lm")
    d.line([40, 90, w - 40, 90], fill=t.border, width=2)
    if rows:
        y = 128
        for row in rows[:4]:
            rl = str(row.get("label", "")) if isinstance(row, dict) else str(row)
            rv = str(row.get("value", "")) if isinstance(row, dict) else ""
            d.text((40, y), rl, font=_fit(d, rl, t.body, w - 220, 32, 16), fill=t.text, anchor="lm")
            d.text((w - 40, y), rv, font=t.display(34), fill=t.accent, anchor="rm")
            y += 54
    else:
        value = value or title
        d.text((w / 2, h / 2 + 36), value,
               font=_fit(d, value, t.display, w - 80, 92, 28), fill=t.accent, anchor="mm")
    return _finish(img, t)


def _title_card(label: str, c: dict, t: Theme) -> bytes:
    title = _get(c, "title", "text") or _strip_prefix(label)
    sub = _get(c, "subtitle")
    w, h = 1000, 340
    img, d = _panel((w, h), t)
    bf = _fit(d, title.upper(), t.display, w - 110, 76, 40)
    lines = _wrap(d, title.upper(), bf, w - 120)[:3]
    lh = int((bf.getmetrics()[0] + bf.getmetrics()[1]) * 1.02)
    block = len(lines) * lh + (44 if sub else 0)
    y = (h - block) / 2 + lh / 2
    for ln in lines:
        d.text((w / 2, y), ln, font=bf, fill=t.text, anchor="mm")
        y += lh
    if sub:
        d.text((w / 2, y + 6), sub, font=_fit(d, sub, t.body, w - 160, 32),
               fill=t.accent, anchor="mm")
    else:
        d.rounded_rectangle([w / 2 - 46, h - 50, w / 2 + 46, h - 42], radius=4, fill=t.accent)
    return _finish(img, t)


def _ticker(label: str, c: dict, t: Theme) -> bytes:
    items = c.get("items") if isinstance(c.get("items"), list) else None
    text = "    •    ".join(str(i) for i in items) if items else (
        _get(c, "text", "title") or _strip_prefix(label))
    w, h = 1000, 116
    img, d = _panel((w, h), t)
    tag = "AGORA"
    tw = _text_w(d, tag, t.display(26)) + 70
    d.rounded_rectangle([0, 0, tw, h], radius=min(t.corner, h // 2), fill=t.accent)
    d.text((tw / 2, h / 2), tag, font=t.display(26), fill=t.bg, anchor="mm")
    d.text((tw + 28, h / 2), text, font=_fit(d, text, t.body, w - tw - 56, 32, 18),
           fill=t.text, anchor="lm")
    return _finish(img, t)


def _timer(label: str, c: dict, t: Theme) -> bytes:
    val = _get(c, "time", "value", "text") or _strip_prefix(label)
    w, h = 380, 160
    img, d = _panel((w, h), t, accent_bar=True)
    d.text((w / 2 + 6, h / 2), val, font=_fit(d, val, t.display, w - 80, 84, 30),
           fill=t.accent, anchor="mm")
    return _finish(img, t)


def _quote(label: str, c: dict, t: Theme) -> bytes:
    text = _get(c, "text", "quote", "title") or _strip_prefix(label)
    who = _get(c, "attribution", "author", "subtitle")
    w, h = 920, 340
    img, d = _panel((w, h), t, accent_bar=True)
    d.text((46, 26), "\u201c", font=t.display(100), fill=t.accent, anchor="lt")
    qf = t.body(36)
    lines = _wrap(d, text, qf, w - 120)[:4]
    y = 120
    for ln in lines:
        d.text((58, y), ln, font=qf, fill=t.text, anchor="lm")
        y += 50
    if who:
        d.text((58, h - 42), f"\u2014 {who}", font=t.body(26), fill=t.accent, anchor="lm")
    return _finish(img, t)


def _bullet_list(label: str, c: dict, t: Theme) -> bytes:
    title = _get(c, "title")
    items = c.get("items") if isinstance(c.get("items"), list) else []
    if not items:
        items = [_strip_prefix(label)]
    n = min(len(items), 5)
    w, h = 780, 130 + n * 60
    img, d = _panel((w, h), t)
    y = 48
    if title:
        d.text((40, y), title.upper(), font=t.display(28), fill=t.muted, anchor="lm")
        y += 58
    for it in items[:5]:
        d.rounded_rectangle([40, y - 7, 54, y + 7], radius=4, fill=t.accent)
        d.text((70, y), str(it), font=_fit(d, str(it), t.body, w - 100, 32, 18),
               fill=t.text, anchor="lm")
        y += 54
    return _finish(img, t)


def _logo_bug(label: str, c: dict, t: Theme) -> bytes:
    text = _get(c, "text", "title") or _strip_prefix(label)
    w, h = 440, 116
    img, d = _panel((w, h), t, accent_bar=True)
    d.text((42, h / 2), text, font=_fit(d, text, t.display, w - 76, 40, 22),
           fill=t.text, anchor="lm")
    return _finish(img, t)


def _generic(label: str, kind: str, c: dict, t: Theme) -> bytes:
    body = _get(c, "title", "text") or _strip_prefix(label)
    w, h = 720, 210
    img, d = _panel((w, h), t, accent_bar=True)
    tag = kind.replace("_", " ").upper()
    _chip(d, (40, 34), tag, t.body(16), t.accent, (t.accent[0], t.accent[1], t.accent[2], 40))
    y = 100
    bf = t.display(34)
    for ln in _wrap(d, body.upper(), bf, w - 80)[:3]:
        d.text((40, y), ln, font=bf, fill=t.text, anchor="lm")
        y += 42
    return _finish(img, t)


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


def render(
    kind: str,
    label: str,
    content: dict | None = None,
    theme: dict | None = None,
    accent: str | None = None,
) -> bytes:
    """Render an overlay to PNG bytes from its structured `content`, styled by the
    plan's `theme` (overlay_style). Unknown kinds get a generic labeled card."""
    c = content or {}
    th = theme_from(theme, accent) if (theme or accent) else _THEME_DEFAULT
    fn = _LAYOUTS.get(kind)
    if fn:
        return fn(label, c, th)
    return _generic(label, kind, c, th)
