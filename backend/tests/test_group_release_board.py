"""稀有分组处置 / 放行单 / 版本冲突 / 获准范围下载的领域规则测试。

完整覆盖任务脚本：K=3 → 隔离 2 人组 → 2+3 不相容拒并 → 3+1 相容归并成 4 行 →
补入一条 → 新检查与旧处置冲突 → 历史回执保留旧人数与原因 → 获准范围恰好 4 行。
"""
from __future__ import annotations

import pytest

from app.services.group_release import BoardError, VersionConflict, board


@pytest.fixture(autouse=True)
def _reset_board():
    board.reset()
    yield
    board.reset()


CID = 4  # 种子中的「分级交付样本·复诊随访」批次，自带 2/3/1 分组


def test_scenario_seed_has_2_3_1_groups_below_and_at_threshold():
    snap = board.snapshot(CID)
    counts = sorted(g["count"] for g in snap["groups"])
    assert counts == [1, 2, 3]
    low = {g["gid"] for g in snap["groups"] if g["below_threshold"]}
    assert low == {"GA", "GC"}  # 2 人组与 1 人组低于 K=3，3 人组恰好达标


def test_threshold_must_be_positive():
    with pytest.raises(BoardError):
        board.set_threshold(CID, 0)


def test_isolate_two_person_group_snapshots_count_and_reason():
    board.set_threshold(CID, 3)
    board.isolate(CID, "GA", "稀有二人组先隔离")
    snap = board.snapshot(CID)
    ga = next(g for g in snap["groups"] if g["gid"] == "GA")
    assert ga["verdict"] == "已隔离"
    receipt = snap["receipts"][0]
    assert receipt["action"] == "隔离"
    assert receipt["lines"][0]["count"] == 2
    assert "稀有二人组先隔离" in receipt["reason"]


def test_incompatible_2_and_3_groups_cannot_merge_and_state_unchanged():
    board.set_threshold(CID, 3)
    with pytest.raises(BoardError) as exc:
        board.merge(CID, ["GA", "GB"])
    assert exc.value.code == "MERGE_INCOMPATIBLE"
    snap = board.snapshot(CID)
    assert len(snap["merged_groups"]) == 0
    assert sorted(g["count"] for g in snap["groups"]) == [1, 2, 3]


def test_compatible_3_and_1_merge_into_four_delivery_rows():
    board.set_threshold(CID, 3)
    board.isolate(CID, "GA", "先隔离2人组，计划才完整")
    snap = board.merge(CID, ["GB", "GC"])
    merged = snap["merged_groups"][-1]
    assert merged["count"] == 4
    assert len(merged["members"]) == 4
    order = snap["publishable_order"]
    assert order is not None
    assert order["retained_count"] == 4
    assert order["removed_count"] == 2
    assert order["retained_member_ids"] == ["FY-1003", "FY-1004", "FY-1005", "FY-1006"]


def test_isolated_group_lands_in_removed_segment_only():
    board.set_threshold(CID, 3)
    board.isolate(CID, "GA", "隔离原因X")
    board.merge(CID, ["GB", "GC"])
    order = board.snapshot(CID)["publishable_order"]
    assert order["removed_count"] == 2
    assert order["retained_count"] == 4
    assert set(order["removed_member_ids"]) == {"FY-1001", "FY-1002"}
    # 同一样本不能同时出现在保留段与移除段
    assert not (set(order["retained_member_ids"]) & set(order["removed_member_ids"]))
    inv = board.snapshot(CID)["segment_check"]
    assert inv["retained"] == 4 and inv["removed"] == 2


def test_stale_disposition_conflicts_after_append_and_recheck_but_history_keeps_old_count():
    board.set_threshold(CID, 3)
    board.isolate(CID, "GA", "旧原因：当时只有2人")
    board.merge(CID, ["GB", "GC"])
    board.confirm(CID, base_version=1)

    board.add_member(CID, "GA")
    snap = board.recheck(CID)
    assert snap["version"] == 2
    conflict = next(c for c in snap["conflicts"] if c["gid"] == "GA")
    assert conflict["old_count"] == 2 and conflict["new_count"] == 3

    # 交错提交旧处置：必须判版本冲突，且不改写任何旧回执
    before = board.snapshot(CID)["receipts"]
    with pytest.raises(VersionConflict):
        board.confirm(CID, base_version=1)
    after = board.snapshot(CID)["receipts"]
    assert [r["id"] for r in after] == [r["id"] for r in before]

    detail = board.classify_detail(4)
    oldest = detail["receipts"][-1]
    assert oldest["action"] == "隔离"
    assert oldest["lines"][0]["count"] == 2
    assert "旧原因" in oldest["reason"]
    # 旧版放行单仍可发布，新检查冲突版本不可发布
    assert detail["publishable_order"]["rows"] and len(detail["publishable_order"]["rows"]) == 4
    states = {(v["publishable"], v["state_text"]) for v in detail["versions"]}
    assert any(p is True and "可发布" in text for p, text in states)
    assert any(p is False and "不可发布" in text for p, text in states)


def test_scope_csv_has_exactly_four_approved_rows_without_isolated_members():
    board.set_threshold(CID, 3)
    board.isolate(CID, "GA", "隔离")
    board.merge(CID, ["GB", "GC"])
    csv_text, order = board.scope_csv(4)
    lines = [ln for ln in csv_text.strip().splitlines()[1:] if ln]
    assert len(lines) == 4
    body = "\n".join(lines)
    assert "FY-1003" in body and "FY-1006" in body
    assert "FY-1001" not in body and "FY-1002" not in body


def test_unknown_batch_raises_not_found():
    with pytest.raises(BoardError) as exc:
        board.snapshot(9999)
    assert exc.value.code == "BATCH_NOT_FOUND"
