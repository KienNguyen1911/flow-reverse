"""Unit tests for the N-account pool (allocation math, selection, i2i templates).

Pure/discrete logic only — no browser and no network are involved:
``DummySupervisor`` replaces PoolSupervisor so nothing is launched.

Run:  python -m pytest tests -q
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.WebUI.jobs import BatchItem, plan_dependency_waves, prepare_batch_items  # noqa: E402
from src.Workflows.account_pool import (  # noqa: E402
    AccountPoolManager,
    ReferenceMediaRegistry,
)
from src.Workflows.flow_models import (  # noqa: E402
    build_args_from_template,
    build_image_args,
    captured_args_has_reference,
    mask_template_token,
)

FAKE_TOKEN = "0cAFcWeA" + ("x" * 500)


class DummySupervisor:
    def __init__(self, alive_ports=()):
        self.alive = set(alive_ports)
        self.launched: list[tuple[str, int]] = []

    def cdp_url(self, port: int) -> str:
        return f"http://127.0.0.1:{port}"

    def is_alive(self, port: int, timeout_s: float = 1.5) -> bool:
        return port in self.alive

    def ensure_running(self, profile_id: str, port: int, wait_timeout_s: float = 60.0) -> bool:
        if port in self.alive:            # mirrors PoolSupervisor: attach, never duplicate
            return True
        self.launched.append((profile_id, port))
        self.alive.add(port)
        return True

    def hibernate(self, profile_id: str, port: int, graceful_timeout_s: float = 6.0) -> dict:
        self.alive.discard(port)
        return {"ok": True, "reason": "closed"}

    def is_managed(self, profile_id: str) -> bool:
        return False

    def read_pid(self, profile_id: str):
        return None


def make_pool(tmp_path: Path, n_accounts: int = 4, state: dict | None = None,
              alive=()) -> AccountPoolManager:
    accounts = [
        {"id": f"acc_{i + 1:02d}", "profile_id": f"acc_{i + 1:02d}", "cdp_port": 9222 + i}
        for i in range(n_accounts)
    ]
    cfg = tmp_path / "accounts_pool.json"
    cfg.write_text(json.dumps({
        "target_jobs_per_account": 25,
        "max_active_browsers": 4,
        "port_base": 9222,
        "accounts": accounts,
    }), encoding="utf-8")
    state_path = tmp_path / "pool_state.json"
    if state:
        state_path.write_text(json.dumps(state), encoding="utf-8")
    return AccountPoolManager(
        config_path=cfg,
        state_path=state_path,
        breaker_dir=tmp_path / "breakers",
        ref_cache_path=tmp_path / "reference_media_cache.json",
        vault_dir=tmp_path / "vault",
        out_root=tmp_path / "out",
        supervisor=DummySupervisor(alive),
        log=lambda *_: None,
    )


def trip_breaker(tmp_path: Path, account_id: str, seconds: float) -> None:
    breaker_dir = tmp_path / "breakers"
    breaker_dir.mkdir(parents=True, exist_ok=True)
    (breaker_dir / f"{account_id}.json").write_text(json.dumps({
        "cooldown_until_ms": int(time.time() * 1000 + seconds * 1000),
        "cooldown_reason": "test",
        "consecutive_anti_abuse": 0,
        "last_anti_abuse_ms": 0,
        "total_accepted": 0,
        "total_rejected": 0,
    }), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Allocation math — docs/upgrade_plan_n_account_pool.md §1.1/§1.2
# --------------------------------------------------------------------------- #


def test_allocation_formula_plan_table(tmp_path):
    pool = make_pool(tmp_path, n_accounts=4)
    assert pool.compute_allocation(1) == 1
    assert pool.compute_allocation(12) == 1      # Pha 1 anchor assets
    assert pool.compute_allocation(25) == 1
    assert pool.compute_allocation(26) == 2
    assert pool.compute_allocation(50) == 2
    assert pool.compute_allocation(75) == 3
    assert pool.compute_allocation(100) == 4


def test_allocation_capped_by_n(tmp_path):
    pool = make_pool(tmp_path, n_accounts=8)
    assert pool.compute_allocation(100) == 4     # min(N=8, M_RAM=4, ceil(100/25)=4)


def test_allocation_capped_by_m_ram(tmp_path):
    pool = make_pool(tmp_path, n_accounts=4)
    pool.max_active_browsers = 2
    assert pool.compute_allocation(100, max_ram=2) == 2


def test_allocation_single_account(tmp_path):
    pool = make_pool(tmp_path, n_accounts=1)
    assert pool.compute_allocation(100) == 1


def test_allocation_zero_when_all_cooldown(tmp_path):
    pool = make_pool(tmp_path, n_accounts=2)
    for aid in ("acc_01", "acc_02"):
        trip_breaker(tmp_path, aid, 600)
    assert pool.available_accounts() == []
    assert pool.compute_allocation(50) == 0


def test_allocation_shrinks_when_one_cooldown(tmp_path):
    pool = make_pool(tmp_path, n_accounts=4)
    trip_breaker(tmp_path, "acc_01", 600)
    assert len(pool.available_accounts()) == 3
    assert pool.compute_allocation(100) == 3


# --------------------------------------------------------------------------- #
# Selection: wear-leveling + sticky affinity (plan §1.3 / Phần 2)
# --------------------------------------------------------------------------- #


def test_selection_wear_leveling(tmp_path):
    pool = make_pool(tmp_path, n_accounts=4, state={"accounts": {
        "acc_01": {"total_completed": 50, "last_used_at_ms": 9_000},
        "acc_02": {"total_completed": 25, "last_used_at_ms": 8_000},
    }})
    picked = [a.id for a in pool.select_working_set(2)]
    assert picked == ["acc_03", "acc_04"]


def test_selection_prefers_affinity(tmp_path):
    pool = make_pool(tmp_path, n_accounts=4, state={"accounts": {
        "acc_02": {"total_completed": 500, "last_used_at_ms": 9_999_999},
    }})
    pool.registry.put("acc_02", {"sha256": "deadbeef"})
    picked = pool.select_working_set(1, affinity_shas={"deadbeef"})
    assert [a.id for a in picked] == ["acc_02"]


def test_selection_excludes(tmp_path):
    pool = make_pool(tmp_path, n_accounts=3)
    picked = [a.id for a in pool.select_working_set(2, exclude={"acc_01"})]
    assert picked == ["acc_02", "acc_03"]


def test_ensure_working_set_wakes_only_selected(tmp_path):
    pool = make_pool(tmp_path, n_accounts=4, alive=(9222,))  # acc_01 already up
    active, errors = pool.ensure_working_set(pool.select_working_set(2))
    assert errors == []
    assert [a.config.id for a in active] == ["acc_01", "acc_02"]
    launched = [p for _pid, p in pool.supervisor.launched]
    assert launched == [9223]  # acc_01 attached, acc_02 woken on demand


def test_promote_standby_skips_working_set(tmp_path):
    pool = make_pool(tmp_path, n_accounts=3)
    active, _ = pool.ensure_working_set(pool.select_working_set(1))
    promoted = pool.promote_standby(exclude=[a.config.id for a in active])
    assert promoted is not None
    assert promoted.config.id == "acc_02"


# --------------------------------------------------------------------------- #
# Reference media registry (plan Phần 2 — lazy upload once per account)
# --------------------------------------------------------------------------- #


def test_registry_roundtrip_and_counts(tmp_path):
    reg = ReferenceMediaRegistry(tmp_path / "refs.json")
    assert reg.get("acc_01", "sha1") is None
    reg.put("acc_01", {"sha256": "sha1", "media_id": "m1", "template_args": [1, 2]})
    reg.put("acc_02", {"sha256": "sha2", "media_id": "m2"})
    assert reg.get("acc_01", "sha1")["media_id"] == "m1"
    assert reg.has("acc_02", "sha2")
    assert reg.count_for("acc_01", ["sha1", "sha2", "sha3"]) == 1
    # reload from disk
    reg2 = ReferenceMediaRegistry(tmp_path / "refs.json")
    assert reg2.get("acc_01", "sha1")["template_args"] == [1, 2]


# --------------------------------------------------------------------------- #
# i2i template helpers (never guess the upload protocol: capture + substitute)
# --------------------------------------------------------------------------- #


def test_captured_args_has_reference_detects_t2i_baseline():
    args = build_image_args("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "a duck", FAKE_TOKEN, 123)
    assert captured_args_has_reference(args) is False
    ref = args[1][0][7]
    ref[2] = "f0e1d2c3-b4a5-9687-7869-5a4b3c2d1e0f"  # app adds a media ref
    assert captured_args_has_reference(args) is True


def test_mask_template_token_blanks_slot():
    args = build_image_args("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "a duck", FAKE_TOKEN, 123)
    masked = mask_template_token(args)
    assert masked[1][0][7][10][0] == ""
    assert args[1][0][7][10][0] == FAKE_TOKEN  # original untouched


def test_build_args_from_template_substitutes_all():
    old_prompt = "old character master shot"
    template = mask_template_token(
        build_image_args("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", old_prompt, FAKE_TOKEN, 999)
    )
    args, replaced = build_args_from_template(
        template,
        token=FAKE_TOKEN, seed=4242, prompt="new action shot", old_prompt=old_prompt,
        u1="11111111-1111-1111-1111-111111111111".upper(),
        u2="22222222-2222-2222-2222-222222222222".upper(),
        gen_id="33333333-3333-3333-3333-333333333333".upper(),
    )
    assert replaced["token"] and replaced["seed"] and replaced["prompt"] == 1 and replaced["uuids"] == 3
    assert args[1][0][3] == 4242
    assert args[1][0][7][10][0] == FAKE_TOKEN
    assert args[1][0][8] == [[["new action shot"]]]
    assert args[1][0][12] == "11111111-1111-1111-1111-111111111111"


def test_build_args_from_template_missing_prompt_raises():
    template = mask_template_token(
        build_image_args("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "typed prompt", FAKE_TOKEN, 1)
    )
    try:
        build_args_from_template(template, token=FAKE_TOKEN, seed=5, prompt="new", old_prompt="not present")
    except ValueError:
        return
    raise AssertionError("expected ValueError when old prompt is absent")


# --------------------------------------------------------------------------- #
# Dependency waves (plan Phần 3 — anchor → continuity → b-roll)
# --------------------------------------------------------------------------- #


def _item(idx: int, shot: str | None = None, dep: str | None = None, mode: str = "t2i") -> BatchItem:
    return BatchItem(idx=idx, prompt=f"p{idx}", mode=mode, shot_id=shot, depends_on_shot_id=dep)


def test_plan_dependency_waves_three_stages():
    a1 = _item(0, "a1")
    a2 = _item(1, "a2")
    b1 = _item(2, "b1", dep="a1", mode="i2i")
    b2 = _item(3, "b2", dep="a2", mode="i2i")
    c1 = _item(4, "c1")  # b-roll, no deps → runs wave 1 alongside anchors
    waves = plan_dependency_waves([a1, a2, b1, b2, c1])
    assert [[it.shot_id for it in w] for w in waves] == [["a1", "a2", "c1"], ["b1", "b2"]]


def test_plan_dependency_waves_missing_dep_skipped():
    b1 = _item(0, "b1", dep="ghost", mode="i2i")
    waves = plan_dependency_waves([b1])
    assert waves == []
    assert b1.status == "skipped" and "ghost" in b1.error


def test_plan_dependency_waves_cycle_skipped():
    x = _item(0, "x", mode="i2i")
    y = _item(1, "y", dep="x", mode="i2i")
    x.depends_on_shot_id = "y"
    waves = plan_dependency_waves([x, y])
    assert waves == []
    assert x.status == "skipped" and y.status == "skipped"


# --------------------------------------------------------------------------- #
# Batch item preparation (inline items + storyboard file)
# --------------------------------------------------------------------------- #


def test_prepare_batch_items_mode_inference():
    items = prepare_batch_items({"items": [
        {"prompt": "a"},
        {"prompt": "b", "reference_image_path": "ref.png"},
        {"prompt": "c", "depends_on_shot_id": "x", "id": "y"},
    ]})
    assert [it.mode for it in items] == ["t2i", "i2i", "i2i"]
    assert items[1].reference_image_path == "ref.png"
    assert items[2].depends_on_shot_id == "x"
    assert items[2].shot_id == "y"


def test_prepare_batch_items_rejects_bad_i2i():
    with pytest.raises(ValueError):
        prepare_batch_items({"items": [{"prompt": "a", "mode": "i2i"}]})


def test_prepare_batch_items_rejects_empty():
    with pytest.raises(ValueError):
        prepare_batch_items({"items": []})


def test_prepare_batch_items_from_example_storyboard():
    items = prepare_batch_items({"storyboard_path": "configs/storyboard_100.json"})
    assert len(items) == 6
    assert {it.mode for it in items} == {"t2i", "i2i"}
    waves = plan_dependency_waves(items)
    # wave 1: anchors + explicit-ref shot + b-roll; wave 2: depends_on shots
    assert [it.shot_id for it in waves[0]] == [
        "anchor_char_01", "anchor_env_01", "scene_002_shot_001", "broll_001",
    ]
    assert [it.shot_id for it in waves[1]] == ["scene_001_shot_001", "scene_001_shot_002"]


def test_example_pool_config_is_loadable(tmp_path):
    cfg = ROOT / "configs" / "accounts_pool.json"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["target_jobs_per_account"] == 25
    assert data["auto_discover"] is True
    assert data["accounts"] == []
