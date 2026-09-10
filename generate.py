#!/usr/bin/env python3
"""Regenerate index.html from the GitHub API.

Lists every public repository of the configured owner that has GitHub Pages
enabled, files each one into a category from categories.json, and writes a
static index page.

The output is a pure function of the API response plus categories.json, so a run
that finds nothing new produces a byte-identical file and the workflow commits
nothing.
"""

import html
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
API = "https://api.github.com"


def api_get(path):
    req = urllib.request.Request(API + path)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "pages-index-generator")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_pages_repos(owner):
    """Every public repo of `owner` that serves a GitHub Pages site."""
    repos = []
    page = 1
    while True:
        batch = api_get(f"/users/{owner}/repos?per_page=100&page={page}&sort=full_name")
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return [r for r in repos if r.get("has_pages") and not r.get("archived")]


def site_url(owner, repo):
    """The project Pages URL. A custom domain in `homepage` wins."""
    home = (repo.get("homepage") or "").strip()
    if home.startswith("http") and "github.com" not in home:
        return home
    name = repo["name"]
    if name.lower() == f"{owner.lower()}.github.io":
        return f"https://{name}/"
    return f"https://{owner}.github.io/{name}/"


def classify(repo, config):
    """Explicit listing wins; then keyword match; then the fallback bucket."""
    name = repo["name"]
    for cat in config["categories"]:
        if name in cat.get("repos", []):
            return cat["id"]
    haystack = " ".join([
        name,
        repo.get("description") or "",
        " ".join(repo.get("topics") or []),
        repo.get("language") or "",
    ]).lower()
    best, best_score = None, 0
    for cat in config["categories"]:
        score = sum(1 for kw in cat.get("match", []) if kw in haystack)
        if score > best_score:
            best, best_score = cat["id"], score
    return best or config["fallback"]["id"]


def kst_date(iso):
    if not iso:
        return ""
    dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).strftime("%Y-%m-%d")


def e(text):
    return html.escape(text or "", quote=True)


CSS = """
:root {
  color-scheme: light dark;
  --bg: #f6f7f9;
  --bg-elev: #ffffff;
  --fg: #14171c;
  --fg-muted: #5b6472;
  --fg-faint: #8b93a1;
  --line: #e3e6eb;
  --line-strong: #d0d5dd;
  --accent: #2f6fed;
  --accent-soft: #e8f0ff;
  --shadow: 0 1px 2px rgba(16,24,40,.06), 0 8px 24px -12px rgba(16,24,40,.18);
  --radius: 14px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0e1116;
    --bg-elev: #161b22;
    --fg: #e6edf3;
    --fg-muted: #9aa5b1;
    --fg-faint: #6e7781;
    --line: #262c36;
    --line-strong: #333b46;
    --accent: #6ea8ff;
    --accent-soft: #16243d;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR",
        Roboto, "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
a { color: inherit; text-decoration: none; }
.wrap { max-width: 1140px; margin: 0 auto; padding: 0 20px 72px; }

header.top { padding: 56px 0 28px; }
h1 { margin: 0 0 8px; font-size: 30px; letter-spacing: -.02em; }
h1 .at { color: var(--fg-faint); font-weight: 400; }
.tagline { margin: 0; color: var(--fg-muted); font-size: 15px; }
.meta { margin: 14px 0 0; color: var(--fg-faint); font-size: 13px; }
.meta a { color: var(--accent); }

.controls {
  position: sticky; top: 0; z-index: 10;
  margin: 0 -20px 26px; padding: 12px 20px;
  background: color-mix(in srgb, var(--bg) 88%, transparent);
  backdrop-filter: saturate(180%) blur(12px);
  border-bottom: 1px solid var(--line);
}
.search {
  display: block; width: 100%; padding: 10px 13px;
  font: inherit; color: var(--fg);
  background: var(--bg-elev);
  border: 1px solid var(--line-strong); border-radius: 10px;
}
.search:focus { outline: 2px solid var(--accent); outline-offset: 1px; border-color: transparent; }
.search::placeholder { color: var(--fg-faint); }
.pills { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 10px; }
.pill {
  padding: 5px 12px; font-size: 13px; cursor: pointer;
  color: var(--fg-muted); background: var(--bg-elev);
  border: 1px solid var(--line-strong); border-radius: 999px;
}
.pill:hover { color: var(--fg); }
.pill[aria-pressed="true"] {
  color: var(--accent); background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 45%, transparent);
}
.pill .n { color: var(--fg-faint); margin-left: 5px; font-variant-numeric: tabular-nums; }

section.cat { margin: 0 0 38px; }
section.cat > h2 {
  display: flex; align-items: baseline; gap: 9px;
  margin: 0 0 3px; font-size: 17px; letter-spacing: -.01em;
}
section.cat > h2 .count {
  font-size: 12px; font-weight: 500; color: var(--fg-faint);
  font-variant-numeric: tabular-nums;
}
section.cat > .blurb { margin: 0 0 14px; color: var(--fg-faint); font-size: 13px; }

.grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(272px, 1fr)); }
.card {
  display: flex; flex-direction: column; gap: 8px;
  padding: 15px 16px 13px;
  background: var(--bg-elev);
  border: 1px solid var(--line); border-radius: var(--radius);
  box-shadow: var(--shadow);
  transition: transform .12s ease, border-color .12s ease;
}
.card:hover { transform: translateY(-2px); border-color: color-mix(in srgb, var(--accent) 40%, var(--line)); }
.card h3 { margin: 0; font-size: 15.5px; letter-spacing: -.01em; }
.card h3 a::after { content: ""; position: absolute; inset: 0; }
.card { position: relative; }
.card p { margin: 0; color: var(--fg-muted); font-size: 13.5px; flex: 1; }
.card .foot {
  display: flex; align-items: center; gap: 10px;
  margin-top: 3px; padding-top: 9px;
  border-top: 1px solid var(--line);
  font-size: 12px; color: var(--fg-faint);
}
.card .foot .repo { position: relative; z-index: 1; color: var(--fg-faint); }
.card .foot .repo:hover { color: var(--accent); text-decoration: underline; }
.card .foot .spacer { flex: 1; }
.card .foot time { font-variant-numeric: tabular-nums; }

.empty { display: none; padding: 40px 0; color: var(--fg-faint); text-align: center; }
body.no-results .empty { display: block; }
[hidden] { display: none !important; }

footer.bot {
  margin-top: 44px; padding-top: 20px;
  border-top: 1px solid var(--line);
  color: var(--fg-faint); font-size: 12.5px;
}
footer.bot a { color: var(--accent); }
@media (max-width: 560px) {
  header.top { padding: 34px 0 20px; }
  h1 { font-size: 24px; }
}
"""

