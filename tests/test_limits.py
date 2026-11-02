"""Limits resolution: env → configs/limits.json → defaults (single source of truth)."""

from __future__ import annotations

import json

import pytest

from src.Workflows import limits as limits_mod


@pytest.fixture(autouse=True)
def _clear_cache():
    limits_mod.reset_cache()
    yield
    limits_mod.reset_cache()


def test_defaults_when_nothing_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(limits_mod, "LIMITS_CONFIG", tmp_path / "missing.json")
    monkeypatch.delenv("FLOWBENCH_MAX_PROMPT_CHARS", raising=False)
    monkeypatch.delenv("FLOWBENCH_MAX_BATCH_ITEMS", raising=False)

    lim = limits_mod.load_limits()
    assert lim.max_prompt_chars == limits_mod.DEFAULT_MAX_PROMPT_CHARS == 7200
    assert lim.max_batch_items == limits_mod.DEFAULT_MAX_BATCH_ITEMS == 300


def test_config_file_overrides_defaults(tmp_path, monkeypatch):
    cfg = tmp_path / "limits.json"
    cfg.write_text(json.dumps({"max_prompt_chars": 9000, "max_batch_items": 42}), encoding="utf-8")
    monkeypatch.setattr(limits_mod, "LIMITS_CONFIG", cfg)
    monkeypatch.delenv("FLOWBENCH_MAX_PROMPT_CHARS", raising=False)
    monkeypatch.delenv("FLOWBENCH_MAX_BATCH_ITEMS", raising=False)

    lim = limits_mod.load_limits()
    assert lim.max_prompt_chars == 9000
    assert lim.max_batch_items == 42


def test_env_beats_config_file(tmp_path, monkeypatch):
    cfg = tmp_path / "limits.json"
    cfg.write_text(json.dumps({"max_prompt_chars": 9000}), encoding="utf-8")
    monkeypatch.setattr(limits_mod, "LIMITS_CONFIG", cfg)
    monkeypatch.setenv("FLOWBENCH_MAX_PROMPT_CHARS", "12345")

    assert limits_mod.load_limits().max_prompt_chars == 12345


@pytest.mark.parametrize("raw", ["0", "-5", "abc", "", "nan"])
def test_bad_values_fall_back_to_default(tmp_path, monkeypatch, raw):
    monkeypatch.setattr(limits_mod, "LIMITS_CONFIG", tmp_path / "missing.json")
    monkeypatch.setenv("FLOWBENCH_MAX_PROMPT_CHARS", raw)
    assert limits_mod.load_limits().max_prompt_chars == limits_mod.DEFAULT_MAX_PROMPT_CHARS


def test_absurd_values_are_clamped(tmp_path, monkeypatch):
    monkeypatch.setattr(limits_mod, "LIMITS_CONFIG", tmp_path / "missing.json")
    monkeypatch.setenv("FLOWBENCH_MAX_PROMPT_CHARS", "999999999")
    assert limits_mod.load_limits().max_prompt_chars == 200_000


def test_corrupt_config_file_is_ignored(tmp_path, monkeypatch):
    cfg = tmp_path / "limits.json"
    cfg.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(limits_mod, "LIMITS_CONFIG", cfg)
    monkeypatch.delenv("FLOWBENCH_MAX_PROMPT_CHARS", raising=False)

    assert limits_mod.load_limits().max_prompt_chars == limits_mod.DEFAULT_MAX_PROMPT_CHARS


def test_node_options_exposes_limits():
    """UI reads `/api/node/options -> limits`; keep the key stable."""
    from src.Workflows.media_service import node_options

    opts = node_options()
    assert opts["limits"]["max_prompt_chars"] == limits_mod.load_limits().max_prompt_chars
    assert opts["limits"]["max_batch_items"] == limits_mod.load_limits().max_batch_items
