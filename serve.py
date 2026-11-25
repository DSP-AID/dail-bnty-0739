"""PLE harness v2: a WebSocket server solving tasks over the serve protocol.

Listens on $PORT (taskbridge.run). For each task it runs `agent_core.run_loop`
against an OpenAI-compatible model endpoint, driving the task container through
the single `exec` tool, and returns the model's final message.

Environment (set by the kit / evaluation server per docs/models.md):
  OPENAI_BASE_URL (or MODEL_BASE_URL), MODEL_NAME, OPENAI_API_KEY (or MODEL_API_KEY).
A google-cloud gemini pairing exports no OpenAI URL; the Gemini API's own
OpenAI-compatible path (GOOGLE_GEMINI_BASE_URL + /v1beta/openai) is used then.
Optional: MAX_STEPS (default 120), MAX_OUTPUT_TOKENS (default 4096).
"""

from __future__ import annotations

import json
import os

import agent_core
import taskbridge


def resolve_endpoint(environ=None):
  """Model endpoint from env, in the order the kit exports it.

  An explicit OpenAI URL always wins (that is how `kit check --model-base-url`
  and our own server are pointed). A bare google-cloud gemini pairing exports
  only GOOGLE_GEMINI_BASE_URL + GEMINI_API_KEY, so the Gemini API's own
  OpenAI-compatible path is derived from it. Unit-tested in
  tests/test_submission_yaml.py.
  """
  env = os.environ if environ is None else environ
  gemini = env.get("GOOGLE_GEMINI_BASE_URL", "")
  base_url = (
      env.get("OPENAI_BASE_URL")
      or env.get("MODEL_BASE_URL")
      or (gemini.rstrip("/") + "/v1beta/openai" if gemini else "")
      or "http://127.0.0.1:8000/v1"
  )
  api_key = (
      env.get("OPENAI_API_KEY") or env.get("MODEL_API_KEY") or env.get("GEMINI_API_KEY") or ""
  )
  return env.get("MODEL_NAME", "model"), base_url, api_key


MODEL, BASE_URL, API_KEY = resolve_endpoint()
MAX_STEPS = int(os.environ.get("MAX_STEPS", "120"))
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "4096"))


async def solve(session):
  """Solves one task and returns the final message."""

  def note(text):
    print(f"[{session.task.get('id', '?')}] {text}", flush=True)

  async def exec_tool(command):
    result = await session.exec(command, timeout_sec=600)
    out = result.get("output") or ""
    if result.get("truncated"):
      out += "\n[output truncated by the evaluator]"
    code = result.get("exit_code")
    if code:
      out += f"\n[exit code {code}]"
    return out

  # expose each task MCP server's tools as model functions <server>__<tool>
  tools = list(agent_core.TOOLS)
  mcp = {}  # model tool name -> (MCPClient, real tool name)
  for cfg in session.mcp_servers:
    name = str(cfg.get("name") or "mcp")
    try:
      client = taskbridge.MCPClient(session, str(cfg["url"]))
      await client.initialize()
      for t in await client.list_tools():
        tool = f"{name}__{t['name']}"
        mcp[tool] = (client, t["name"])
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool,
                    "description": f"MCP tool {t['name']} on server {name}. "
                    + (t.get("description") or ""),
                    "parameters": t.get("inputSchema")
                    or {"type": "object", "properties": {}},
                },
            }
        )
      note(f"mcp server {name}: {len(mcp)} tool(s)")
    except Exception as exc:
      note(f"mcp server {name} unavailable: {exc}")

  async def mcp_tool(tool_name, arguments):
    client, real = mcp[tool_name]
    result = await client.call_tool(real, arguments)
    parts = [c.get("text", "") for c in result.get("content") or [] if isinstance(c, dict)]
    return "\n".join(parts) or json.dumps(result)

  call_model = agent_core.make_http_call_model(
      BASE_URL, API_KEY, MODEL, max_tokens=MAX_OUTPUT_TOKENS, tools=tools
  )
  final, _steps, metrics = await agent_core.run_loop(
      session.instruction,
      call_model,
      exec_tool,
      max_steps=MAX_STEPS,
      time_left=session.time_left,
      log=note,
      mcp_tool=mcp_tool if mcp else None,
  )
  note(f"done: {json.dumps(metrics)}")
  return final


if __name__ == "__main__":
  taskbridge.run(solve)
