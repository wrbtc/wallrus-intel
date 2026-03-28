# wallrus-intel

Static publishing repo for `intel.wallrus.org`.

This repo is intentionally simple:

- `build.py` renders markdown briefings in `content/briefings/`
- `static/style.css` provides the terminal-style theme
- GitHub Actions builds `dist/` and deploys it to GitHub Pages on every push to `main`

## Content format

Each briefing is a markdown file under `content/briefings/` named like:

`YYYY-MM-DD-intel-briefing.md`

Frontmatter shape:

```md
---
title: "Wallrus Intel — 2026-03-28"
date: "2026-03-28"
categories: ["bitcoin", "macro", "ai"]
---

## Headlines
- First point
- Second point

## Briefing
Main body here.
```

## Local preview

```bash
python3 build.py --serve
```

That builds to `dist/` and serves a preview at `http://127.0.0.1:4000`.

## Publishing

Push to `main` and GitHub Actions will rebuild and deploy automatically.

Cloudflare DNS / Pages cutover for `wallrus.org` and `intel.wallrus.org` is handled separately from this repo so content publishing stays simple.
