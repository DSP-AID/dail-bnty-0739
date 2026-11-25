# Running this harness on the PLE dev set

`eval/run.py` has three modes; the default one needs no network and no API
keys, so a clean machine reproduces it exactly.

| mode | what it does | needs |
|---|---|---|
| `replay` (default) | rebuilds `artifacts/dev_results.json` from the committed evidence in `runs/`, `samples/` and `artifacts/hf_gate.json` | nothing |
| `--mode local` | runs `runner_local.py` live on every sample task, then replays those runs | an OpenAI-compatible endpoint you own (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `MODEL_NAME`) |
| `--mode harbor` | delegates to the official runner from the `ple` repo (`$PLE_REPO/eval/run.py`), which downloads the 29 dev tasks and grades them in Docker/Harbor | Docker + `uv` + Harbor + Hugging Face access to `google/physical-engineerings-last-exam` |

```bash
python3 eval/run.py                 # offline, writes artifacts/dev_results.json
python3 eval/run.py --probe         # refresh the HF gate probe (network)
python3 eval/run.py --mode local --out runs-local
OPENAI_BASE_URL=http://your-host:8000/v1 python3 eval/run.py --mode local
PLE_REPO=~/repos/ple python3 eval/run.py --mode harbor --tasks-dir /path/to/tasks
```

## Why the 29 official dev tasks are not scored here

The dev set is the 29 task ids pinned in `eval/dev_set.yaml` (a verbatim copy
of the kit's `eval/dev_set.yaml`, dataset revision
`b3857a3fea39a695e18f845d4a88f29442e96e75`). The task folders live in the
Hugging Face dataset `google/physical-engineerings-last-exam`. On this machine,
with no HF token:

* `resolve/<rev>/README.md` → **HTTP 200** (public; kept as a real sample at
  `samples/hf-dataset-readme.md`), and
* `resolve/<rev>/tasks/<id>/{task.toml,instruction.md,release.json,eval.yaml}`
  → **HTTP 401 for all 29 tasks**, so the official runner cannot download them
  and Harbor cannot start the containers.

`python3 eval/run.py --probe` re-measures that and writes it to
`artifacts/hf_gate.json`; `artifacts/dev_results.json` then lists every task
with its status (`gated_401`, `run_locally`, `not_run`) instead of invented
scores. So: every *accessible* task (the three public sample tasks) is run, and
the gate is the documented reason the full 29-task run and the Stage-2 harbor
runs did not happen here. With a granted HF token, `--mode harbor` is the
command that produces the official scores; the entry's `submission.yaml` then
needs only `MODEL_PROXY_URL` / `MODEL_PROXY_KEY` (or `GEMINI_API_KEY` +
`GOOGLE_GEMINI_BASE_URL`) because the kit forbids a base URL for
`google-cloud/*` models.
