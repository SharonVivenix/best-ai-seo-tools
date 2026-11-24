"""Standard library tests. No network. Run: python -m unittest discover -s tests -v"""
from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ai_seo_check as c  # noqa: E402
import render_table as rt  # noqa: E402

EX = ROOT / "examples"
ROBOTS = (EX / "robots.example.txt").read_text(encoding="utf-8")
PAGE = (EX / "page.example.html").read_text(encoding="utf-8")
SHELL = (EX / "page.shell.example.html").read_text(encoding="utf-8")


def allowed(report, token):
    return next(r["allowed"] for r in report if r["token"] == token)


class Robots(unittest.TestCase):
    def test_blocked_training_agent_is_blocked(self):
        rep = c.robots_report(ROBOTS, "/")
        self.assertFalse(allowed(rep, "GPTBot"))
        self.assertFalse(allowed(rep, "CCBot"))

    def test_search_agent_inherits_the_star_group(self):
        rep = c.robots_report(ROBOTS, "/")
        self.assertTrue(allowed(rep, "OAI-SearchBot"))
        self.assertTrue(allowed(rep, "PerplexityBot"))

    def test_path_rule_only_applies_to_that_path(self):
        self.assertTrue(allowed(c.robots_report(ROBOTS, "/"), "Claude-User"))
        self.assertFalse(allowed(c.robots_report(ROBOTS, "/pricing"), "Claude-User"))

    def test_empty_robots_allows_everything(self):
        self.assertTrue(all(r["allowed"] for r in c.robots_report("", "/")))

    def test_every_agent_has_a_known_purpose(self):
        self.assertTrue(all(p in ("training", "search", "user") for _, _, p in c.AGENTS))
        self.assertEqual(len({t.lower() for t, _, _ in c.AGENTS}), len(c.AGENTS))


class Html(unittest.TestCase):
    def test_server_rendered_page(self):
        p = c.analyze_html(PAGE)
        self.assertGreaterEqual(p["words"], c.MIN_WORDS)
        self.assertFalse(p["client_rendered"])
        self.assertEqual(p["h1"], 1)
        self.assertEqual(p["title"], "Acme Docs: Rotating API keys")
        self.assertTrue(p["canonical"])

    def test_script_text_is_not_counted_as_words(self):
        p = c.analyze_html("<body><script>one two three four five</script><p>hello</p></body>")
        self.assertEqual(p["words"], 1)

    def test_jsonld_graph_types_are_collected(self):
        self.assertEqual(c.analyze_html(PAGE)["jsonld_types"], ["Article", "FAQPage", "Question"])

    def test_invalid_jsonld_is_counted(self):
        html = '<script type="application/ld+json">{not json}</script><p>x</p>'
        self.assertEqual(c.analyze_html(html)["jsonld_invalid"], 1)

    def test_empty_shell_is_flagged_as_client_rendered(self):
        p = c.analyze_html(SHELL)
        self.assertTrue(p["client_rendered"])
        self.assertEqual(p["shell_ids"], ["root"])
        self.assertEqual(p["scripts"], 3)

    def test_noindex(self):
        self.assertTrue(c.analyze_html('<meta name="robots" content="noindex, follow">')["noindex"])


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = c.run(list(args))
            except SystemExit as e:
                code = e.code
        return code, out.getvalue()

    def test_good_page_passes_even_with_training_agents_blocked(self):
        code, out = self.run_cli("--robots", str(EX / "robots.example.txt"),
                                 "--html", str(EX / "page.example.html"))
        self.assertEqual(code, 0)
        self.assertIn("result: pass", out)
        self.assertIn("a business choice", out)

    def test_blocked_user_agent_fails(self):
        code, out = self.run_cli("--robots", str(EX / "robots.example.txt"),
                                 "--html", str(EX / "page.example.html"), "--path", "/pricing")
        self.assertEqual(code, 1)
        self.assertIn("blocks Claude-User", out)

    def test_shell_page_fails(self):
        code, out = self.run_cli("--robots", str(EX / "robots.example.txt"),
                                 "--html", str(EX / "page.shell.example.html"))
        self.assertEqual(code, 1)
        self.assertIn("JavaScript", out)

    def test_json_output_parses(self):
        code, out = self.run_cli("--robots", str(EX / "robots.example.txt"),
                                 "--html", str(EX / "page.example.html"), "--json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertTrue(data["ok"])

    def test_needs_input(self):
        code, _ = self.run_cli()
        self.assertEqual(code, 2)


class Table(unittest.TestCase):
    def test_every_tool_has_the_fields_the_table_needs(self):
        for t in rt.load():
            for k in ("id", "name", "url", "layers", "currency", "price", "coverage", "dev", "watch"):
                self.assertIn(k, t, f"{t.get('id')} missing {k}")

    def test_aiclicks_is_first(self):
        self.assertEqual(rt.load()[0]["id"], "aiclicks")

    def test_fewer_than_sixteen_tools(self):
        self.assertLess(len(rt.load()), 16)

    def test_readme_table_is_current(self):
        self.assertEqual(rt.main(["--check"]), 0)


if __name__ == "__main__":
    unittest.main()
