"""Local stand-in for the Gemini API's OpenAI-compatible path.

    UPSTREAM=http://<your-openai-host>/v1 python3 scripts/gemini_openai_shim.py [port]

A `google-cloud/*` gemini pairing exports GOOGLE_GEMINI_BASE_URL + GEMINI_API_KEY
and no OpenAI URL, so the harness derives `<base>/v1beta/openai` from it (see
`serve.resolve_endpoint`). This shim serves that exact path shape and forwards
to UPSTREAM, which lets the pairing wiring be exercised end to end with your
own endpoint and key — what is under test is the harness's resolution, not
Google's service.
"""

import os
import sys

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response

app = FastAPI()
UPSTREAM = os.environ.get("UPSTREAM", "http://127.0.0.1:8000/v1").rstrip("/")


@app.api_route("/v1beta/openai/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request):
  body = await request.body()
  async with httpx.AsyncClient(timeout=600) as client:
    upstream = await client.request(
        request.method,
        f"{UPSTREAM}/{path}",
        content=body,
        headers={"content-type": request.headers.get("content-type") or "application/json"},
    )
  return Response(
      content=upstream.content,
      status_code=upstream.status_code,
      media_type=upstream.headers.get("content-type") or "application/json",
  )


if __name__ == "__main__":
  uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8077)
