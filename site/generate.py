#!/usr/bin/env python3
"""Generate the static site in docs/ from experiments/*/site-data.json.

No external dependencies (stdlib only). Run from repo root:

    python3 site/generate.py
"""
import html
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = ROOT / "experiments"
DOCS_DIR = ROOT / "docs"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def load_experiments():
    experiments = []
    skipped = []
    for site_data_path in sorted(EXPERIMENTS_DIR.glob("*/site-data.json")):
        data = json.loads(site_data_path.read_text())
        data["_slug"] = site_data_path.parent.name
        if data.get("draft"):
            skipped.append(data["_slug"])
            continue
        experiments.append(data)
    experiments.sort(key=lambda e: e.get("date", ""), reverse=True)
    if skipped:
        print(f"Skipping draft experiment(s) (not published to site): {', '.join(skipped)}")
    return experiments


def esc(value):
    return html.escape(str(value))


def all_results(exp):
    """Flatten every result row across an experiment's result_sets (or its
    legacy single `results` array) - used for index-page summary stats where
    we just want the single best row regardless of which chart it's in."""
    if exp.get("result_sets"):
        return [r for rs in exp["result_sets"] for r in rs["results"]]
    return exp.get("results", [])


def status_badge(status):
    status = status or "complete"
    label = {"in-progress": "In progress", "complete": "Complete"}.get(status, status)
    return f'<span class="badge badge-{esc(status)}">{esc(label)}</span>'


def render_index(experiments):
    template = (TEMPLATES_DIR / "index.html").read_text()
    rows = []
    for i, exp in enumerate(experiments, start=1):
        results = all_results(exp)
        best = max(results, key=lambda r: r["mean"]) if results else None
        headline = f'{esc(best["name"])} &middot; {best["mean"]:.3f}' if best else ""
        rows.append(f"""
        <a class="index-row" href="experiments/{esc(exp['_slug'])}/" data-reveal data-reveal-group="index">
          <span class="index-num">{i:02d}</span>
          <div class="index-main">
            <div class="index-top-line">
              <span class="index-category">{esc(exp.get('category', ''))}</span>
              {status_badge(exp.get('status'))}
            </div>
            <h2 class="index-title">{esc(exp['title'])}</h2>
            <p class="index-summary">{esc(exp['summary'])}</p>
          </div>
          <div class="index-side">
            <span class="index-headline">{headline}</span>
            <span class="index-date">{esc(exp.get('date', ''))}</span>
            <span class="index-arrow">&rarr;</span>
          </div>
        </a>""")
    return template.replace("{{CARDS}}", "\n".join(rows)).replace(
        "{{COUNT}}", str(len(experiments))
    )


def render_result_set(result_set, metric, set_index):
    """Render one chart+table block. `result_set` has {id, title (optional), results}.
    A page can have one or many of these (e.g. reasoning off/on) - each gets its
    own Chart.js instance, paired via a shared data-chart-id attribute so
    chart.js can find them without relying on document order."""
    set_id = result_set.get("id") or f"set-{set_index}"
    results = result_set["results"]

    rows = []
    for r in results:
        rows.append(f"""
        <tr>
          <td>{esc(r['name'])}</td>
          <td>{r['mean']:.4f}</td>
          <td>[{r['ci_low']:.4f}, {r['ci_high']:.4f}]</td>
          <td>{r['n']}</td>
        </tr>""")

    metric_range = metric.get("range")
    if metric_range and len(metric_range) == 2:
        axis_max = metric_range[1]
    else:
        axis_max = round(max((r["ci_high"] for r in results), default=1) * 1.15, 2)

    results_json = json.dumps({
        "labels": [r["name"] for r in results],
        "means": [r["mean"] for r in results],
        "ci_low": [r["ci_low"] for r in results],
        "ci_high": [r["ci_high"] for r in results],
        "ns": [r["n"] for r in results],
        "metricName": metric.get("name", "Score"),
        "axisMax": axis_max,
    })

    title_html = f'<h3 class="result-set-title">{esc(result_set["title"])}</h3>' if result_set.get("title") else ""
    description_html = f'<p class="result-set-description">{esc(result_set["description"])}</p>' if result_set.get("description") else ""
    callout_html = (
        f'<div class="result-callout"><span class="result-callout-label">Behind the numbers</span>'
        f'<p class="result-callout-text">{esc(result_set["callout"])}</p></div>'
        if result_set.get("callout") else ""
    )

    return f"""
      <div class="result-set">
        {title_html}
        <div class="chart-wrap">
          <div class="chart-canvas-box"><canvas data-chart-canvas="{esc(set_id)}"></canvas></div>
          <p class="chart-fallback">Enable JavaScript to see the interactive chart &mdash; figures are in the table below.</p>
          <div class="chart-legend">
            <span><span class="legend-swatch"></span> Mean</span>
            <span><span class="legend-swatch ci"></span> 95% confidence interval</span>
          </div>
        </div>
        <script type="application/json" data-chart-data="{esc(set_id)}">{results_json}</script>

        <table class="results-table">
          <thead>
            <tr><th>Model</th><th>Mean</th><th>95% CI</th><th>n</th></tr>
          </thead>
          <tbody>
            {"".join(rows)}
          </tbody>
        </table>
        {description_html}
        {callout_html}
      </div>"""


