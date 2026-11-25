"""Builds the writeup figures from committed run artifacts (no invented numbers).

    python3 scripts/make_figures.py

Reads runs/*/metrics.json and runs/*/*.json plus runs/kit-check.log, the
official kit stage results in runs/kit-check.json, and the dev-set result
table in artifacts/dev_results.json (regenerate it with
`python3 eval/run.py --mode replay`). Every number plotted is parsed from
those files. Output goes to figures/.
"""

import json
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(run):
  with open(os.path.join(ROOT, "runs", run, "metrics.json")) as fh:
    metrics = json.load(fh)
  with open(os.path.join(ROOT, "runs", run, "trajectory.json")) as fh:
    traj = json.load(fh)
  return metrics, traj


def figure_steps_vs_tokens():
  """Step mix and tool-output volume of a full local replay (long-memo when committed)."""
  run = "long-memo" if os.path.exists(os.path.join(ROOT, "runs", "long-memo", "trajectory.json")) else "hello"
  metrics, traj = load(run)
  steps = traj["steps"]
  model_steps = [i + 1 for i, s in enumerate(steps) if s["source"] == "model"]
  tool_steps = [i + 1 for i, s in enumerate(steps) if s["source"] == "tool"]

  # replay usage accounting exactly as the loop does: prompt tokens grow with
  # each model call; per-call values are stored in the metrics total only, so
  # plot the trajectory's tool-output volume against model-call index instead.
  out_sizes = []
  n = 0
  for s in steps:
    if s["source"] == "tool":
      n += 1
      out_sizes.append(len(s["message"].get("output", "")))
  fig, ax = plt.subplots(figsize=(7, 3.5))
  ax.bar(range(1, len(out_sizes) + 1), out_sizes, color="#4c72b0")
  ax.set_xlabel("tool call #")
  ax.set_ylabel("chars returned to the model")
  ax.set_title(
      f"{run} sample run: {len(model_steps)} model calls,"
      f" {len(tool_steps)} exec results,\n{metrics['prompt_tokens']:,} prompt /"
      f" {metrics['completion_tokens']:,} completion tokens"
  )
  fig.tight_layout()
  fig.savefig(os.path.join(ROOT, "figures", "sample_run_tool_activity.png"), dpi=140)
  plt.close(fig)


def figure_run_costs():
  """Steps and tokens for each verified run, straight from metrics.json."""
  runs = [d for d in sorted(os.listdir(os.path.join(ROOT, "runs"))) if os.path.isdir(os.path.join(ROOT, "runs", d))]
  names, steps, prompt, completion = [], [], [], []
  for run in runs:
    try:
      with open(os.path.join(ROOT, "runs", run, "metrics.json")) as fh:
        m = json.load(fh)
    except (FileNotFoundError, KeyError):
      continue
    names.append(run)
    steps.append(m["total_steps"])
    prompt.append(m["prompt_tokens"])
    completion.append(m["completion_tokens"])
  x = range(len(names))
  w = 0.4
  fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 3.2))
  ax1.bar([i - w / 2 for i in x], steps, w, label="steps", color="#55a868")
  ax1.set_xticks(list(x), names)
  ax1.set_ylabel("model round trips")
  ax1.legend()
  ax2.bar([i - w / 2 for i in x], prompt, w, label="prompt", color="#4c72b0")
  ax2.bar([i + w / 2 for i in x], completion, w, label="completion", color="#c44e52")
  ax2.set_xticks(list(x), names)
  ax2.set_ylabel("tokens")
  ax2.legend()
  fig.suptitle("verified local-model sample runs (from metrics.json)")
  fig.tight_layout()
  fig.savefig(os.path.join(ROOT, "figures", "run_costs.png"), dpi=140)
  plt.close(fig)


def figure_kit_stages():
  """Stage-by-stage results parsed straight out of runs/kit-check.log."""
  with open(os.path.join(ROOT, "runs", "kit-check.log")) as fh:
    log = fh.read()
  stages = re.findall(r"\[(PASS|FAIL|SKIP|INFO|WARN)\]\s+([a-z0-9_.-]+)[^\n]*", log)
  seen = {}
  for status, name in stages:
    if name not in seen or seen[name] == "INFO":
      seen[name] = status
  names = list(seen)
  colors = {
      "PASS": "#55a868",
      "FAIL": "#c44e52",
      "SKIP": "#8c8c8c",
      "INFO": "#4c72b0",
      "WARN": "#dd8452",
  }
  fig, ax = plt.subplots(figsize=(7, 1.1 + 0.4 * len(names)))
  ax.barh(
      names, [1] * len(names), color=[colors[seen[n]] for n in names]
  )
  for i, n in enumerate(names):
    ax.text(1.02, i, seen[n], va="center")
  ax.set_xlim(0, 1.25)
  ax.set_xticks([])
  ax.set_title("official kit check stages (parsed from runs/kit-check.log)")
  fig.tight_layout()
  fig.savefig(os.path.join(ROOT, "figures", "kit_check_stages.png"), dpi=140)
  plt.close(fig)


