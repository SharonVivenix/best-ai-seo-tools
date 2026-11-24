#!/usr/bin/env python3
"""
Regenerate the comparison table in README.md from tools.yaml.

    python render_table.py                 print the table
    python render_table.py --write         rewrite the block between the markers
    python render_table.py --check         exit 1 when README.md is stale
    python render_table.py --layer measure list tools in one layer, cheapest first

The list is organized by the layer of an AI SEO stack a tool works on, not by
price or feature count. Edit one YAML entry and run --write.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "tools.yaml"
README = ROOT / "README.md"
START, END = "<!-- TABLE:START -->", "<!-- TABLE:END -->"

LAYERS = {
    "fetch": "Fetch",
    "markup": "Markup",
    "measure": "Measure",
    "create": "Create",
    "data": "Data",
}


def load() -> list[dict]:
    tools = yaml.safe_load(DATA.read_text(encoding="utf-8"))
    for t in tools:
        bad = set(t["layers"]) - set(LAYERS)
        if bad:
            raise SystemExit(f"{t['id']}: unknown layer {sorted(bad)}, choose from {list(LAYERS)}")
    return tools


def price_cell(t: dict) -> str:
    p = t.get("price")
    if p is None:
        return "Not listed"
    if p == 0:
        return "Free"
    num = f"{p:g}" if p == int(p) else f"{p:.2f}"
    cell = f"{t['currency']}{num}/mo"
    if t.get("price_note"):
        cell += f" ({t['price_note']})"
    return cell


def table(tools: list[dict]) -> str:
    head = ["Tool", "Layers", "Starts at", "What it reads or does", "Developer surface", "Watch out for"]
    rows = [
        "| " + " | ".join(head) + " |",
        "| " + " | ".join("---" for _ in head) + " |",
    ]
    for t in tools:
        layers = ", ".join(LAYERS[x] for x in LAYERS if x in t["layers"])
        cells = [f"[{t['name']}]({t['url']})", layers, price_cell(t), t["coverage"], t["dev"], t["watch"]]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def splice(text: str, body: str) -> str:
    a, b = text.index(START) + len(START), text.index(END)
    return text[:a] + "\n" + body + "\n" + text[b:]


def by_layer(tools: list[dict], layer: str) -> int:
    if layer not in LAYERS:
        print(f"unknown layer {layer!r}, choose from {list(LAYERS)}", file=sys.stderr)
        return 2
    fit = [t for t in tools if layer in t["layers"]]
    fit.sort(key=lambda t: (t.get("price") is None, t.get("price") or 0))
    for t in fit:
        print(f"{t['name']:<24} {price_cell(t)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--layer", metavar="NAME")
    a = ap.parse_args(argv)
    tools = load()

    if a.layer:
        return by_layer(tools, a.layer)
    body = table(tools)
    if not (a.write or a.check):
        print(body)
        return 0

    text = README.read_text(encoding="utf-8")
    new = splice(text, body)
    if a.check:
        if new != text:
            print("README table is stale, run: python render_table.py --write", file=sys.stderr)
            return 1
        print("README table matches tools.yaml")
        return 0
    README.write_text(new, encoding="utf-8", newline="\n")
    print("README table updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
