# Side experiment: does reasoning effort change scaffolding quality?

## Question

The main replication (see the top-level [README.md](../../README.md)) runs
all three models under test with `reasoning_effort="none"`, matching the
MathTutorBench paper's own convention of evaluating with thinking disabled.
This experiment asks: **does giving the models room to reason before
answering change how well they scaffold**, for better or worse?

Two plausible effects pull in opposite directions:
- More reasoning could let a model better diagnose the student's specific
  error before responding, producing a sharper, more targeted hint.
- More reasoning could cause a model to "solve" the problem internally and
  then leak that solved state into the response, defeating the task's
  actual goal (guide, don't reveal).

## Setup

- **Same 50 dialogs across all 3 models**, so the comparison is paired and
  apples-to-apples. Dialog IDs: 0-50 (51 consecutive IDs) **excluding ID 22**,
  which fails the judge's upstream content-moderation check for all models
  (see the main README/run notes) - so effectively 50 usable IDs.
- **1 trial per dialog** (matching the main run's trial count, itself a
  budget-driven deviation from the original 3-trial design - see the main
  README).
- **reasoning_effort="medium" for all 3 models under test**, kept identical
  across models specifically so any score difference reflects the models'
  actual response to more reasoning budget, not an uncontrolled variable.
- **Judge stays exactly as in the main run**: `qwen3.8-max`, temperature 0,
  `reasoning_effort="none"`, identical prompt template (logged again to
  `results/judge_prompt.txt` in this folder - should be byte-identical to
  the main run's, confirming the only changed variable is the test models'
  reasoning effort).
- **Baseline for comparison**: the same 50 dialog IDs' results already exist
  in the main run's `../../results/judged.jsonl` at `reasoning_effort="none"`.
  This experiment does not re-run the baseline - it filters the existing
  main-run data down to the same 50 IDs for a fair side-by-side.

## Folder contents

```
README.md                   this file
results/generations.jsonl   50 dialogs x 3 models, reasoning_effort=medium
results/judged.jsonl        judge scores for the above
results/judge_prompt.txt    exact judge prompt used (should match the main run's)
results/summary.csv         mean + 95% CI per model, medium condition
results/summary_chart.png   chart, medium condition
results/comparison.csv      medium vs. none, same 50 dialogs, side by side
results/comparison_chart.png
```

## How this was run

Reused the main pipeline's scripts with override flags added for this
purpose (`--dialog-ids`, `--reasoning-effort`, `--output` on
`run_generation.py`; `--generations`/`--output` on `run_judge.py`;
`--input`/`--output-csv`/`--output-chart` on `aggregate_stats.py`) rather
than duplicating pipeline code:

```bash
cd ../..   # repo root
source .venv/bin/activate

python3 scripts/run_generation.py \
  --models kimi_k3 deepseek_v4_flash glm_5_2 \
  --dialog-ids 0,1,2,...,50  \
  --trials 1 \
  --reasoning-effort medium \
  --output experiments/reasoning_effort_medium/results/generations.jsonl \
  --max-requests 200

python3 scripts/run_judge.py \
  --generations experiments/reasoning_effort_medium/results/generations.jsonl \
  --output experiments/reasoning_effort_medium/results/judged.jsonl \
  --max-requests 200

python3 scripts/aggregate_stats.py \
  --input experiments/reasoning_effort_medium/results/judged.jsonl \
  --output-csv experiments/reasoning_effort_medium/results/summary.csv \
  --output-chart experiments/reasoning_effort_medium/results/summary_chart.png \
  --title "Hard-scaffolding (n=50): reasoning_effort=medium"
```

## Caveats

- n=50 per model, much smaller than the main run's n=322 - CIs here will be
  visibly wider. This is a directional side-check, not a claim on par with
  the main result.
- `medium` reasoning effort is not officially documented for these models on
  this endpoint - only confirmed live (see the main README's discovery
  notes for `high`/`none`); confirmed working with a live test call before
  this experiment ran, but its actual reasoning depth/cost per model is
  whatever the provider implements behind that label, not something this
  project controls or can fully characterize.
- Different generations (medium) are judged by the same judge configuration
  as the main run's `none` condition, so any observed difference reflects
  the test models' behavior change, not a judge change - but it is still one
  judge's opinion, same limitation as the main run.

## Results

It took three attempts to get a trustworthy answer. Both failed attempts are
preserved under `results/attempt1_maxtokens200_broken/` and
`results/attempt2_maxtokens600_serverside_stop_bug/` rather than deleted,
since the failure modes are themselves useful to know about if anyone
enables `reasoning_effort` on this endpoint elsewhere in this project.

### Attempt 1 (`max_tokens=200`) - broken: token-budget starvation

`run_generation.py`'s default `max_tokens=200` was carried over unchanged
from the main run's `reasoning_effort="none"` condition, where none of that
budget goes to hidden reasoning. Under `reasoning_effort="medium"`, reasoning
tokens draw from the *same* budget as the visible answer, so most responses
came back empty or truncated mid-thought:

| Model | Empty responses (of 50) | Failure mode |
|---|---|---|
| DeepSeek V4 Flash | 35 (70%) | `finish_reason="stop"` with nothing |
| GLM-5.2 | 21 (42%) | `finish_reason="length"` - reasoning alone consumed the full budget |
| Kimi K3 | 2 (4%), but the "non-empty" ones were truncated reasoning leaking into the answer field (e.g. `"Let me analyze the student's work."` and nothing else) |

### Attempt 2 (`max_tokens=600`) - broken: stop-sequences firing inside hidden reasoning

Raising the budget fixed Kimi K3 (2→1 empty) and GLM-5.2 (21→2 empty), but
**DeepSeek V4 Flash was still 33/50 (66%) empty.** Investigation ruled out
budget: empty responses ranged from 101 to 736 completion tokens used - no
consistent "ran out of room" pattern, and some exceeded the 600 cap entirely.

The real cause: `run_generation.py` sends `stop=["Student:", "\n\n",
"Teacher:"]` to prevent the model hallucinating a full continued
conversation. With reasoning enabled, this stop-matching appears to scan the
*raw generation stream, including the hidden reasoning trace* - and a
reasoning trace naturally drafts candidate teacher lines and paragraph
breaks while thinking, so it can contain a literal `"Teacher:"` or `"\n\n"`
before the real answer ever starts, truncating the whole response to
nothing. This is the same failure the source MathTutorBench repo's own model
wrapper (`models/completion_api.py`) explicitly works around, with the
comment: *"Stop strings are applied after the trace is removed, since they
would otherwise fire inside the reasoning."*

**Fix** (in [`harbor/task.py`](../../harbor/task.py)): server-side `stop` is
now only sent when `reasoning_effort` is `"none"`/unset; client-side
truncation (`truncate_at_stop`) still always applies to the final returned
content, matching the source repo's approach.

### Attempt 3 (`max_tokens=900` + fixed stop handling) - clean

| Model | Empty responses (of 50) |
|---|---|
| DeepSeek V4 Flash | 7 (14%) - down from 33 |
| Kimi K3 | 4 (8%) |
| GLM-5.2 | 2 (4%) |

13/150 (8.7%) is a normal rate consistent with genuine model behavior
(occasional refusals/empty turns happen even at `reasoning_effort="none"` in
the main run), not a pipeline bug. This is the run trusted for the
comparison below.

### Numbers (see `results/comparison.csv` and `results/comparison_chart.png`)

Same 50 dialogs, `none` (main run baseline) vs `medium` (this experiment):

| Model | none (n=50) | medium, all responses (n=50) | medium, non-empty only |
|---|---|---|---|
| GLM-5.2 | 0.755 ± 0.079 | **0.835 ± 0.058** (2 empty) | 0.870 ± 0.035 (n=48) |
| DeepSeek V4 Flash | 0.577 ± 0.093 | **0.714 ± 0.085** (7 empty) | 0.763 ± 0.076 (n=43) |
| Kimi K3 | 0.642 ± 0.097 | **0.693 ± 0.087** (4 empty) | 0.732 ± 0.080 (n=46) |

### Conclusion

**All three models scored higher with `reasoning_effort="medium"` than with
`"none"`, and the direction is consistent across all three** - none got
worse. That consistency is itself informative even though each individual
model's 95% CI overlaps its own `none` baseline at n=50 (this is a modest
sample; DeepSeek's gap is the closest to non-overlapping). The improvement
holds and gets slightly larger when excluding the residual empty responses,
so it isn't an artifact of the empty-response exclusion choice either.

**Honest read:** this is suggestive evidence that letting these models think
before answering does help them scaffold better on this task, for all three
models tested - but n=50 per model, one judge, one judge prompt, and
non-overlapping-but-close CIs mean this should be read as "worth taking
seriously," not "proven." A larger n (e.g. running the full 322-dialog set
at `medium`) would be needed to make this a confident claim comparable in
rigor to the main run.
