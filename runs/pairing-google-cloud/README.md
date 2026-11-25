# pairing-google-cloud — the `google-cloud/*` pairing path, run live

Proves the harness reaches a model through the environment a `google-cloud`
pairing gives it, using an endpoint and key **we own** (no Google account, no
secret in this repo).

What was exported, exactly as a gemini pairing exports it — native base URL and
key, no OpenAI URL:

```
GOOGLE_GEMINI_BASE_URL=http://127.0.0.1:8077   GEMINI_API_KEY=own-endpoint-key
MODEL_NAME=qwen3.8-flash-next-iq3_s            (our local model)
```

`serve.resolve_endpoint` turned that into `http://127.0.0.1:8077/v1beta/openai`
— the OpenAI-compatible path shape, which is what
`PROVIDERS["gemini"].base_url` in the vendored official kit uses — and the run
went through it end to end (`scripts/gemini_openai_shim.py` serves that path and
forwards to our server).

```bash
UPSTREAM=http://127.0.0.1:8000/v1 python3 scripts/gemini_openai_shim.py 8077 &
GOOGLE_GEMINI_BASE_URL=http://127.0.0.1:8077 GEMINI_API_KEY=own-endpoint-key \
  MODEL_NAME=qwen3.8-flash-next-iq3_s python3 runner_local.py tmp/pairing-ws runs/pairing-google-cloud
```

`hello.txt` was written with content `HELLO`; step 2 was a content-only reply
and the pause nudge (step 2 → 3) is why step 3 verified the file instead of
stopping. What this does **not** prove: that Google's hosted
`gemini-3.8-flash` answers on that path — at final entry the kit exports the
organizer's model server as `OPENAI_BASE_URL`, which the same resolver takes
first (both paths are unit-tested in `tests/test_submission_yaml.py`).