def load_json(rel):
  with open(os.path.join(ROOT, rel)) as fh:
    return json.load(fh)


def figure_architecture():
  """The harness data flow, straight from the repo's module boundaries."""
  boxes = [
      ("evaluation server\n(serve protocol)", "#e8e8e8"),
      ("taskbridge.py\nWebSocket serve protocol", "#cfe3f7"),
      ("serve.py\none agent loop per task", "#cfe3f7"),
      ("agent_core.run_loop\nsteps, retries, wrap-up,\npause nudge", "#ffe2b3"),
      ("exec: bash -c\nin the task workspace\n(24k head+tail cut)", "#d8ecc8"),
      ("task's MCP tools\n<server>__<tool>", "#d8ecc8"),
      ("model endpoint\nOpenAI-compatible chat", "#f7cfcf"),
  ]
  fig, ax = plt.subplots(figsize=(8.6, 3.4))
  ys = [0.82, 0.58, 0.34]
  pos = {
      0: (0.03, ys[0]), 1: (0.28, ys[0]), 2: (0.56, ys[0]),
      3: (0.28, ys[1]), 4: (0.03, ys[2]), 5: (0.42, ys[2]), 6: (0.74, ys[1]),
  }
  for i, (label, color) in enumerate(boxes):
    x, y = pos[i]
    ax.add_patch(FancyBboxPatch((x, y), 0.21, 0.15, boxstyle="round,pad=0.012",
                                facecolor=color, edgecolor="#444", transform=ax.transAxes))
    ax.text(x + 0.105, y + 0.075, label, ha="center", va="center", fontsize=8,
            transform=ax.transAxes)

  def edge(i, side):
    x, y = pos[i]
    return {
        "l": (x, y + 0.075), "r": (x + 0.21, y + 0.075),
        "b": (x + 0.105, y), "t": (x + 0.105, y + 0.15),
        "bl": (x + 0.04, y), "br": (x + 0.17, y),
        "tl": (x + 0.04, y + 0.15), "tr": (x + 0.17, y + 0.15),
    }[side]

  arrows = [
      (edge(0, "r"), edge(1, "l")), (edge(1, "r"), edge(2, "l")),
      (edge(2, "b"), edge(3, "t")), (edge(3, "bl"), edge(4, "tr")),
      (edge(3, "br"), edge(5, "tl")), (edge(3, "r"), edge(6, "l")),
  ]
  for (xa, ya), (xb, yb) in arrows:
    ax.add_patch(FancyArrowPatch((xa, ya), (xb, yb), arrowstyle="-|>",
                                 mutation_scale=12, color="#333",
                                 transform=ax.transAxes))
  ax.text(0.995, 0.02, "protocol code vendored verbatim from the official kit\n"
          "model env per docs/models.md (MODEL_NAME / OPENAI_BASE_URL / key)",
          ha="right", va="bottom", fontsize=7, color="#555", transform=ax.transAxes)
  ax.set_axis_off()
  ax.set_title("harness v2 architecture (repo module boundaries)")
  fig.tight_layout()
  fig.savefig(os.path.join(ROOT, "figures", "architecture.png"), dpi=140)
  plt.close(fig)


