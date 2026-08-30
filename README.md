# neeraj-benchmarks

Open-source benchmark experiments: comparing models, harnesses, and prompting
strategies on real datasets. Results are published as a static site at
https://kn-neeraj.github.io/neeraj-benchmarks/.

## Layout

```
experiments/<slug>/     one self-contained experiment per folder
site/                   static site generator (stdlib-only Python, no deps)
docs/                   generated site, served by GitHub Pages
```

## Adding an experiment

1. Create `experiments/<slug>/` with your code, data pipeline, and a `README.md`
   describing methodology, dataset, and license.
2. Add `experiments/<slug>/site-data.json` summarizing results in this shape:

   ```json
   {
     "id": "...", "title": "...", "summary": "...", "date": "YYYY-MM-DD",
     "status": "in-progress | complete", "category": "...",
     "dataset": {"name": "...", "url": "...", "license": "..."},
     "task_description": "...",
     "metric": {"name": "...", "range": [0, 1], "higher_is_better": true, "description": "..."},
     "results": [{"name": "...", "mean": 0.0, "ci_low": 0.0, "ci_high": 0.0, "n": 0}],
     "notes": ["..."],
     "methodology_url": "https://github.com/kn-neeraj/neeraj-benchmarks/tree/main/experiments/<slug>"
   }
   ```

3. Regenerate the site:

   ```bash
   python3 site/generate.py
   ```

4. Commit `experiments/<slug>/` and the updated `docs/`, then push.

Keep raw/heavy outputs (generations, logs, `.env`) out of git — only the
summarized `site-data.json` needs to be committed for the site.

## GitHub Pages setup

Settings → Pages → Source: Deploy from a branch → `main` / `/docs`.
