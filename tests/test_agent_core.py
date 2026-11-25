"""Offline unit tests: no network, no API keys (mock model + mock exec)."""

import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, ".")

import agent_core


def script_model(replies):
  """call_model that replaves canned OpenAI-shaped replies, then records calls."""
  calls = []

  async def call_model(messages):
    calls.append(messages)
    reply = replies[min(len(calls) - 1, len(replies) - 1)]
    return {
        "choices": [{"message": reply}],
        "usage": {"prompt_tokens": 10 * len(calls), "completion_tokens": 5},
    }

  return call_model, calls


def tool_call(name, command, cid="c1"):
  return {
      "type": "assistant",
      "tool_calls": [
          {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps({"command": command})}}
      ],
      "content": None,
  }


def test_loop_two_steps_then_final():
  ran = []

  async def exec_tool(command):
    ran.append(command)
    return "ok: " + command

  call_model, calls = script_model([tool_call("exec", "ls"), {"role": "assistant", "content": "DONE"}])
  final, steps, metrics = asyncio.run(agent_core.run_loop("do it", call_model, exec_tool))
  assert final == "DONE"
  assert ran == ["ls"]
  # the content-only reply after work gets one verification nudge, then the
  # model's next message is accepted as final (pause-is-not-a-finish fix)
  assert metrics["total_steps"] == 3
  assert calls[-1][-2:][0]["content"] == "DONE"
  assert "verify" in calls[-1][-1]["content"]
  # the tool result reached the model as a tool message
  tool_msgs = [m for m in calls[1] if m.get("role") == "tool"]
  assert tool_msgs and tool_msgs[0]["content"].startswith("ok: ls")
  assert steps[0]["source"] == "model" and steps[1]["source"] == "tool"


def test_exec_failure_is_fed_back_not_fatal():
  async def exec_tool(command):
    raise RuntimeError("container gone")

  call_model, calls = script_model([tool_call("exec", "ls"), {"role": "assistant", "content": "recovered"}])
  final, _, _ = asyncio.run(agent_core.run_loop("t", call_model, exec_tool))
  assert final == "recovered"
  tool_msgs = [m for m in calls[1] if m.get("role") == "tool"]
  assert "exec failed" in tool_msgs[0]["content"]


def test_step_budget_triggers_wrapup():
  always_tool = tool_call("exec", "echo x", cid="loop")
  call_model, _ = script_model([always_tool, always_tool, {"role": "assistant", "content": "wrapped up"}])

  async def exec_tool(command):
    return ""

  final, _, metrics = asyncio.run(
      agent_core.run_loop("t", call_model, exec_tool, max_steps=2)
  )
  assert final == "wrapped up"
  assert metrics["total_steps"] == 3  # 2 tool steps + 1 wrap-up call


def test_time_guard_stops_the_loop():
  call_model, _ = script_model([{"role": "assistant", "content": "late"}])

  async def exec_tool(command):
    return ""

  final, _, metrics = asyncio.run(
      agent_core.run_loop("t", call_model, exec_tool, time_left=lambda: 10)
  )
  # the loop never runs a tool step; one wrap-up model call still answers
  assert metrics["total_steps"] == 1
  assert final == "late"


def test_pause_nudge_once_then_final():
  """A content-only reply after real work gets exactly one verification nudge."""
  ran = []

  async def exec_tool(command):
    ran.append(command)
    return "ok"

  pause = {"role": "assistant", "content": "I will now write the file."}
  call_model, calls = script_model(
      [tool_call("exec", "ls"), pause, {"role": "assistant", "content": "done"}]
  )
  final, _, metrics = asyncio.run(agent_core.run_loop("t", call_model, exec_tool))
  assert final == "done"
  assert metrics["total_steps"] == 3
  # the nudge reached the model as a user message right after the pause
  nudges = [m for m in calls[2] if m.get("role") == "user" and "verify" in m["content"]]
  assert len(nudges) == 1

  # without the fix this run would have ended at the pause; a second pause
  # after the nudge is accepted as final (the nudge never repeats)
  call_model, _ = script_model(
      [tool_call("exec", "ls"), pause, pause, {"role": "assistant", "content": "x"}]
  )
  final, _, metrics = asyncio.run(agent_core.run_loop("t", call_model, exec_tool))
  assert final == "I will now write the file."
  assert metrics["total_steps"] == 3


