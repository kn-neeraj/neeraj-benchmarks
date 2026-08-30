"""Fetch the MathTutorBench hard-scaffolding subset directly from GitHub.

MathTutorBench is not published as a Hugging Face Hub dataset (confirmed: a
Hub search for "eth-lre/mathtutorbench" / "MathTutorBench" returns no
matches) - the data lives in the eth-lre/mathtutorbench GitHub repo. This
script pulls the raw dataset file and the repo's own license text directly
from GitHub over HTTPS, so the license is read from the source, not assumed.

Reproduces the exact preprocessing in that repo's dataloaders/mathbridge.py:
the last teacher turn in each dialog is held out as the ground-truth
response, and the remaining history is joined into "Student: .../Teacher:
..." lines - so what we send to a model under test is exactly what the
original task would have shown it.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/eth-lre/mathtutorbench/main"
DATASET_URL = f"{GITHUB_RAW_BASE}/datasets/mathdial_bridge_hard.json"
CONFIG_URL = f"{GITHUB_RAW_BASE}/configs/scaffolding_generation_hard.yaml"
README_URL = f"{GITHUB_RAW_BASE}/README.md"

OUTPUT_PATH = REPO_ROOT / "data" / "hard_scaffolding.jsonl"


def _format_dialog_history(conversation_list, cutoff: int) -> str:
    lines = []
    for turn in conversation_list[:cutoff]:
        role = "Student" if turn["user"] == "Student" else "Teacher"
        lines.append(f"{role}: {turn['text']}")
    return "\n".join(lines)


def fetch_and_process() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        print(f"Downloading dataset from {DATASET_URL}")
        raw_data = client.get(DATASET_URL).raise_for_status().json()
        (RAW_DIR / "mathdial_bridge_hard.json").write_text(json.dumps(raw_data, indent=2))

        print(f"Downloading task config from {CONFIG_URL}")
        config_text = client.get(CONFIG_URL).raise_for_status().text
        (RAW_DIR / "scaffolding_generation_hard.yaml").write_text(config_text)

        print(f"Downloading README (for license text) from {README_URL}")
        readme_text = client.get(README_URL).raise_for_status().text
        (RAW_DIR / "SOURCE_README.md").write_text(readme_text)

    license_lines = [
        line for line in readme_text.splitlines()
        if "licen" in line.lower() or "creativecommons.org" in line.lower()
    ]
    license_note_path = RAW_DIR / "LICENSE_NOTICE.txt"
    license_note_path.write_text(
        "License text as found verbatim in the source repo's README.md "
        f"({README_URL}) on the date this was fetched:\n\n" + "\n".join(license_lines) + "\n"
    )
    print(f"License lines found in source README (see {license_note_path}):")
    for line in license_lines:
        print(f"  {line}")

    processed = []
    for i, example in enumerate(raw_data):
        conversation_list = example.get("dialog_history", [])
        cutoff = len(conversation_list) - 1
        if cutoff < 1:
            continue
        ground_truth_turn = conversation_list[cutoff]
        processed.append(
            {
                "dialog_id": i,
                "question": example["problem"],
                "reference_solution": example["reference_solution"],
                "dialog_history": _format_dialog_history(conversation_list, cutoff),
                "ground_truth_response": ground_truth_turn["text"],
            }
        )

    with open(OUTPUT_PATH, "w") as f:
        for row in processed:
            f.write(json.dumps(row) + "\n")

    print(f"Wrote {len(processed)} processed dialogs to {OUTPUT_PATH}")
    if len(processed) != 327:
        print(
            f"NOTE: expected 327 dialogs per the eval design being replicated, got "
            f"{len(processed)}. Proceeding anyway, but flagging the mismatch."
        )


if __name__ == "__main__":
    fetch_and_process()