JS = """
(function () {
  var search = document.getElementById('search');
  var pills = Array.prototype.slice.call(document.querySelectorAll('.pill'));
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  var sections = Array.prototype.slice.call(document.querySelectorAll('section.cat'));
  var active = 'all';

  function apply() {
    var q = search.value.trim().toLowerCase();
    var shown = 0;
    cards.forEach(function (card) {
      var okCat = active === 'all' || card.dataset.cat === active;
      var okText = !q || card.dataset.search.indexOf(q) !== -1;
      var visible = okCat && okText;
      card.hidden = !visible;
      if (visible) shown++;
    });
    sections.forEach(function (s) {
      s.hidden = !s.querySelector('.card:not([hidden])');
    });
    document.body.classList.toggle('no-results', shown === 0);
  }

  search.addEventListener('input', apply);
  pills.forEach(function (pill) {
    pill.addEventListener('click', function () {
      active = pill.dataset.cat;
      pills.forEach(function (p) {
        p.setAttribute('aria-pressed', String(p === pill));
      });
      apply();
    });
  });
  document.addEventListener('keydown', function (ev) {
    if (ev.key === '/' && document.activeElement !== search) {
      ev.preventDefault();
      search.focus();
    } else if (ev.key === 'Escape' && document.activeElement === search) {
      search.value = '';
      apply();
      search.blur();
    }
  });
})();
"""


