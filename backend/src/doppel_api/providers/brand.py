"""Brand extraction from a URL pasted in the prompt.

When the creator references a company/site (e.g. https://elevata.io), we fetch the
page (+ a few linked stylesheets) and pull a lightweight brand identity: name,
description, the prominent brand colors (theme-color + most-used non-neutral
hexes), and font families. This is folded into research as a structured `brand`
block so the planner can anchor the video's `overlay_style` palette, typography
and energy on the REAL brand instead of a generic theme. Best-effort, never raises.
"""
import re
from collections import Counter
from urllib.parse import urljoin

import httpx

_UA = "Mozilla/5.0 (compatible; DoppelBot/1.0; +https://doppel.app)"
_HEX_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_RGB_RE = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.I | re.S)
_LINK_RE = re.compile(r"<link\b[^>]*>", re.I)
_HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)
_FONT_RE = re.compile(r"font-family\s*:\s*([^;}\"']+)", re.I)


def _expand_hex(h: str) -> str:
    h = h.lower()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return f"#{h}"


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _is_neutral(hex6: str) -> bool:
    """White/black/near-grey — not a brand accent."""
    r, g, b = int(hex6[1:3], 16), int(hex6[3:5], 16), int(hex6[5:7], 16)
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 22:  # low saturation -> grey/white/black
        return True
    return mx < 24 or mn > 236


def _collect_colors(text: str, counter: Counter) -> None:
    for m in _HEX_RE.findall(text):
        counter[_expand_hex(m)] += 1
    for r, g, b in _RGB_RE.findall(text):
        try:
            ri, gi, bi = int(r), int(g), int(b)
        except ValueError:
            continue
        if ri <= 255 and gi <= 255 and bi <= 255:
            counter[_rgb_to_hex(ri, gi, bi)] += 1


def _meta(html: str, key: str, attr: str = "name") -> str:
    m = re.search(
        rf'<meta[^>]+{attr}\s*=\s*["\']{re.escape(key)}["\'][^>]*content\s*=\s*["\']([^"\']+)["\']',
        html, re.I,
    )
    if m:
        return m.group(1).strip()
    m = re.search(
        rf'<meta[^>]+content\s*=\s*["\']([^"\']+)["\'][^>]*{attr}\s*=\s*["\']{re.escape(key)}["\']',
        html, re.I,
    )
    return m.group(1).strip() if m else ""


def _fonts(text: str) -> list[str]:
    out: list[str] = []
    for raw in _FONT_RE.findall(text):
        first = raw.split(",")[0].strip().strip("\"'")
        low = first.lower()
        if first and low not in (
            "inherit", "initial", "unset", "sans-serif", "serif", "monospace",
        ) and not low.startswith("var("):
            out.append(first)
    seen, uniq = set(), []
    for f in out:
        if f.lower() not in seen:
            seen.add(f.lower())
            uniq.append(f)
    return uniq[:3]


def _css_links(html: str, base: str, limit: int) -> list[str]:
    hrefs: list[str] = []
    for tag in _LINK_RE.findall(html):
        if "stylesheet" in tag.lower():
            m = _HREF_RE.search(tag)
            if m:
                hrefs.append(urljoin(base, m.group(1)))
        if len(hrefs) >= limit:
            break
    return hrefs


async def extract_brand(url: str, *, max_css: int = 3) -> dict | None:
    """Fetch a site and distill a brand identity dict, or None on any failure."""
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=True, headers={"User-Agent": _UA}
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
            base = str(resp.url)

            colors: Counter = Counter()
            fonts_src = ""
            for block in _STYLE_RE.findall(html):
                _collect_colors(block, colors)
                fonts_src += "\n" + block
            # inline style attributes
            for inline in re.findall(r'style\s*=\s*["\']([^"\']+)["\']', html, re.I):
                _collect_colors(inline, colors)

            for css_url in _css_links(html, base, max_css):
                try:
                    cr = await client.get(css_url)
                    if cr.status_code == 200:
                        _collect_colors(cr.text, colors)
                        fonts_src += "\n" + cr.text
                except httpx.HTTPError:
                    continue
    except Exception as exc:  # best-effort: never break research
        print(f"brand extract failed for {url}: {exc!r}")
        return None

    title = ""
    tm = _TITLE_RE.search(html)
    if tm:
        title = re.sub(r"\s+", " ", tm.group(1)).strip()
    title = _meta(html, "og:site_name", "property") or title
    description = (
        _meta(html, "description") or _meta(html, "og:description", "property")
    )
    theme = _meta(html, "theme-color")
    og_image = _meta(html, "og:image", "property")

    ranked = [c for c, _ in colors.most_common(40) if not _is_neutral(c)]
    palette: list[str] = []
    if theme:
        tmatch = _HEX_RE.fullmatch(theme.strip())
        if tmatch:
            palette.append(_expand_hex(tmatch.group(1)))
    for c in ranked:
        if c not in palette:
            palette.append(c)
        if len(palette) >= 6:
            break

    fonts = _fonts(fonts_src + "\n" + html)
    if not (palette or title or description):
        return None
    return {
        "url": base,
        "title": title,
        "description": description,
        "theme_color": theme,
        "colors": palette,
        "fonts": fonts,
        "og_image": og_image,
    }


def brief_text(b: dict) -> str:
    """Human-readable brand summary for the research/plan context."""
    lines = [f"BRAND SITE: {b.get('url', '')}"]
    if b.get("title"):
        lines.append(f"- Name/title: {b['title']}")
    if b.get("description"):
        lines.append(f"- About: {b['description']}")
    if b.get("colors"):
        lines.append(f"- Brand colors (most prominent, hex): {', '.join(b['colors'])}")
    if b.get("theme_color"):
        lines.append(f"- Declared theme-color: {b['theme_color']}")
    if b.get("fonts"):
        lines.append(f"- Fonts: {', '.join(b['fonts'])}")
    return "\n".join(lines)