def render_example(example):
    """Render one worked example: a trimmed dialog excerpt (as turn-by-turn
    conversation rows, not a raw text blob) plus each model's actual response
    and score, so an abstract judge-score table becomes concrete. Optional -
    only rendered when site-data.json has an `example`."""
    truncated_html = (
        '<div class="convo-turn convo-truncated"><span class="convo-ellipsis">&hellip;</span>'
        '<span class="convo-truncated-label">previous conversation</span></div>'
        if example.get("dialog_truncated") else ""
    )
    turns = "".join(f"""
      <div class="convo-turn convo-{r['speaker'].lower()}">
        <span class="convo-speaker">{esc(r['speaker'])}</span>
        <p class="convo-text">{esc(r['text'])}</p>
      </div>""" for r in example["dialog_turns"])

    responses = "".join(f"""
      <div class="example-response">
        <div class="example-response-head">
          <span class="example-response-model">{esc(r['model'])}</span>
          <span class="example-response-score">score: {r['score']:.1f}</span>
        </div>
        <p class="example-response-text">{esc(r['text'])}</p>
      </div>""" for r in example["responses"])

    return f"""
      <div class="example-block">
        <h3 class="result-set-title">Example dialog</h3>
        <div class="example-card">
          <div class="example-card-section">
            <p class="example-problem"><strong>Problem:</strong> {esc(example['problem'])}</p>
          </div>
          <div class="example-card-section convo">{truncated_html}{turns}
            <div class="convo-turn convo-teacher convo-ground-truth">
              <span class="convo-speaker">Teacher (actual human)</span>
              <p class="convo-text">{esc(example['ground_truth'])}</p>
            </div>
          </div>
          <div class="example-card-section">
            <span class="example-responses-label">Model responses for this turn</span>
            <div class="example-responses">{responses}
            </div>
          </div>
        </div>
      </div>"""


