#!/usr/bin/env python3
"""
wallrus.org static site builder.

Reads markdown briefings from content/briefings/, renders them to HTML,
generates an archive index and RSS feed. Zero external dependencies beyond
Python 3.9+ stdlib + markdown lib.

Usage:
    python3 build.py                # build to dist/
    python3 build.py --serve        # build + local preview on :4000
"""

from __future__ import annotations

import argparse
import datetime
import html
import http.server
import json
import os
import re
import shutil
import sys
from pathlib import Path
from textwrap import dedent

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content" / "briefings"
TEMPLATE_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
DIST_DIR = ROOT / "dist"

SITE_TITLE = "Wallrus Intel"
SITE_URL = "https://intel.wallrus.org"
SITE_DESCRIPTION = "AI-curated intelligence briefings. Bitcoin, geopolitics, AI, macro."


# ---------------------------------------------------------------------------
# Markdown → HTML (minimal, no external deps)
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML-like frontmatter and body from markdown."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    fm_block = text[3:end].strip()
    body = text[end + 3:].strip()
    meta = {}
    for line in fm_block.split("\n"):
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",")]
            meta[key] = val
    return meta, body


def md_to_html(md: str) -> str:
    """Convert markdown to HTML. Handles headers, bullets, bold, links, code, paragraphs."""
    lines = md.split("\n")
    out = []
    in_ul = False
    in_code = False
    code_buf = []

    for line in lines:
        # Fenced code blocks
        if line.strip().startswith("```"):
            if in_code:
                out.append(f'<pre><code>{html.escape(chr(10).join(code_buf))}</code></pre>')
                code_buf = []
                in_code = False
            else:
                if in_ul:
                    out.append("</ul>")
                    in_ul = False
                in_code = True
            continue
        if in_code:
            code_buf.append(line)
            continue

        stripped = line.strip()

        # Empty line
        if not stripped:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            continue

        # Headers
        hm = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if hm:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            level = len(hm.group(1))
            text = inline_format(hm.group(2))
            slug = re.sub(r"[^a-z0-9]+", "-", hm.group(2).lower()).strip("-")
            out.append(f'<h{level} id="{slug}">{text}</h{level}>')
            continue

        # Bullet points
        bm = re.match(r"^[-*]\s+(.*)", stripped)
        if bm:
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline_format(bm.group(1))}</li>")
            continue

        # Horizontal rule
        if re.match(r"^[-*_]{3,}$", stripped):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append("<hr>")
            continue

        # Paragraph
        if in_ul:
            out.append("</ul>")
            in_ul = False
        out.append(f"<p>{inline_format(stripped)}</p>")

    if in_ul:
        out.append("</ul>")
    if in_code:
        out.append(f'<pre><code>{html.escape(chr(10).join(code_buf))}</code></pre>')

    return "\n".join(out)


def inline_format(text: str) -> str:
    """Handle bold, italic, inline code, links."""
    # Inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    # Links
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


# ---------------------------------------------------------------------------
# Category tags
# ---------------------------------------------------------------------------

CAT_SHORT = {
    "bitcoin": "BTC",
    "crypto": "BTC",
    "geopolitics": "GEO",
    "ai": "AI",
    "europe": "EU",
    "macro": "MACRO",
    "notable": "NOTE",
    "oil": "OIL",
    "markets": "MKT",
}


def cat_tags_html(categories: list | str) -> str:
    if isinstance(categories, str):
        categories = [c.strip() for c in categories.split(",")]
    tags = []
    for cat in categories:
        short = CAT_SHORT.get(cat.lower(), cat.upper()[:4])
        tags.append(f'<span class="cat-tag">{html.escape(short)}</span>')
    return " ".join(tags)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def base_html(title: str, body: str, *, is_home: bool = False) -> str:
    nav_class = ' class="active"' if is_home else ""
    return dedent(f"""\
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{html.escape(title)}</title>
        <meta name="description" content="{html.escape(SITE_DESCRIPTION)}">
        <link rel="alternate" type="application/rss+xml" title="{html.escape(SITE_TITLE)}" href="{SITE_URL}/feed.xml">
        <link rel="stylesheet" href="/style.css">
        <link rel="icon" type="image/png" href="/favicon.png">
        <link rel="apple-touch-icon" href="/apple-touch-icon.png">
        <meta property="og:image" content="{SITE_URL}/og-image.png">
        <meta property="og:title" content="{html.escape(title)}">
        <meta property="og:type" content="website">
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap" media="print" onload="this.media='all'">
    </head>
    <body>
        <header>
            <nav>
                <a href="/" class="site-name"><img src="/logo-dark.svg" alt="" class="site-logo" width="28" height="24">WALLRUS<span class="dim">INTEL</span></a>
                <div class="nav-links">
                    <a href="/">Latest</a>
                    <a href="/archive.html">Archive</a>
                    <a href="/feed.xml" class="rss-link">RSS</a>
                    <button class="theme-toggle" onclick="toggleTheme()" aria-label="Toggle theme">dark</button>
                </div>
            </nav>
        </header>
        <main>
    {body}
        </main>
        <footer>
            <p>Wallrus Intel. AI-curated. Not financial advice.</p>
        </footer>
        <script src="/theme.js"></script>
    </body>
    </html>""")


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def load_briefings() -> list[dict]:
    """Load all briefing markdown files, return sorted by date descending."""
    briefings = []
    if not CONTENT_DIR.exists():
        return briefings
    for path in sorted(CONTENT_DIR.glob("*.md"), reverse=True):
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        date_str = meta.get("date", path.stem[:10])
        try:
            date = datetime.date.fromisoformat(date_str)
        except ValueError:
            date = datetime.date.today()
        briefings.append({
            "slug": path.stem,
            "date": date,
            "date_str": date_str,
            "title": meta.get("title", f"Intel Briefing — {date_str}"),
            "categories": meta.get("categories", []),
            "body_md": body,
            "body_html": md_to_html(body),
            "meta": meta,
        })
    briefings.sort(key=lambda b: b["date"], reverse=True)
    return briefings