def render(config, buckets, owner, total, latest):
    cats = list(config["categories"]) + [config["fallback"]]
    parts = []
    add = parts.append

    add("<!doctype html>")
    add('<html lang="en">')
    add("<head>")
    add('<meta charset="utf-8">')
    add('<meta name="viewport" content="width=device-width, initial-scale=1">')
    add(f"<title>{e(config['title'])} · {e(owner)}</title>")
    add(f'<meta name="description" content="{e(config["tagline"])}">')
    add(f'<meta property="og:title" content="{e(config["title"])} · {e(owner)}">')
    add(f'<meta property="og:description" content="{e(config["tagline"])}">')
    add('<link rel="icon" href="data:image/svg+xml,'
        '%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22%3E'
        '%3Ctext y=%22.9em%22 font-size=%2290%22%3E%F0%9F%97%82%EF%B8%8F%3C/text%3E%3C/svg%3E">')
    add(f"<style>{CSS}</style>")
    add("</head>")
    add("<body>")
    add('<div class="wrap">')

    add('<header class="top">')
    add(f"<h1>{e(config['title'])} <span class=\"at\">· {e(owner)}</span></h1>")
    add(f'<p class="tagline">{e(config["tagline"])}</p>')
    add(f'<p class="meta">{total} live site{"s" if total != 1 else ""} across '
        f'{sum(1 for c in cats if buckets.get(c["id"]))} categories · '
        f'latest activity {e(latest)} (KST) · '
        f'<a href="https://github.com/{e(owner)}">github.com/{e(owner)}</a></p>')
    add("</header>")

    add('<div class="controls">')
    add('<input id="search" class="search" type="search" autocomplete="off" '
        'placeholder="Search sites — press / to focus" aria-label="Search sites">')
    add('<div class="pills">')
    add(f'<button class="pill" data-cat="all" aria-pressed="true">All'
        f'<span class="n">{total}</span></button>')
    for cat in cats:
        items = buckets.get(cat["id"], [])
        if not items:
            continue
        add(f'<button class="pill" data-cat="{e(cat["id"])}" aria-pressed="false">'
            f'{e(cat["icon"])} {e(cat["name"])}<span class="n">{len(items)}</span></button>')
    add("</div>")
    add("</div>")

    add('<main>')
    for cat in cats:
        items = buckets.get(cat["id"], [])
        if not items:
            continue
        add(f'<section class="cat" id="{e(cat["id"])}">')
        add(f'<h2>{e(cat["icon"])} {e(cat["name"])} '
            f'<span class="count">{len(items)}</span></h2>')
        add(f'<p class="blurb">{e(cat["blurb"])}</p>')
        add('<div class="grid">')
        for it in items:
            needle = e(" ".join([it["name"], it["description"], " ".join(it["topics"])]).lower())
            add(f'<article class="card" data-cat="{e(cat["id"])}" data-search="{needle}">')
            add(f'<h3><a href="{e(it["url"])}">{e(it["title"])}</a></h3>')
            add(f'<p>{e(it["description"]) or "&nbsp;"}</p>')
            add('<div class="foot">')
            add(f'<a class="repo" href="{e(it["repo_url"])}">source</a>')
            add('<span class="spacer"></span>')
            add(f'<time datetime="{e(it["pushed"])}">updated {e(it["pushed"])}</time>')
            add("</div>")
            add("</article>")
        add("</div>")
        add("</section>")
    add("</main>")

    add('<p class="empty">No site matches that search.</p>')
    add('<footer class="bot">')
    add(f'Generated from the GitHub API by '
        f'<a href="https://github.com/{e(owner)}/github-pages">github-pages</a>. '
        f'New sites are picked up automatically.')
    add("</footer>")
    add("</div>")
    add(f"<script>{JS}</script>")
    add("</body>")
    add("</html>")
    return "\n".join(parts) + "\n"


def main():
    config = json.loads((ROOT / "categories.json").read_text(encoding="utf-8"))
    owner = os.environ.get("PAGES_OWNER") or config["owner"]

    try:
        repos = fetch_pages_repos(owner)
    except urllib.error.HTTPError as err:
        print(f"GitHub API error {err.code}: {err.reason}", file=sys.stderr)
        return 1

    # This repository indexes the others; it does not index itself.
    repos = [r for r in repos if r["name"] != "github-pages"]

    buckets = {}
    for repo in sorted(repos, key=lambda r: r["name"]):
        entry = {
            "name": repo["name"],
            "title": config.get("titles", {}).get(
                repo["name"], repo["name"].replace("-", " ").title()
            ),
            "description": repo.get("description") or "",
            "topics": repo.get("topics") or [],
            "url": site_url(owner, repo),
            "repo_url": repo["html_url"],
            "pushed": kst_date(repo.get("pushed_at")),
        }
        buckets.setdefault(classify(repo, config), []).append(entry)

    latest = max((e_["pushed"] for items in buckets.values() for e_ in items), default="")
    out = render(config, buckets, owner, len(repos), latest)
    (ROOT / "index.html").write_text(out, encoding="utf-8")

    unsorted = buckets.get(config["fallback"]["id"], [])
    print(f"{len(repos)} site(s) indexed for {owner}")
    for cat in list(config["categories"]) + [config["fallback"]]:
        n = len(buckets.get(cat["id"], []))
        if n:
            print(f"  {cat['name']}: {n}")
    if unsorted:
        print("Unsorted (add to categories.json): "
              + ", ".join(x["name"] for x in unsorted), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
