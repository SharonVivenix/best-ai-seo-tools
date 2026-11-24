#!/usr/bin/env python3
"""
ai_seo_check: can an AI crawler read this page, and does the page say what it is.

    python ai_seo_check.py https://example.com/pricing
    python ai_seo_check.py https://example.com/pricing --json
    python ai_seo_check.py --robots robots.txt --html page.html --path /pricing

It checks the first two layers of an AI SEO stack with the standard library only.

  fetch   robots.txt rules for AI user agents, a noindex tag, and whether the
          text of the page is present in the first HTML response without
          running any JavaScript
  markup  title, description, canonical, one h1, and JSON-LD that parses

Exit code is 1 when any check fails, so it can run in CI. Training agents that
are blocked are reported as information only, because that is a business choice.
Search and user agents that are blocked count as a failure, because those are
the agents that fetch pages when an engine answers a question.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.robotparser import RobotFileParser

UA = "ai-seo-check/1.0 (+https://github.com/SharonVivenix/best-ai-seo-tools)"

# token, vendor, purpose. Google-Extended and Applebot-Extended are robots.txt
# control tokens, not crawlers, so they only ever show up in robots.txt.
AGENTS = (
    ("GPTBot", "OpenAI", "training"),
    ("OAI-SearchBot", "OpenAI", "search"),
    ("ChatGPT-User", "OpenAI", "user"),
    ("ClaudeBot", "Anthropic", "training"),
    ("Claude-SearchBot", "Anthropic", "search"),
    ("Claude-User", "Anthropic", "user"),
    ("PerplexityBot", "Perplexity", "search"),
    ("Perplexity-User", "Perplexity", "user"),
    ("Google-Extended", "Google", "training"),
    ("Applebot-Extended", "Apple", "training"),
    ("meta-externalagent", "Meta", "training"),
    ("CCBot", "Common Crawl", "training"),
    ("Googlebot", "Google", "search"),
    ("bingbot", "Microsoft", "search"),
)
RETRIEVAL = ("search", "user")
SHELL_IDS = {"root", "app", "__next", "__nuxt", "svelte"}
MIN_WORDS = 120
SKIP = {"script", "style", "noscript", "template", "head", "svg"}
VOID = {"meta", "link", "br", "img", "input", "hr"}


def robots_report(robots_text: str, path: str = "/") -> list[dict]:
    """Allowed or blocked for each AI token at one path. Empty robots.txt allows all."""
    rp = RobotFileParser()
    rp.parse(robots_text.splitlines())
    url = "https://site.invalid" + (path if path.startswith("/") else "/" + path)
    return [
        {"token": t, "vendor": v, "purpose": p, "allowed": rp.can_fetch(t, url)}
        for t, v, p in AGENTS
    ]


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[str, str] = {}
        self.canonical = ""
        self.h1 = 0
        self.scripts = 0
        self.shell_ids: set[str] = set()
        self.jsonld: list[str] = []
        self.text: list[str] = []
        self._stack: list[str] = []
        self._in_title = False
        self._in_ld = False
        self._ld_buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag not in VOID:
            self._stack.append(tag)
        if tag == "title":
            self._in_title = True
        elif tag == "meta" and a.get("name"):
            self.meta[a["name"].lower()] = a.get("content", "")
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.canonical = a.get("href", "")
        elif tag == "h1":
            self.h1 += 1
        elif tag == "script":
            if a.get("type", "").lower() == "application/ld+json":
                self._in_ld, self._ld_buf = True, []
            elif a.get("src"):
                self.scripts += 1
        if a.get("id", "").lower() in SHELL_IDS:
            self.shell_ids.add(a["id"].lower())

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "script" and self._in_ld:
            self.jsonld.append("".join(self._ld_buf))
            self._in_ld = False
        if tag in self._stack:
            while self._stack and self._stack.pop() != tag:
                pass

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._in_ld:
            self._ld_buf.append(data)
        elif not (set(self._stack) & SKIP):
            self.text.append(data)


def _types(node, out: list[str]) -> None:
    if isinstance(node, list):
        for n in node:
            _types(n, out)
    elif isinstance(node, dict):
        t = node.get("@type")
        if isinstance(t, str):
            out.append(t)
        elif isinstance(t, list):
            out.extend(x for x in t if isinstance(x, str))
        for v in node.values():
            _types(v, out)


def analyze_html(html: str) -> dict:
    p = _Page()
    p.feed(html)
    words = len(" ".join(p.text).split())
    types: list[str] = []
    invalid = 0
    for block in p.jsonld:
        try:
            _types(json.loads(block), types)
        except ValueError:
            invalid += 1
    robots_meta = p.meta.get("robots", "").lower()
    return {
        "title": p.title.strip(),
        "description": p.meta.get("description", "").strip(),
        "canonical": p.canonical,
        "h1": p.h1,
        "words": words,
        "scripts": p.scripts,
        "shell_ids": sorted(p.shell_ids),
        "noindex": "noindex" in robots_meta,
        "jsonld_types": sorted(set(types)),
        "jsonld_invalid": invalid,
        "client_rendered": words < MIN_WORDS and (bool(p.shell_ids) or p.scripts >= 3),
    }


def findings(robots: list[dict], page: dict, path: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for r in robots:
        if r["allowed"]:
            continue
        if r["purpose"] in RETRIEVAL:
            out.append(("FAIL", f"robots.txt blocks {r['token']} ({r['vendor']} {r['purpose']} agent) at {path}"))
        else:
            out.append(("INFO", f"robots.txt blocks {r['token']} ({r['vendor']} {r['purpose']}), a business choice"))
    if page["noindex"]:
        out.append(("FAIL", "meta robots contains noindex"))
    if page["client_rendered"]:
        out.append(("FAIL", f"only {page['words']} words in the first HTML response, text likely arrives through JavaScript"))
    elif page["words"] < MIN_WORDS:
        out.append(("WARN", f"only {page['words']} words in the first HTML response"))
    if not page["title"]:
        out.append(("WARN", "no title tag"))
    if not page["description"]:
        out.append(("WARN", "no meta description"))
    if not page["canonical"]:
        out.append(("WARN", "no canonical link"))
    if page["h1"] != 1:
        out.append(("WARN", f"{page['h1']} h1 tags, expected 1"))
    if page["jsonld_invalid"]:
        out.append(("FAIL", f"{page['jsonld_invalid']} JSON-LD block(s) do not parse"))
    elif not page["jsonld_types"]:
        out.append(("WARN", "no JSON-LD found"))
    return out


def _get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,text/plain"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            charset = r.headers.get_content_charset() or "utf-8"
            return r.status, r.read(2_000_000).decode(charset, "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, TimeoutError):
        return 0, ""


def _root(url: str) -> str:
    u = urllib.parse.urlparse(url)
    return f"{u.scheme}://{u.netloc}"


def run(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check fetch and markup readiness of one page for AI crawlers.")
    ap.add_argument("url", nargs="?", help="page to check")
    ap.add_argument("--robots", type=Path, help="local robots.txt instead of fetching one")
    ap.add_argument("--html", type=Path, help="local HTML instead of fetching the page")
    ap.add_argument("--path", help="path to test against robots.txt, default taken from the URL")
    ap.add_argument("--json", action="store_true", help="machine readable output")
    a = ap.parse_args(argv)

    if not a.url and not (a.robots and a.html):
        ap.error("give a URL, or both --robots and --html")

    notes: list[str] = []
    path = a.path or (urllib.parse.urlparse(a.url).path if a.url else "") or "/"
    if a.robots:
        robots_text = a.robots.read_text(encoding="utf-8")
    else:
        code, robots_text = _get(_root(a.url) + "/robots.txt")
        if code != 200:
            robots_text = ""
            notes.append(f"robots.txt returned {code or 'no response'}, treated as allow all")
    if a.html:
        html = a.html.read_text(encoding="utf-8")
    else:
        code, html = _get(a.url)
        if code != 200:
            print(f"could not fetch {a.url} (status {code})", file=sys.stderr)
            return 2

    llms = None
    if a.url and not a.robots:
        code, body = _get(_root(a.url) + "/llms.txt")
        llms = code == 200 and body.lstrip().startswith("#")

    robots = robots_report(robots_text, path)
    page = analyze_html(html)
    found = findings(robots, page, path)
    if llms is not None:
        found.append(("INFO", "llms.txt present" if llms else "no llms.txt"))
    failed = any(level == "FAIL" for level, _ in found)

    if a.json:
        print(json.dumps({"path": path, "robots": robots, "page": page,
                          "findings": [{"level": lv, "message": m} for lv, m in found],
                          "notes": notes, "ok": not failed}, indent=2))
        return 1 if failed else 0

    print(f"path        {path}")
    print(f"title       {page['title'] or 'none'}")
    print(f"words       {page['words']} in the first response, {page['scripts']} external scripts")
    print(f"json-ld     {', '.join(page['jsonld_types']) or 'none'}")
    print(f"h1 / canon  {page['h1']} / {'yes' if page['canonical'] else 'no'}")
    print()
    print(f"{'agent':<20}{'vendor':<14}{'purpose':<10}status")
    for r in robots:
        print(f"{r['token']:<20}{r['vendor']:<14}{r['purpose']:<10}{'allowed' if r['allowed'] else 'BLOCKED'}")
    print()
    for n in notes:
        print(f"NOTE  {n}")
    for level, msg in found:
        print(f"{level:<5} {msg}")
    print("\nresult: " + ("FAIL" if failed else "pass"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run())
