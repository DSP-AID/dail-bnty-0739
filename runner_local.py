"""Runs harness v2 end-to-end on a task folder without Docker or the protocol.

    python runner_local.py TASK_DIR OUT_DIR [--instruction-file instruction.md]

The agent's `exec` tool runs bash in TASK_DIR; final_message.md, trajectory.json
and metrics.json are written to OUT_DIR. Used for offline runs on bundled
public sample tasks (see samples/). The model endpoint is resolved by
`serve.resolve_endpoint`, the same path the kit entry uses.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys

import agent_core
import serve


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("task_dir")
  parser.add_argument("out_dir")
  parser.add_argument("--instruction-file", default="instruction.md")
  args = parser.parse_args()

  task_dir = os.path.abspath(args.task_dir)
  with open(os.path.join(task_dir, args.instruction_file)) as fh:
    instruction = fh.read()

  async def exec_tool(command):
    proc = await asyncio.create_subprocess_exec(
        "bash",
        "-c",
        command,
        cwd=task_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
      )
    out, _ = await proc.communicate()
    text = out.decode(errors="replace")
    if proc.returncode:
      text += f"\n[exit code {proc.returncode}]"
    return text

  model, base_url, api_key = serve.resolve_endpoint()
  call_model = agent_core.make_http_call_model(base_url, api_key, model)

  final, steps, metrics = asyncio.run(
      agent_core.run_loop(instruction, call_model, exec_tool, log=print)
  )
  os.makedirs(args.out_dir, exist_ok=True)
  with open(os.path.join(args.out_dir, "final_message.md"), "w") as fh:
    fh.write(final + "\n")
  with open(os.path.join(args.out_dir, "trajectory.json"), "w") as fh:
    json.dump(
        {"agent": "harness-v2", "model": model, "steps": steps, "final_metrics": metrics},
        fh,
        indent=1,
    )
  with open(os.path.join(args.out_dir, "metrics.json"), "w") as fh:
    json.dump(metrics, fh, indent=1)
  print(json.dumps(metrics))
  return 0


if __name__ == "__main__":
  sys.exit(main())