def extract_headlines(body_md: str) -> list[str]:
    """Extract headline bullets from the ## Headlines section."""
    headlines = []
    in_headlines = False
    for line in body_md.split("\n"):
        if re.match(r"^##\s+Headlines", line, re.IGNORECASE):
            in_headlines = True
            continue
        if in_headlines:
            if line.startswith("## "):
                break
            bm = re.match(r"^[-*]\s+(.*)", line.strip())
            if bm:
                headlines.append(bm.group(1))
    return headlines


def build_briefing_page(b: dict) -> str:
    cats = cat_tags_html(b["categories"]) if b["categories"] else ""
    body = f"""
        <article class="briefing">
            <div class="briefing-meta">
                <time datetime="{b['date_str']}">{b['date'].strftime('%B %d, %Y')}</time>
                {cats}
            </div>
            <h1>{html.escape(b['title'])}</h1>
            <div class="briefing-content">
                {b['body_html']}
            </div>
        </article>"""
    return base_html(f"{b['title']} — {SITE_TITLE}", body)


def build_index(briefings: list[dict]) -> str:
    if not briefings:
        body = '<p class="empty">No briefings yet. Check back soon.</p>'
        return base_html(SITE_TITLE, body, is_home=True)

    latest = briefings[0]
    cats = cat_tags_html(latest["categories"]) if latest["categories"] else ""

    # Latest briefing (full)
    parts = [f"""
        <article class="briefing latest">
            <div class="briefing-meta">
                <time datetime="{latest['date_str']}">{latest['date'].strftime('%B %d, %Y')}</time>
                {cats}
                <span class="label-latest">LATEST</span>
            </div>
            <h1><a href="/{latest['slug']}.html">{html.escape(latest['title'])}</a></h1>
            <div class="briefing-content">
                {latest['body_html']}
            </div>
        </article>"""]

    # Previous briefings (headlines only)
    if len(briefings) > 1:
        parts.append('<section class="previous-briefings"><h2>Previous Briefings</h2>')
        for b in briefings[1:10]:
            headlines = extract_headlines(b["body_md"])
            hl_html = ""
            if headlines:
                hl_items = "".join(f"<li>{inline_format(h)}</li>" for h in headlines[:5])
                hl_html = f"<ul class='headlines-preview'>{hl_items}</ul>"
            b_cats = cat_tags_html(b["categories"]) if b["categories"] else ""
            parts.append(f"""
            <div class="briefing-summary">
                <div class="briefing-meta">
                    <time datetime="{b['date_str']}">{b['date'].strftime('%B %d, %Y')}</time>
                    {b_cats}
                </div>
                <h3><a href="/{b['slug']}.html">{html.escape(b['title'])}</a></h3>
                {hl_html}
            </div>""")
        parts.append("</section>")

    return base_html(SITE_TITLE, "\n".join(parts), is_home=True)


def build_archive(briefings: list[dict]) -> str:
    parts = ['<h1>Archive</h1>', '<div class="archive-list">']
    current_year = None
    for b in briefings:
        year = b["date"].year
        if year != current_year:
            if current_year is not None:
                parts.append("</div>")
            parts.append(f'<h2 class="archive-year">{year}</h2><div class="archive-year-entries">')
            current_year = year
        headlines = extract_headlines(b["body_md"])
        hl_preview = ""
        if headlines:
            hl_preview = f' <span class="archive-headlines">— {html.escape(headlines[0][:80])}</span>'
        cats = cat_tags_html(b["categories"]) if b["categories"] else ""
        parts.append(
            f'<div class="archive-entry">'
            f'<time datetime="{b["date_str"]}">{b["date"].strftime("%b %d")}</time> '
            f'{cats} '
            f'<a href="/{b["slug"]}.html">{html.escape(b["title"])}</a>'
            f'{hl_preview}'
            f'</div>'
        )
    if current_year is not None:
        parts.append("</div>")
    parts.append("</div>")
    return base_html(f"Archive — {SITE_TITLE}", "\n".join(parts))