def test_first_reply_without_work_is_final():
  async def exec_tool(command):
    return ""

  call_model, _ = script_model([{"role": "assistant", "content": "nothing to do"}])
  final, _, metrics = asyncio.run(agent_core.run_loop("t", call_model, exec_tool))
  assert final == "nothing to do"
  assert metrics["total_steps"] == 1


def test_output_cut_keeps_head_and_tail():
  text = "H" * 5_000 + "M" * 20_000 + "T" * 5_000
  cut = agent_core._cut(text)
  assert len(cut) < len(text)
  assert cut.startswith("HHH") and cut.endswith("TTT") and "chars cut" in cut


def test_mcp_tool_dispatch():
  seen = []

  async def exec_tool(command):
    return ""

  async def mcp_tool(name, arguments):
    seen.append((name, arguments))
    return "SECRET-WORD"

  call = {
      "id": "m1",
      "type": "function",
      "function": {"name": "apps__secret_word", "arguments": "{}"},
  }
  reply = {"tool_calls": [call], "content": None}

  async def call_model(messages):
    if any(m.get("role") == "tool" for m in messages):
      return {"choices": [{"message": {"role": "assistant", "content": "done"}}], "usage": {}}
    return {"choices": [{"message": reply}], "usage": {}}

  final, steps, _ = asyncio.run(
      agent_core.run_loop("t", call_model, exec_tool, mcp_tool=mcp_tool)
  )
  assert final == "done"  # accepted after the one verification nudge
  assert seen == [("apps__secret_word", {})]
  tool_msgs = [s for s in steps if s["source"] == "tool"]
  assert tool_msgs[0]["message"]["tool"] == "apps__secret_word"
  assert "SECRET-WORD" in tool_msgs[0]["message"]["output"]


class _Handler(BaseHTTPRequestHandler):
  # per-request queues; the test pushes status codes and bodies before calling
  statuses = [200]
  bodies = []

  def do_POST(self):
    n = int(self.headers["Content-Length"])
    self.rfile.read(n)
    code = self.__class__.statuses.pop(0) if self.__class__.statuses else 200
    body = self.__class__.bodies.pop(0) if self.__class__.bodies else "{}"
    self.send_response(code)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(body.encode())

  def log_message(self, *a):
    pass


def test_http_chat_roundtrip_and_retry():
  ok = json.dumps({"choices": [{"message": {"role": "assistant", "content": "hi"}}], "usage": {}})
  _Handler.statuses = [200]
  _Handler.bodies = [ok]
  srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
  threading.Thread(target=srv.serve_forever, daemon=True).start()
  base = f"http://127.0.0.1:{srv.server_address[1]}/v1"
  waits = []
  real_sleep = __import__("time").sleep
  agent_core.time_sleep = waits.append  # no real sleeping in tests
  try:
    resp = agent_core.http_chat(base, "key", "test-model", [{"role": "user", "content": "x"}], agent_core.TOOLS, 8, 10)
    assert resp["choices"][0]["message"]["content"] == "hi"

    # a 500 then a success: the retry loop must recover after one wait
    _Handler.statuses = [500, 200]
    _Handler.bodies = ["err", json.dumps({"choices": [{"message": {"role": "assistant", "content": "after-retry"}}]})]
    resp = agent_core.http_chat(base, "", "test-model", [], agent_core.TOOLS, 8, 10)
    assert resp["choices"][0]["message"]["content"] == "after-retry"
    assert waits == [5]
  finally:
    agent_core.time_sleep = real_sleep
    srv.shutdown()


def test_http_chat_4xx_fails_fast():
  _Handler.statuses = [400]
  _Handler.bodies = ['{"error":"bad request"}']
  srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
  threading.Thread(target=srv.serve_forever, daemon=True).start()
  base = f"http://127.0.0.1:{srv.server_address[1]}/v1"
  try:
    import pytest

    with pytest.raises(RuntimeError, match="HTTP 400"):
      agent_core.http_chat(base, "", "m", [], agent_core.TOOLS, 8, 10)
  finally:
    srv.shutdown()
