# github-pages

An index of every GitHub Pages site published from this account.

**https://ctbot000.github.io/github-pages/**

## How it stays current

`generate.py` asks the GitHub API for every public repository that has Pages
enabled, files each one into a category, and writes `index.html`. It takes no
dependencies beyond the standard library.

```bash
python3 generate.py
```

The output is a pure function of the API response plus `categories.json` — a run
that finds nothing new writes a byte-identical file, so the workflow commits
nothing.

[`.github/workflows/update-index.yml`](.github/workflows/update-index.yml) runs
it every 6 hours and commits when the result differs. A repository that has just
turned Pages on does not have to wait for the next tick:

```bash
gh api -X POST repos/ctbot000/github-pages/dispatches -f event_type=pages-changed
```

## Categories

`categories.json` is the only thing to edit by hand. Each category carries:

- `repos` — an explicit list, which always wins.
- `match` — keywords tried against the repo name, description, topics and
  language when the name is not listed.

A new site that matches nothing lands in **Unsorted** rather than being dropped,
and `generate.py` names it on stderr so it is easy to file.

`titles` overrides the name shown on a card, for the cases where
`some-repo-name` does not title-case well.