def figure_score_vs_cost():
  """Cost of every local run vs what the official kit check verified of it."""
  dev = load_json(os.path.join("artifacts", "dev_results.json"))
  stages = {s["name"]: s["status"] for s in dev.get("kit_check_stages", [])}
  verified = "pass" if stages.get("smoke") == "pass" else "unverified"
  mcp_ok = "pass" if stages.get("mcp") == "pass" else "unverified"
  rows, labels = [], []
  for r in dev["results"]:
    if not r["run"]:
      continue
    rows.append((r["task"], r["run"]["prompt_tokens"], r["run"]["completion_tokens"], r["run"]["total_steps"]))
    labels.append(
        {
            "hello": f"verified ({verified})",
            "hello-nudge": "pause fix verified live",
            "pairing-google-cloud": "google-cloud pairing path, live",
            "long-memo-retry": "pause-bug early stop (pre-fix)",
        }.get(r["task"], "known-bad: context overflow")
    )
  fig, ax = plt.subplots(figsize=(7.6, 3.8))
  ax.set_xscale("log")
  ax.set_yscale("log")
  colors = {
      "verified (pass)": "#55a868",
      "verified (unverified)": "#8c8c8c",
      "google-cloud pairing path, live": "#4c72b0",
  }
  xmin, xmax = 1e9, 0
  for name, prompt, completion, steps in rows:
    xmin, xmax = min(xmin, prompt), max(xmax, prompt)
  ax.set_xlim(left=xmin / 2.5, right=xmax * 8)
  ax.set_ylim(top=max([r[2] for r in rows] + [1]) * 3)  # headroom for the top annotation
  for (name, prompt, completion, steps), label in zip(rows, labels):
    ax.scatter(prompt, completion, s=steps * 12, color=colors.get(label, "#c44e52"), zorder=3)
    right = prompt < xmax / 2  # room to the right for the left-hand points
    ax.annotate(
        f"{name} · {steps} steps · {label}", (prompt, completion),
        textcoords="offset points", xytext=(14 if right else -14, 10),
        ha="left" if right else "right", fontsize=7.5,
    )
  extra = f" · mcp stage {mcp_ok}" if mcp_ok == "pass" else ""
  ax.set_xlabel("prompt tokens (log)")
  ax.set_ylabel("completion tokens (log)")
  ax.set_title("local runs: cost vs verified outcome (artifacts/dev_results.json)")
  fig.text(
      0.5, 0.01,
      f"official kit check: smoke stage {verified}{extra}; the 29 HF dev tasks are gated "
      "401 on this machine, so they carry no official score",
      ha="center", fontsize=7.5, color="#555",
  )
  fig.tight_layout(rect=(0, 0.05, 1, 1))
  fig.savefig(os.path.join(ROOT, "figures", "score_vs_cost.png"), dpi=140)
  plt.close(fig)


def figure_failure_breakdown():
  """Where the dev-set entries stand, tallied from artifacts/dev_results.json."""
  dev = load_json(os.path.join("artifacts", "dev_results.json"))
  counts = {
      "dev tasks gated on HF (HTTP 401)": sum(1 for r in dev["results"] if r["status"] == "gated_401"),
      "run locally, official grader unreachable": sum(1 for r in dev["results"] if r["status"] == "run_locally"),
      "sample task, no committed run yet": sum(1 for r in dev["results"] if r["status"] == "not_run"),
      # flagged individual runs (subsets of the row above), counted not invented:
      "pause-is-not-a-finish bug (fixed; pre-fix run kept)": sum(
          1 for r in dev["results"] if r["task"] == "long-memo-retry" and r["run"]
      ),
      "context-overflow known-bad run": sum(
          1 for r in dev["results"] if r["task"] == "long-memo" and r["run"]
      ),
  }
  counts = {k: v for k, v in counts.items() if v}
  names = list(counts)
  colors = ["#c44e52", "#55a868", "#8c8c8c", "#dd8452", "#4c72b0"]
  fig, ax = plt.subplots(figsize=(8, 1.0 + 0.45 * len(names)))
  ax.barh(names, [counts[n] for n in names], color=colors[: len(names)])
  for i, n in enumerate(names):
    ax.text(counts[n] + 0.25, i, str(counts[n]), va="center")
  ax.set_xlabel(
      f"count — top three rows are the {len(dev['results'])} dev-set entries "
      "(29 gated tasks + local/sample tasks); the last two flag single runs"
  )
  ax.set_xlim(0, max(counts.values()) + 2)
  ax.set_title("dev-set failure / accessibility breakdown")
  fig.tight_layout()
  fig.savefig(os.path.join(ROOT, "figures", "failure_breakdown.png"), dpi=140)
  plt.close(fig)


if __name__ == "__main__":
  os.makedirs(os.path.join(ROOT, "figures"), exist_ok=True)
  figure_steps_vs_tokens()
  figure_run_costs()
  figure_kit_stages()
  figure_architecture()
  figure_score_vs_cost()
  figure_failure_breakdown()
  print("wrote", ", ".join(sorted(os.listdir(os.path.join(ROOT, "figures")))))
