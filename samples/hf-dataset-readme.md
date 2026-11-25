---
pretty_name: "Physical-Engineering’s Last Exam (Dev Set)"
language:
- en
license: cc-by-4.0
task_categories:
- text-generation
- question-answering
tags:
- benchmark
- agents
- engineering
- electrical-engineering
- civil-engineering
- structural-engineering
- mechanical-engineering
- harbor
size_categories:
- n<1K
extra_gated_heading: Request access to Physical-Engineering’s Last Exam (PLE)
extra_gated_description: >-
  This dataset contains the development tasks and grading verifiers used to
  evaluate the Physical-Engineering’s Last Exam (PLE) benchmark. Access is gated to protect benchmark
  integrity.
extra_gated_prompt: >-
  By requesting access you agree to ALL of the following. Misuse may result in
  access revocation and exclusion from the benchmark leaderboard.
extra_gated_fields:
  Full name: text
  Affiliation / organization: text
  Intended use: text
  I will NOT use this data (in whole or part) to train, fine-tune, or distill any model: checkbox
  I will NOT expose this data to any model/agent while it is being evaluated on PLE: checkbox
  I will NOT redistribute or publicly repost this data: checkbox
  I agree to all terms above and understand access is logged and may be revoked: checkbox
extra_gated_button_content: Request access
configs:
- config_name: default
  data_files:
  - split: dev
    path: task_cards.parquet
---

# Physical-Engineering’s Last Exam (Dev Set)

Physical-Engineering’s Last Exam (PLE) is a benchmark of long-horizon engineering tasks built by licensed practicing engineers across 4 disciplines. In each task, an agent works inside a realistic project workspace containing drawings, specifications, spreadsheets, solver scripts, and CAD/BIM or simulation tools to produce engineering deliverables: code, calculations, models, schedules, and technical reports.

This repository contains the 29-task public development set (`split: dev`) of the 85-task PLE benchmark. Each task is packaged as a self-contained [Harbor](https://github.com/laude-institute/harbor) task folder under `tasks/<task_id>/`. Every task runs with a uniform 6-hour agent time limit and no internet access beyond model API calls, and is graded on a 0 to 1 scale in an isolated verifier container (12 tasks `checks`; 14 tasks `rubric`; 3 tasks `checks-judge`).

- Paper: [arXiv:2610.30537](https://arxiv.org/abs/2610.30537)
- Benchmark site: https://ple-bench.com
- Competition kit, with the evaluation runner and sample submissions: [github.com/google-research/ple](https://github.com/google-research/ple)

## Benchmark disciplines

| Discipline | Benchmark tasks | Dev tasks | What the tasks cover |
|---|--:|--:|---|
| Structural engineering | 10 | 4 | Calculate gravity, wind, and seismic loads, verify structural members and connections, and design roof decks, diaphragms, and equipment supports. |
| Civil engineering | 18 | 9 | Lay out site grading, drainage, and utilities, evaluate soil settlement and foundation strategies, and verify excavation shoring and construction plans. |
| Electrical engineering | 27 | 9 | Analyze power distribution from utility service to branch circuits, size feeders and cables, review solar interconnections, and check drawings for energization. |
| Mechanical engineering | 30 | 7 | Design and troubleshoot HVAC, thermal, and fluid-flow systems, route clash-free building services, and validate equipment performance and fire simulations. |

## Leaderboard

A model's score is its mean reward over the 29 dev tasks; the results we report average 3 runs. The [dev-set leaderboard](https://ple-bench.com/leaderboard?set=dev) covers every model we evaluated. Hub leaderboards for this dataset list open-weight models only, because the Hub reads results from model repositories.


## Running the dev set

### With the PLE evaluation runner (recommended)

To evaluate an agent harness or prepare a PLE Harness Competition entry, use the runner in the [competition kit](https://github.com/google-research/ple): `uv run python eval/run.py <submission>`. It downloads this dataset's latest commit (recorded in `results.json`), applies the 6-hour agent time limit, builds task-specific verifier images, grades each task in its verifier container, and exports `artifacts/` for submission. While the dataset is gated, request access on this page and set `HF_TOKEN` to a token of the account that was granted access.

### With standalone Harbor

12 of the 29 tasks also run with [Harbor](https://github.com/laude-institute/harbor) alone (`uv tool install harbor==0.20.0`) and Docker. Tasks with `verifier_image = "task"` under `[metadata]` in `task.toml` are graded by a verifier built from the task's own image plus `tests/`, which Harbor does not build, so run them with the kit's `eval/run.py`. In this release, that applies to the other 17 tasks: `data-hall-mep-routing`, `fire-test-validation-memo`, `data-hall-mep-routing-offset`, `landscape-sheet-revision`, `data-center-site-model`, `engineers-estimate-check`, `footing-settlement-verification`, `solar-supplemental-review`, `solar-witness-test-package`, `fire-solve-convergence`, `les-mesh-resolution`, `fill-compaction-acceptance`, `shoring-design-verification`, `emergency-spillway-check`, `pre-application-capacity-response`, `permission-to-operate-memo`, `backfeed-energization-reply`.

`harbor run --repo` fetches tasks with `git clone` and `git lfs`, so install [Git LFS](https://git-lfs.com), and while the dataset is gated give git your Hugging Face token, for example with `git config --global credential.helper store` and then `hf auth login --add-to-git-credential`.

Of those 12, the programmatic tasks (`checks`) run directly from the Hub:

```bash
export ANTHROPIC_API_KEY=<your key>
harbor run --repo https://huggingface.co/datasets/google/physical-engineerings-last-exam -i frame-extension-method \
  -a claude-code -m anthropic/claude-opus-5-5 --allow-agent-host api.anthropic.com
```

The judge-graded ones (`checks-judge`) require downloading the dataset locally so you can allow your judge endpoint in `task.toml` (`hf download` uses `HF_TOKEN` or your `hf auth login` token):

```bash
hf download google/physical-engineerings-last-exam --repo-type dataset --local-dir ple
# In ple/tasks/eor-review-corrections/task.toml, under both [verifier] and [verifier.environment]:
#   network_mode = "allowlist"
#   allowed_hosts = ["<your judge's host>"]
export JUDGE_BASE_URL=https://<your judge's host>/v1 JUDGE_API_KEY=<your key> JUDGE_MODEL=<model name>
harbor run -p ple/tasks/eor-review-corrections -a claude-code -m anthropic/claude-opus-5-5 --allow-agent-host api.anthropic.com
```

> Note for standalone Harbor: every `task.toml` already sets the 6-hour agent time limit (`timeout_sec = 21600` under `[agent]`). On top of Harbor, `eval/run.py` builds the task-image verifiers and raises Harbor 0.20's 15-second proxy header timeout for long rubric evaluations.

## Citation

```bibtex
@misc{han2026ple,
  title         = {{PLE}: Physical-Engineering's Last Exam},
  author        = {Rujun Han and Yufan Zhuang and Arijit Ray and Han Yu and
                   Zhongying CuiZhu and George Lee and Yifei Ming and Binz Roy and
                   Varun Sakalkar and Vishy Tirumalashetty and Burak Gokturk and
                   Tomas Pfister and Chen-Yu Lee},
  year          = {2026},
  eprint        = {2610.30537},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2610.30537}
}
```

## License

The dev tasks are released under the [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/) license.
