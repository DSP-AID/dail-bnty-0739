"""The agent loop: model calls plus one `exec` tool (harness v1 core).

Kept free of protocol and transport details so it can be unit-tested with a
mock model and a mock executor. `serve.py` wires this to the PLE serve
protocol; `runner_local.py` wires it to a plain local directory.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "exec",
            "description": (
                "Run a bash command in the task workspace and return its"
                " combined stdout/stderr output."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "bash -c"},
                },
                "required": ["command"],
            },
        },
    }
]

SYSTEM = (
    "You are an engineering agent working on a task in a container. You work"
    " only through the `exec` tool: run shell commands to read the project"
    " files, do the work, and write the deliverable files exactly where the"
    " task asks. Your exec runs with cwd = the task workspace, and that"
    " directory is the whole project: do all work there with relative paths"
    " and never explore or read elsewhere on the machine. If the task names"
    " an absolute path you cannot create, write the same file in your working"
    " directory instead. Verify your own numbers with shell commands when you"
    " can. Keep going until every requested deliverable exists on disk. When"
    " the work is finished, reply with one final message (no tool call) that"
    " states which files you wrote and the key results in them."
)

# tool output over this many characters is cut in half around the middle
OUTPUT_CHARS = 24_000
RETRY_WAITS = (5, 15, 30)


def http_chat(base_url, api_key, model, messages, tools, max_tokens, timeout):
  """One OpenAI-compatible /chat/completions call. Returns the response dict."""
  body = {
      "model": model,
      "messages": messages,
      "tools": tools,
      "max_tokens": max_tokens,
  }
  # llama.cpp rejects unknown fields on other servers, so only qwen models get
  # the thinking switch (it otherwise burns the whole budget on reasoning).
  if "qwen" in model.lower():
    body["chat_template_kwargs"] = {"enable_thinking": False}
  data = json.dumps(body).encode()
  headers = {"Content-Type": "application/json"}
  if api_key:
    headers["Authorization"] = f"Bearer {api_key}"
  url = base_url.rstrip("/") + "/chat/completions"
  last = None
  for attempt in range(len(RETRY_WAITS) + 1):
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
      with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)
    except urllib.error.HTTPError as exc:
      # 4xx (except 429) will not fix themselves; give up on those.
      if exc.code != 429 and 400 <= exc.code < 500:
        raise RuntimeError(f"model endpoint HTTP {exc.code}: {exc.read()[:300]!r}") from exc
      last = exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
      last = exc
    if attempt < len(RETRY_WAITS):
      time_sleep(RETRY_WAITS[attempt])
  raise RuntimeError(f"model endpoint unreachable after retries: {last}")


def time_sleep(seconds):
  """Sleep wrapper (monkeypatched in tests)."""
  import time

  time.sleep(seconds)


def _cut(text):
  if len(text) <= OUTPUT_CHARS:
    return text
  half = OUTPUT_CHARS // 2
  return text[:half] + f"\n[... {len(text) - OUTPUT_CHARS} chars cut ...]\n" + text[-half:]


async def run_loop(
    instruction,
    call_model,
    exec_tool,
    max_steps=120,
    time_left=None,
    log=None,
    mcp_tool=None,
):
  """Runs the tool loop. Returns (final_text, steps, metrics).

  Args:
    instruction: the task text from the evaluator.
    call_model: async fn(messages) -> response dict (OpenAI shape).
    exec_tool: async fn(command) -> output string.
    max_steps: cap on model round trips.
    time_left: optional fn() -> seconds remaining; the loop stops early near 0.
    log: optional fn(text) for progress lines.
    mcp_tool: optional async fn(name, arguments) -> output string, called for
      tool calls whose function name is not `exec` (the MCP-provided tools).
  """
  messages = [
      {"role": "system", "content": SYSTEM},
      {"role": "user", "content": instruction},
  ]
  steps, metrics = [], {"total_steps": 0, "prompt_tokens": 0, "completion_tokens": 0}
  # one nudge turns a mid-task "pause" (a content-only reply that announces
  # more work) back into work; see the pause-is-not-a-finish bug in KAGGLE_WRITEUP.
  nudged = False
  worked = False

  def note(text):
    if log:
      log(text)

  for step in range(1, max_steps + 1):
    if time_left is not None and time_left() is not None and time_left() < 90:
      note("out of time; stopping the loop")
      break
    resp = await call_model(messages)
    choice = (resp.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    usage = resp.get("usage") or {}
    metrics["prompt_tokens"] += usage.get("prompt_tokens") or 0
    metrics["completion_tokens"] += usage.get("completion_tokens") or 0
    metrics["total_steps"] += 1
    calls = msg.get("tool_calls") or []
    steps.append({"step_id": step, "source": "model", "message": msg})
    if not calls:
      final = (msg.get("content") or "").strip()
      if worked and not nudged:
        # a content-only reply after real work is usually a pause, not the end
        nudged = True
        messages.append(msg)
        messages.append(
            {
                "role": "user",
                "content": (
                    "Before stopping, use exec to verify every deliverable the"
                    " task asked for exists on disk. If any is missing keep"
                    " working; if all are there reply with your final message."
                ),
            }
        )
        note(f"step {step}: pause nudge after a content-only reply")
        continue
      return final or "(the model returned no final message)", steps, metrics
    worked = True
    messages.append(msg)
    for call in calls:
      fn = call.get("function", {})
      name = fn.get("name") or "exec"
      try:
        args = json.loads(fn.get("arguments") or "{}")
      except json.JSONDecodeError:
        args = {"command": fn.get("arguments") or ""}
      if name == "exec":
        command = args.get("command", "")
        note(f"step {step}: exec {command[:120]!r}")
        label = {"command": command}
        invoke = lambda c=command: exec_tool(c)
      else:
        note(f"step {step}: mcp {name} {json.dumps(args)[:120]}")
        label = {"tool": name, "arguments": args}
        invoke = (
            (lambda a=args, n=name: mcp_tool(n, a)) if mcp_tool else None
        )
      try:
        output = await invoke() if invoke else f"unknown tool {name!r}"
      except Exception as exc:  # a failing call is fed back, not fatal
        output = f"{name} failed: {type(exc).__name__}: {exc}"
      output = _cut(str(output))
      messages.append(
          {
              "role": "tool",
              "tool_call_id": call.get("id", ""),
              "content": output,
          }
      )
      steps.append(
          {"step_id": step, "source": "tool", "message": {**label, "output": output}}
      )
  note(f"step budget reached ({max_steps}); asking the model to wrap up")
  messages.append(
      {
          "role": "user",
          "content": "Stop calling tools. Reply now with your final message describing what you completed and what is missing.",
      }
  )
  resp = await call_model(messages)
  msg = ((resp.get("choices") or [{}])[0]).get("message") or {}
  metrics["total_steps"] += 1
  return (msg.get("content") or "(no final message)").strip(), steps, metrics


def make_http_call_model(base_url, api_key, model, max_tokens=4096, timeout=300, tools=None):
  """Returns an async `call_model(messages)` backed by the HTTP endpoint."""

  async def call_model(messages):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: http_chat(base_url, api_key, model, messages, tools or TOOLS, max_tokens, timeout),
    )

  return call_model
