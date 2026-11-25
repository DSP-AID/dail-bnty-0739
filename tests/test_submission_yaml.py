"""Offline validation of submission.yaml with the vendored official kit spec."""

import os
import sys

sys.path.insert(0, ".")

from plekit import spec

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_submission_yaml_loads_with_official_spec():
  sub = spec.load(ROOT)  # raises spec.SpecError on any problem
  assert sub.name == "bnty-0739-harness-v2"
  # the final competition entry accepts only google-cloud/<model> pairings
  # (docs/models.md); locally it runs through MODEL_PROXY_URL/MODEL_PROXY_KEY
  assert sub.model.provider == "google-cloud"
  assert sub.model.name == "gemini-3.8-flash"
  assert sub.model.family == "gemini"
  # google-cloud models must not carry a model_base_url (kit rule)
  assert not sub.model.base_url


def test_serve_command_references_src_placeholder():
  sub = spec.load(ROOT)
  assert "{src}" in sub.serve and "serve.py" in sub.serve
  assert "{src}" in sub.install


def test_kit_google_cloud_env_is_resolved_by_the_harness():
  """The kit's own exported env for a google-cloud pairing must work here.

  `models.environment` is vendored from the kit: at final entry it exports
  OPENAI_BASE_URL/MODEL_BASE_URL (the organizer model server, ending in /v1)
  plus GOOGLE_GEMINI_BASE_URL and the keys. The harness has to pick the
  OpenAI-compatible one, not derive a path over the native base.
  """
  import serve
  from plekit import models

  sub = spec.load(ROOT)
  env = models.environment(sub.model, "organizer-key", "https://llm.example.org/v1")
  assert env["OPENAI_BASE_URL"] == "https://llm.example.org/v1"  # kit behaviour
  model, base_url, key = serve.resolve_endpoint(env)
  assert (model, base_url, key) == ("gemini-3.8-flash", "https://llm.example.org/v1", "organizer-key")


def test_gemini_native_pairing_falls_back_to_the_openai_path():
  """With only the native gemini base + key, derive the OpenAI-compatible path.

  The suffix is not invented: PROVIDERS["gemini"].base_url in the vendored kit
  is `<native_url>/v1beta/openai`, which is what this must reproduce.
  """
  import serve
  from plekit import models

  native = models.PROVIDERS["gemini"].native_url
  model, base_url, key = serve.resolve_endpoint(
      {"GOOGLE_GEMINI_BASE_URL": native + "/", "GEMINI_API_KEY": "own-key", "MODEL_NAME": "x"}
  )
  assert base_url == models.PROVIDERS["gemini"].base_url
  assert key == "own-key" and model == "x"


def test_own_endpoint_overrides_the_pairing():
  """`kit check --model-base-url` / our own server must win (docs/local-models.md)."""
  import serve

  _model, base_url, key = serve.resolve_endpoint(
      {
          "OPENAI_BASE_URL": "https://llm.example.org/v1",
          "GOOGLE_GEMINI_BASE_URL": "https://native.example.org",
          "OPENAI_API_KEY": "own-key",
          "GEMINI_API_KEY": "ignored",
      }
  )
  assert (base_url, key) == ("https://llm.example.org/v1", "own-key")