def render_experiment(exp, index):
    template = (TEMPLATES_DIR / "experiment.html").read_text()
    metric = exp.get("metric", {})

    # `result_sets` (a list of {id, title, results}) is the general form, used
    # whenever a page needs more than one chart (e.g. reasoning off/on). A
    # plain `results` array is still supported as shorthand for a single
    # untitled result set.
    result_sets = exp.get("result_sets")
    if result_sets is None:
        result_sets = [{"results": exp["results"]}]

    result_sections = "".join(
        render_result_set(rs, metric, i) for i, rs in enumerate(result_sets)
    )

    example_section = render_example(exp["example"]) if exp.get("example") else ""

    notes = "".join(f"<li>{esc(n)}</li>" for n in exp.get("notes", []))

    # Judge prompt is optional - only experiments using an LLM-judge have one.
    # When present it becomes methodology step 02, pushing Notes to 03;
    # otherwise Notes stays step 02, so numbering is always contiguous.
    judge_prompt = exp.get("judge_prompt")
    if judge_prompt:
        judge_prompt_step = f"""
        <div class="step" data-reveal data-reveal-group="steps">
          <span class="step-num">02</span>
          <div class="step-body">
            <h3>Judge prompt</h3>
            <pre class="judge-prompt">{esc(judge_prompt)}</pre>
          </div>
        </div>"""
        notes_step_num = "03"
    else:
        judge_prompt_step = ""
        notes_step_num = "02"

    out = template
    out = out.replace("{{TITLE}}", esc(exp["title"]))
    out = out.replace("{{SUMMARY}}", esc(exp["summary"]))
    out = out.replace("{{STATUS_BADGE}}", status_badge(exp.get("status")))
    out = out.replace("{{DATE}}", esc(exp.get("date", "")))
    out = out.replace("{{CATEGORY}}", esc(exp.get("category", "")))
    out = out.replace("{{INDEX}}", f"{index:02d}")
    out = out.replace("{{TASK_DESCRIPTION}}", esc(exp.get("task_description", "")))
    out = out.replace("{{METRIC_NAME}}", esc(metric.get("name", "")))
    out = out.replace("{{METRIC_DESCRIPTION}}", esc(metric.get("description", "")))
    out = out.replace("{{DATASET_NAME}}", esc(exp.get("dataset", {}).get("name", "")))
    out = out.replace("{{DATASET_URL}}", esc(exp.get("dataset", {}).get("url", "#")))
    out = out.replace("{{DATASET_LICENSE}}", esc(exp.get("dataset", {}).get("license", "")))
    out = out.replace("{{METHODOLOGY_URL}}", esc(exp.get("methodology_url", "#")))
    takeaways = exp.get("takeaways", [])
    if takeaways:
        # Takeaways may use <strong> for emphasis - trusted content (we author
        # site-data.json ourselves), so not escaped like plain notes text.
        items = "".join(f"<li>{t}</li>" for t in takeaways)
        takeaways_section = f"""
    <section class="section" data-reveal>
      <div class="section-head"><span class="section-num">04</span><h2>Takeaways</h2></div>
      <ul class="takeaways-list">{items}</ul>
    </section>"""
    else:
        takeaways_section = ""

    out = out.replace("{{RESULT_SECTIONS}}", result_sections)
    out = out.replace("{{EXAMPLE_SECTION}}", example_section)
    out = out.replace("{{JUDGE_PROMPT_STEP}}", judge_prompt_step)
    out = out.replace("{{NOTES_STEP_NUM}}", notes_step_num)
    out = out.replace("{{NOTES}}", notes)
    out = out.replace("{{TAKEAWAYS_SECTION}}", takeaways_section)
    return out


def main():
    experiments = load_experiments()
    DOCS_DIR.mkdir(exist_ok=True)

    for asset in ("style.css", "main.js", "chart.js", "theme.js"):
        (DOCS_DIR / asset).write_text((TEMPLATES_DIR / asset).read_text())

    (DOCS_DIR / "index.html").write_text(render_index(experiments))

    published_slugs = set()
    for i, exp in enumerate(experiments, start=1):
        exp_dir = DOCS_DIR / "experiments" / exp["_slug"]
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "index.html").write_text(render_experiment(exp, i))
        published_slugs.add(exp["_slug"])

    # Remove any previously-generated experiment page that's no longer
    # published (draft flipped on, site-data.json deleted, etc.) so stale
    # pages don't linger in docs/.
    docs_experiments_dir = DOCS_DIR / "experiments"
    if docs_experiments_dir.exists():
        for stale_dir in docs_experiments_dir.iterdir():
            if stale_dir.is_dir() and stale_dir.name not in published_slugs:
                shutil.rmtree(stale_dir)
                print(f"Removed stale generated page: docs/experiments/{stale_dir.name}")

    (DOCS_DIR / ".nojekyll").write_text("")
    print(f"Generated site for {len(experiments)} experiment(s) into {DOCS_DIR}")


if __name__ == "__main__":
    main()
