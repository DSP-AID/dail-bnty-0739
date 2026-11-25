#!/usr/bin/env python3
"""Runs this harness on the PLE dev set, as far as this machine can reach it.

    python3 eval/run.py            # replay: offline, no keys (default)
    python3 eval/run.py --mode local   [--out runs-local]  # live smoke runs
    python3 eval/run.py --mode harbor  [--tasks-dir DIR]   # official runner
    python3 eval/run.py --probe        # refresh the HF gate evidence

Modes:
  replay  Rebuilds `artifacts/dev_results.json` from the committed evidence
    (`runs/*/metrics.json`, `runs/kit-check.json`, `samples/*`) plus the
    recorded Hugging Face gate probe in `artifacts/hf_gate.json`. Needs no
    network and no API keys, so a clean machine reproduces it exactly.
  local   Runs `runner_local.py` live on every sample task with instruction.md
    against your own OpenAI-compatible endpoint (OPENAI_BASE_URL / MODEL_NAME
    / OPENAI_API_KEY), then replays those runs into dev_results.json.
  harbor  Delegates to the official `eval/run.py` from the ple repo
    ($PLE_REPO, default ~/repos/ple-official), which downloads the 29 dev
    tasks from Hugging Face and needs Docker + Harbor. Without HF access the
    task folders return 401 (see artifacts/hf_gate.json) and this mode says so.

The full 29-task dev set is gated behind Hugging Face access to
`google/physical-engineerings-last-exam`; this machine has no HF token, so
every *accessible* task (the three public sample tasks) is run and the gate
itself is recorded as evidence instead of invented scores.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
HF_BASE = "https://huggingface.co/datasets/google/physical-engineerings-last-exam"
GATE_FILES = ["task.toml", "instruction.md", "release.json", "eval.yaml"]


def dev_set_tasks() -> list[dict]:
  """Parses the pinned task list out of eval/dev_set.yaml (no yaml import)."""
  text = (ROOT / "eval" / "dev_set.yaml").read_text()
  tasks, cur = [], None
  for line in text.splitlines():
    if line.startswith("- id: "):
      cur = {"id": line.split(" ", 2)[2].strip()}
      tasks.append(cur)
    elif line.startswith("  sha256: ") and cur:
      cur["sha256"] = line.split(" ", 1)[1].strip()
  return tasks


def probe_hf() -> dict:
  """HEADs the dataset README and a few gated task files; records HTTP codes."""
  token = os.environ.get("HF_TOKEN", "")

  def code(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    if token:
      req.add_header("Authorization", f"Bearer {token}")
    try:
      with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status
    except urllib.error.HTTPError as exc:
      return exc.code
    except OSError:
      return 0

  revision = next(
      l.split(":", 1)[1].strip()
      for l in (ROOT / "eval" / "dev_set.yaml").read_text().splitlines()
      if l.startswith("tasks_revision:")
  )
  readme = code(f"{HF_BASE}/resolve/{revision}/README.md")
  tasks = []
  for task in dev_set_tasks():
    folder = f"{HF_BASE}/resolve/{revision}/tasks/{task['id']}"
    tasks.append(
        {
            "id": task["id"],
            "sha256": task.get("sha256", ""),
            "files": {name: code(f"{folder}/{name}") for name in GATE_FILES},
        }
    )
  blocked = [t["id"] for t in tasks if any(c == 401 for c in t["files"].values())]
  return {
      "probed_utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
      "hf_token_present": bool(token),
      "tasks_repo": "google/physical-engineerings-last-exam",
      "tasks_revision": revision,
      "readme_status": readme,
      "tasks": tasks,
      "blocked_task_count": len(blocked),
      "conclusion": (
          f"README.md is public ({readme}); task folders are gated "
          f"({len(blocked)}/{len(tasks)} tasks return 401 without a granted "
          "HF token), so the official runner cannot download them here."
      ),
  }


def write_gate(path: pathlib.Path, gate: dict) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(gate, indent=1) + "\n")


def read_json(path: pathlib.Path, default=None):
  try:
    return json.loads(path.read_text())
  except FileNotFoundError:
    return default


def replay(runs_dir: pathlib.Path, gate_path: pathlib.Path) -> dict:
  """Builds the dev-set result table from committed artifacts only."""
  gate = read_json(gate_path) or {}
  blocked = {t["id"] for t in gate.get("tasks", []) if any(c == 401 for c in t["files"].values())}
  results = []
  for sample in sorted((ROOT / "samples").iterdir()):
    if not (sample / "instruction.md").exists():
      continue
    task_id = sample.name
    run = read_json(runs_dir / task_id / "metrics.json")
    results.append(
        {
            "task": task_id,
            "accessible": True,
            "graded_officially": False,
            "run": run,
            "status": "run_locally" if run else ("gated_401" if task_id in blocked else "not_run"),
            "note": (
                "public sample task; run with runner_local.py against an "
                "endpoint you own; the official grader needs the gated HF "
                "task folder"
            ),
        }
    )
  for name in sorted(p.name for p in runs_dir.iterdir() if p.is_dir()):
    if name not in {r["task"] for r in results}:
      results.append(
          {
              "task": name,
              "accessible": True,
              "graded_officially": False,
              "run": read_json(runs_dir / name / "metrics.json"),
              "status": "run_locally",
              "note": "committed local run evidence (see runs/)",
          }
      )
  for task in dev_set_tasks():
    if task["id"] not in {r["task"] for r in results}:
      results.append(
          {
              "task": task["id"],
              "accessible": False,
              "graded_officially": False,
              "run": None,
              "status": "gated_401" if task["id"] in blocked else "not_run",
              "note": "HF dataset folder returns 401 without granted access",
          }
      )
  kit = read_json(ROOT / "runs" / "kit-check.json") or {}
  return {
      "generated_utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
      "source": "replay of committed runs/ + samples/ + artifacts/hf_gate.json",
      "hf_gate": gate.get("conclusion", "no gate probe recorded; run --probe"),
      "kit_check_stages": kit.get("stages", []),
      "results": results,
  }


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--mode", choices=["replay", "local", "harbor"], default="replay")
  parser.add_argument("--out", default=str(ROOT / "runs-local"), help="local mode output dir")
  parser.add_argument("--tasks-dir", help="harbor mode: dev task folders already downloaded")
  parser.add_argument("--ple-repo", default=os.path.expanduser("~/repos/ple-official"))
  parser.add_argument("--probe", action="store_true", help="refresh artifacts/hf_gate.json over the network")
  parser.add_argument("--results-out", default=str(ROOT / "artifacts" / "dev_results.json"))
  args = parser.parse_args()

  gate_path = ROOT / "artifacts" / "hf_gate.json"
  if args.probe or not gate_path.exists():
    write_gate(gate_path, probe_hf())
    print(f"wrote {gate_path}")

  runs_dir = pathlib.Path(args.out)
  if args.mode == "local":
    for sample in sorted((ROOT / "samples").iterdir()):
      if not (sample / "instruction.md").exists():
        continue
      subprocess.run(
          [sys.executable, str(ROOT / "runner_local.py"), str(sample), str(runs_dir / sample.name)],
          check=True,
          cwd=ROOT,
      )
  elif args.mode == "harbor":
    runner = pathlib.Path(args.ple_repo) / "eval" / "run.py"
    if not runner.exists():
      print(f"[FAIL] official runner not found at {runner}; set --ple-repo")
      return 1
    cmd = [sys.executable, str(runner), str(ROOT)]
    if args.tasks_dir:
      cmd += ["--tasks-dir", args.tasks_dir]
    print(" ".join(cmd))
    return subprocess.call(cmd)

  results = replay(runs_dir if args.mode == "local" else ROOT / "runs", gate_path)
  out = pathlib.Path(args.results_out)
  out.parent.mkdir(parents=True, exist_ok=True)
  out.write_text(json.dumps(results, indent=1) + "\n")
  n_run = sum(1 for r in results["results"] if r["status"] == "run_locally")
  n_gate = sum(1 for r in results["results"] if r["status"] == "gated_401")
  print(f"wrote {out}: {n_run} tasks run locally, {n_gate} gated 401, {len(results['results'])} total")
  return 0


if __name__ == "__main__":
  sys.exit(main())