def build_rss(briefings: list[dict]) -> str:
    items = []
    for b in briefings[:20]:
        items.append(f"""    <item>
      <title>{html.escape(b['title'])}</title>
      <link>{SITE_URL}/{b['slug']}.html</link>
      <guid>{SITE_URL}/{b['slug']}.html</guid>
      <pubDate>{b['date'].strftime('%a, %d %b %Y')} 00:00:00 +0000</pubDate>
      <description>{html.escape(b['body_html'][:500])}</description>
    </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{html.escape(SITE_TITLE)}</title>
    <link>{SITE_URL}</link>
    <description>{html.escape(SITE_DESCRIPTION)}</description>
    <atom:link href="{SITE_URL}/feed.xml" rel="self" type="application/rss+xml"/>
    <language>en-us</language>
{chr(10).join(items)}
  </channel>
</rss>"""


def build_landing() -> str:
    """Build the wallrus.org root landing page."""
    return dedent("""\
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Wallrus</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                background: #0a0a0a;
                color: #b0b0b0;
                font-family: 'IBM Plex Mono', 'JetBrains Mono', 'Fira Code', monospace;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                padding: 2rem;
            }
            .landing {
                text-align: center;
                max-width: 480px;
            }
            .wordmark {
                font-size: 2.5rem;
                font-weight: 700;
                color: #e0e0e0;
                letter-spacing: 0.15em;
                text-transform: uppercase;
                margin-bottom: 1rem;
            }
            .tagline {
                font-size: 0.95rem;
                color: #666;
                margin-bottom: 2.5rem;
                line-height: 1.5;
            }
            .landing a {
                color: #5ba3a8;
                text-decoration: none;
                font-size: 0.9rem;
                border: 1px solid #2a4a4c;
                padding: 0.6rem 1.4rem;
                transition: all 0.2s;
            }
            .landing a:hover {
                background: #5ba3a810;
                border-color: #5ba3a8;
                color: #7cc5ca;
            }
        </style>
    </head>
    <body>
        <div class="landing">
            <div class="wordmark">Wallrus</div>
            <p class="tagline">AI-native trading research.</p>
            <a href="https://intel.wallrus.org">Read the Intel Briefing &rarr;</a>
        </div>
    </body>
    </html>""")


def build():
    """Build the complete site to dist/."""
    # Clean
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)

    # Copy static assets
    if STATIC_DIR.exists():
        for f in STATIC_DIR.iterdir():
            if f.is_file():
                shutil.copy2(f, DIST_DIR / f.name)

    # Load briefings
    briefings = load_briefings()
    print(f"Found {len(briefings)} briefings")

    # Build individual pages
    for b in briefings:
        page = build_briefing_page(b)
        (DIST_DIR / f"{b['slug']}.html").write_text(page, encoding="utf-8")

    # Build index
    (DIST_DIR / "index.html").write_text(build_index(briefings), encoding="utf-8")

    # Build archive
    (DIST_DIR / "archive.html").write_text(build_archive(briefings), encoding="utf-8")

    # Build RSS
    (DIST_DIR / "feed.xml").write_text(build_rss(briefings), encoding="utf-8")

    # Build landing page (for wallrus.org root — separate from intel subdomain)
    landing_dir = DIST_DIR / "landing"
    landing_dir.mkdir()
    (landing_dir / "index.html").write_text(build_landing(), encoding="utf-8")

    # Stats
    total_size = sum(f.stat().st_size for f in DIST_DIR.rglob("*") if f.is_file())
    print(f"Built {len(briefings)} briefings + index + archive + RSS + landing")
    print(f"Total size: {total_size / 1024:.1f} KB")
    print(f"Output: {DIST_DIR}")


def serve(port: int = 4000):
    """Serve dist/ for local preview."""
    os.chdir(DIST_DIR)
    handler = http.server.SimpleHTTPRequestHandler
    server = http.server.HTTPServer(("127.0.0.1", port), handler)
    print(f"Serving at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build wallrus.org")
    parser.add_argument("--serve", action="store_true", help="Build and serve locally")
    parser.add_argument("--port", type=int, default=4000)
    args = parser.parse_args()
    build()
    if args.serve:
        serve(args.port)
