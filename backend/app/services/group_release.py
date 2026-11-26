"""稀有分组处置 / 放行单领域服务。

核心业务约束（与前端「分组处置面板」「分级分类详情」共用同一份服务端事实）：

1. 处置必须基于某个 K 匿名检查批次以及该批次核对时的阈值 / 版本；
2. 低于阈值的等价类分组只有两条出路：
   - 隔离：整组人数进入移除段，不进入交付样本；
   - 复核后归并：只能与「确实相容」的分组归并，合并后总人数达到阈值；
3. 交付（获准范围）中不得包含仍低于阈值的分组；
4. 任一分组的人数只能完整计入保留段或移除段之一，禁止两边重复计数；
5. 处置确认生成不可变回执 / 放行单版本，快照当时人数与原因；
   之后重新检查导致人数 / 版本变化时，旧处置提交会得到版本冲突，
   旧回执与旧放行单不被改写，最近一版已确认范围仍可发布 / 下载。

内存仓库：进程内单例，结构与 app.store 的示例数据保持独立但同样可重建。
"""
from __future__ import annotations

import copy
import threading
from datetime import datetime
from typing import Any

from app.store import store


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class BoardError(Exception):
    """业务校验错误：携带稳定 code，路由层统一转成 {ok:False,...}。"""

    def __init__(self, message: str, *, code: str = "BOARD_INVALID") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class VersionConflict(BoardError):
    def __init__(self, message: str, **extra: Any) -> None:
        super().__init__(message, code="VERSION_CONFLICT")
        self.extra = extra


# ---------------------------------------------------------------------------
# 场景种子：人数 2 的组（隔离）、人数 3 的组、与 3 人组相容的 1 人组。
# 相容性由准标识符泛化规则 + 显式相容关系共同决定，并给出可读原因。
# ---------------------------------------------------------------------------

QI_FIELDS = ["年龄段", "邮编片区", "性别"]

_SCENARIO_GROUPS: list[dict[str, Any]] = [
    {
        "gid": "GA",
        "code": "QI-A",
        "qi": {"年龄段": "30-34", "邮编片区": "200082", "性别": "女"},
        "sensitive_class": "传染病随访",
        "compatible": [],
        "incompatible": ["GB"],
        "incompat_reason": "性别取值不同（女/男）且不允许泛化，敏感随访等级也不相容",
        "members": [
            {"样本编号": "FY-1001", "年龄段": "30-34", "邮编片区": "200082", "性别": "女", "随访项目": "传染病复查"},
            {"样本编号": "FY-1002", "年龄段": "30-34", "邮编片区": "200082", "性别": "女", "随访项目": "传染病复查"},
        ],
    },
    {
        "gid": "GB",
        "code": "QI-B",
        "qi": {"年龄段": "35-39", "邮编片区": "200085", "性别": "男"},
        "sensitive_class": "常规随访",
        "compatible": ["GC"],
        "incompatible": ["GA"],
        "incompat_reason": "性别取值不同（男/女）且不允许泛化，敏感随访等级也不相容",
        "members": [
            {"样本编号": "FY-1003", "年龄段": "35-39", "邮编片区": "200085", "性别": "男", "随访项目": "术后随访"},
            {"样本编号": "FY-1004", "年龄段": "35-39", "邮编片区": "200085", "性别": "男", "随访项目": "术后随访"},
            {"样本编号": "FY-1005", "年龄段": "35-39", "邮编片区": "200085", "性别": "男", "随访项目": "用药回访"},
        ],
    },
    {
        "gid": "GC",
        "code": "QI-C",
        "qi": {"年龄段": "40-44", "邮编片区": "200086", "性别": "男"},
        "sensitive_class": "常规随访",
        "compatible": ["GB"],
        "incompatible": [],
        "incompat_reason": "",
        "members": [
            {"样本编号": "FY-1006", "年龄段": "40-44", "邮编片区": "200086", "性别": "男", "随访项目": "用药回访"},
        ],
    },
]

# 补入小组成员时使用的新编号池，保证多次补入也不重复。
_APPEND_POOL = [
    {"样本编号": "FY-2001", "随访项目": "补录随访"},
    {"样本编号": "FY-2002", "随访项目": "补录随访"},
    {"样本编号": "FY-2003", "随访项目": "补录随访"},
]


def qi_text(group: dict[str, Any]) -> str:
    qi = group.get("qi") or {}
    return " / ".join(str(qi.get(field, "")) for field in QI_FIELDS)


class GroupReleaseBoard:
    """按检查批次持有处置工作台状态（进程内单例）。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._states: dict[int, dict[str, Any]] = {}
        self._classify_link: dict[int, int] = {}

    # ------------------------------------------------------------------ state

    def reset(self) -> None:
        with self._lock:
            self._states.clear()

    def classify_tag_for(self, check_id: int) -> int:
        return self._classify_link.get(check_id, 4)

    def link_classify_tag(self, check_id: int, tag_id: int) -> None:
        self._classify_link[check_id] = tag_id

    def _check_row(self, check_id: int) -> dict[str, Any] | None:
        return store.find("k_anonymity", check_id)

    def ensure_state(self, check_id: int) -> dict[str, Any]:
        """读取 / 懒初始化某个检查批次的工作台状态。

        对任意真实存在的 k_anonymity 批次都提供同一套 2/3/1 示例分组，
        这样审核员从任意批次进入都能完成规定处置流程。
        """
        with self._lock:
            if check_id in self._states:
                return self._states[check_id]
            row = self._check_row(check_id)
            if row is None:
                raise BoardError(f"检查批次 {check_id} 不存在", code="BATCH_NOT_FOUND")
            try:
                threshold = int(str(row.get("K值要求", "3")).strip() or 3)
            except ValueError:
                threshold = 3
            state: dict[str, Any] = {
                "check_id": check_id,
                "check_no": row.get("检查编号", f"K_AN-{check_id:04d}"),
                "dataset": row.get("数据集名称", ""),
                "threshold": threshold,
                "version": 1,
                "groups": copy.deepcopy(_SCENARIO_GROUPS),
                "merged_groups": [],
                "dispositions": [],
                "receipts": [],
                "orders": {},
                "order_versions": [],
                "publishable_order_id": None,
                "conflicts": [],
                "append_cursor": 0,
                "receipt_seq": 0,
                "order_seq": 0,
                "created_at": _now(),
            }
            self._states[check_id] = state
            return state

    # ------------------------------------------------------------- serialization

    def _group_count(self, group: dict[str, Any]) -> int:
        return len(group.get("members", []))

    def _public_group(self, state: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
        threshold = int(state["threshold"])
        count = self._group_count(group)
        merged_into = group.get("merged_into")
        disposition = self._disposition_of(state, group["gid"])
        if merged_into:
            verdict = "已归并"
            below = False
        elif disposition and disposition["type"] == "isolate":
            verdict = "已隔离"
            below = True
        elif count >= threshold:
            verdict = "达标"
            below = False
        else:
            verdict = "低于阈值"
            below = True
        compat_codes = [
            self._group_code(state, gid) for gid in group.get("compatible", [])
            if self._raw_group(state, gid) is not None
        ]
        return {
            "gid": group["gid"],
            "code": group.get("code", group["gid"]),
            "qi": group.get("qi", {}),
            "qi_text": qi_text(group),
            "sensitive_class": group.get("sensitive_class", ""),
            "count": count,
            "actual_count": count,
            "below_threshold": below and not merged_into,
            "verdict": verdict,
            "merged_into": merged_into,
            "compatible_with": group.get("compatible", []),
            "compatible_codes": compat_codes,
            "incompatible_with": group.get("incompatible", []),
            "incompat_reason": group.get("incompat_reason", ""),
            "compat_text": self._compat_text(group, compat_codes),
            "members": copy.deepcopy(group.get("members", [])),
            "disposition": disposition,
            "snapshot_count": (
                disposition.get("count_snapshot")
                if disposition and disposition.get("type") == "isolate"
                else None
            ),
            "data_population": count,
        }

    def _compat_text(self, group: dict[str, Any], compat_codes: list[str]) -> str:
        parts: list[str] = []
        if compat_codes:
            parts.append("相容：可与 " + "、".join(compat_codes) + " 归并")
        if group.get("incompatible"):
            reason = group.get("incompat_reason") or "准标识符 / 敏感等级不相容"
            bad = "、".join(group["incompatible"])
            parts.append(f"与 {bad} 不相容（{reason}）")
        return "；".join(parts) or "未标注相容关系"

    def _raw_group(self, state: dict[str, Any], gid: str) -> dict[str, Any] | None:
        for group in state["groups"]:
            if group["gid"] == gid:
                return group
        return None

    def _group_code(self, state: dict[str, Any], gid: str) -> str:
        group = self._raw_group(state, gid)
        return str(group.get("code", gid)) if group else gid

    def _disposition_of(self, state: dict[str, Any], gid: str) -> dict[str, Any] | None:
        for disp in state["dispositions"]:
            if gid in disp.get("gids", []):
                return disp
        return None

    def snapshot(self, check_id: int) -> dict[str, Any]:
        with self._lock:
            state = self.ensure_state(check_id)
            row = self._check_row(check_id) or {}
            groups = [self._public_group(state, g) for g in state["groups"]]
            merged: list[dict[str, Any]] = []
            for mg in state["merged_groups"]:
                item = copy.deepcopy(mg)
                item["count"] = len(item.get("members", []))
                item["rows_text"] = f"合并组交付：{item['count']} 行"
                merged.append(item)
            order = self._publishable_order(state)
            return {
                "ok": True,
                "check_id": check_id,
                "check_no": state["check_no"],
                "dataset": state["dataset"],
                "check_status": row.get("status"),
                "threshold": state["threshold"],
                "version": state["version"],
                "qi_fields": QI_FIELDS,
                "groups": groups,
                "merged_groups": merged,
                "dispositions": copy.deepcopy(state["dispositions"]),
                "receipts": copy.deepcopy(list(reversed(state["receipts"]))),
                "conflicts": copy.deepcopy(state["conflicts"]),
                "publishable_order": order,
                "orders": copy.deepcopy(state["order_versions"]),
                "classify_tag_id": self.classify_tag_for(check_id),
                "segment_check": self._segment_invariant(state),
            }

    # ------------------------------------------------------------- threshold

    def set_threshold(self, check_id: int, threshold: int) -> dict[str, Any]:
        with self._lock:
            state = self.ensure_state(check_id)
            if threshold < 1:
                raise BoardError("匿名阈值 K 必须是不小于 1 的整数", code="BAD_THRESHOLD")
            state["threshold"] = int(threshold)
            row = self._check_row(check_id)
            if row is not None:
                row["K值要求"] = str(threshold)
            return self.snapshot(check_id)

    # ------------------------------------------------------------- compatibility

    def _check_compatible(self, state: dict[str, Any], gids: list[str]) -> None:
        if len(gids) < 2:
            raise BoardError("归并至少需要选择两个分组", code="MERGE_NEED_TWO")
        raws: list[dict[str, Any]] = []
        for gid in gids:
            group = self._raw_group(state, gid)
            if group is None:
                raise BoardError(f"分组 {gid} 不存在或已归并", code="GROUP_NOT_FOUND")
            if group.get("merged_into"):
                raise BoardError(f"{group.get('code', gid)} 已参与归并，不能重复归并",
                                 code="GROUP_ALREADY_MERGED")
            raws.append(group)
        # 显式不相容 / 未建立相容关系都视为“不满足归并条件”。
        for i, ga in enumerate(raws):
            for gb in raws[i + 1:]:
                a_to_b = gb["gid"] in (ga.get("compatible") or [])
                b_to_a = ga["gid"] in (gb.get("compatible") or [])
                explicit_bad = (
                    gb["gid"] in (ga.get("incompatible") or [])
                    or ga["gid"] in (gb.get("incompatible") or [])
                )
                reason = ga.get("incompat_reason") or gb.get("incompat_reason") or \
                    "准标识符泛化层级或敏感属性不相容"
                if explicit_bad or not (a_to_b and b_to_a):
                    raise BoardError(
                        "所选分组不相容，不满足归并条件："
                        f"{ga.get('code', ga['gid'])} 与 {gb.get('code', gb['gid'])} "
                        f"不能归并（{reason}）",
                        code="MERGE_INCOMPATIBLE",
                    )

    # ------------------------------------------------------------- dispositions

    def _next_receipt_id(self, state: dict[str, Any]) -> str:
        state["receipt_seq"] += 1
        return f"HZ-{state['check_no'].split('-')[-1]}-{state['receipt_seq']:02d}"

    def _append_receipt(
        self,
        state: dict[str, Any],
        *,
        action: str,
        lines: list[dict[str, Any]],
        reason: str,
        base_version: int,
        operator: str = "审核员",
    ) -> dict[str, Any]:
        receipt = {
            "id": self._next_receipt_id(state),
            "action": action,
            "reason": reason,
            "operator": operator,
            "base_check_version": base_version,
            "created_at": _now(),
            "threshold": state["threshold"],
            "lines": lines,
        }
        # 每行补一句可直接展示 / 断言的中文处置描述。
        for line in lines:
            line.setdefault("text", self._line_text(line))
        state["receipts"].append(receipt)
        return copy.deepcopy(receipt)

    @staticmethod
    def _line_text(line: dict[str, Any]) -> str:
        kind = line.get("kind")
        if kind == "isolate":
            return f"隔离 {line.get('code')} 组 {line.get('count')} 人，全部计入移除段"
        if kind == "merge":
            parts = "、".join(
                f"{code}({cnt}人)" for code, cnt in zip(line.get("codes", []), line.get("counts", []))
            )
            return (f"归并 {parts} → {line.get('merged_code')}，"
                    f"合并组 {line.get('total')} 人达到阈值，全部计入保留段")
        if kind == "retain":
            return f"保留 {line.get('code')} 组 {line.get('count')} 人（满足阈值）"
        return str(line.get("text", ""))

    def isolate(self, check_id: int, gid: str, reason: str | None = None) -> dict[str, Any]:
        with self._lock:
            state = self.ensure_state(check_id)
            group = self._raw_group(state, gid)
            if group is None:
                raise BoardError(f"分组 {gid} 不存在", code="GROUP_NOT_FOUND")
            if group.get("merged_into"):
                raise BoardError("已归并的分组不能再隔离", code="GROUP_MERGED")
            count = self._group_count(group)
            base_version = int(state["version"])
            final_reason = (reason or "").strip() or \
                f"人数 {count} 低于 K={state['threshold']}，先行隔离，不进入交付样本"
            # 同组重复隔离：覆盖原处置但保留追加回执轨迹。
            state["dispositions"] = [d for d in state["dispositions"] if gid not in d["gids"]]
            disp = {
                "key": f"isolate-{gid}",
                "type": "isolate",
                "gids": [gid],
                "count_snapshot": count,
                "reason": final_reason,
                "base_version": base_version,
                "at": _now(),
            }
            state["dispositions"].append(disp)
            line = {
                "kind": "isolate",
                "gid": gid,
                "code": group.get("code", gid),
                "count": count,
                "retained": 0,
                "removed": count,
            }
            self._append_receipt(
                state, action="隔离", lines=[line], reason=final_reason,
                base_version=base_version)
            self._refresh_order(state)
            return self.snapshot(check_id)

    def merge(self, check_id: int, gids: list[str], reason: str | None = None) -> dict[str, Any]:
        with self._lock:
            state = self.ensure_state(check_id)
            self._check_compatible(state, gids)
            base_version = int(state["version"])
            raws = [self._raw_group(state, gid) for gid in gids]
            counts = [self._group_count(g) for g in raws]  # type: ignore[arg-type]
            total = sum(counts)
            mgid = f"MG{len(state['merged_groups']) + 1}"
            merged_code = f"归并组-{'+'.join(str(g.get('code', g['gid'])) for g in raws)}"  # type: ignore[union-attr]
            members: list[dict[str, Any]] = []
            for g in raws:
                members.extend(copy.deepcopy(g["members"]))  # type: ignore[index]
                g["merged_into"] = mgid  # type: ignore[index]
            merged = {
                "mgid": mgid,
                "code": merged_code,
                "merged_from": list(gids),
                "from_codes": [g.get("code", g["gid"]) for g in raws],  # type: ignore[union-attr]
                "count": total,
                "members": members,
                "at": _now(),
            }
            state["merged_groups"].append(merged)
            # 清掉这些组上原有的处置，写入归并处置。
            state["dispositions"] = [
                d for d in state["dispositions"] if not any(g in d["gids"] for g in gids)
            ]
            merge_reason = (reason or "").strip() or \
                "准标识符可泛化、随访等级一致，复核确认相容后归并"
            disp = {
                "key": f"merge-{'-'.join(gids)}",
                "type": "merge",
                "gids": list(gids),
                "counts_snapshot": dict(zip(gids, counts)),
                "total_snapshot": total,
                "merged_id": mgid,
                "reason": merge_reason,
                "base_version": base_version,
                "at": _now(),
            }
            state["dispositions"].append(disp)
            line = {
                "kind": "merge",
                "gids": list(gids),
                "codes": [g.get("code", g["gid"]) for g in raws],  # type: ignore[union-attr]
                "counts": counts,
                "merged_id": mgid,
                "merged_code": merged_code,
                "total": total,
                "retained": total,
                "removed": 0,
            }
            self._append_receipt(
                state, action="归并", lines=[line], reason=merge_reason,
                base_version=base_version)
            self._refresh_order(state)
            return self.snapshot(check_id)

    def add_member(self, check_id: int, gid: str) -> dict[str, Any]:
        """给指定小组补入一条样本（克隆该组 QI，保证重新检查仍落同组）。"""
        with self._lock:
            state = self.ensure_state(check_id)
            group = self._raw_group(state, gid)
            if group is None:
                # 允许直接给合并组补入：落到第一个来源组。
                mg = next((m for m in state["merged_groups"] if m["mgid"] == gid), None)
                if mg is None or not mg["merged_from"]:
                    raise BoardError(f"分组 {gid} 不存在", code="GROUP_NOT_FOUND")
                group = self._raw_group(state, mg["merged_from"][0])
            assert group is not None
            cursor = state["append_cursor"]
            extra = _APPEND_POOL[min(cursor, len(_APPEND_POOL) - 1)]
            state["append_cursor"] += 1
            qi = group.get("qi", {})
            member = {
                "样本编号": f"FY-2{1000 + cursor + 1:03d}",
                **{field: qi.get(field, "") for field in QI_FIELDS},
                "随访项目": extra["随访项目"],
            }
            group["members"].append(member)
            if group.get("merged_into"):
                mg = next(m for m in state["merged_groups"] if m["mgid"] == group["merged_into"])
                mg["members"].append(copy.deepcopy(member))
            return self.snapshot(check_id)

    # ------------------------------------------------------------- recheck

    def recheck(self, check_id: int) -> dict[str, Any]:
        with self._lock:
            state = self.ensure_state(check_id)
            state["version"] += 1
            conflicts: list[dict[str, Any]] = []
            for disp in state["dispositions"]:
                if disp["type"] == "isolate":
                    gid = disp["gids"][0]
                    group = self._raw_group(state, gid)
                    current = self._group_count(group) if group else 0
                    old = int(disp.get("count_snapshot", current))
                    if current != old:
                        conflicts.append({
                            "type": "count_drift",
                            "gid": gid,
                            "code": self._group_code(state, gid),
                            "disposition": "隔离",
                            "old_count": old,
                            "new_count": current,
                            "base_version": disp.get("base_version", 1),
                            "current_version": state["version"],
                            "message": (
                                f"{self._group_code(state, gid)} 组旧处置按 {old} 人隔离，"
                                f"重新检查后为 {current} 人；旧处置与新检查结果冲突"
                            ),
                        })
                if disp["type"] == "merge":
                    for gid, old in (disp.get("counts_snapshot") or {}).items():
                        group = self._raw_group(state, gid)
                        current = self._group_count(group) if group else 0
                        if current != int(old):
                            conflicts.append({
                                "type": "count_drift",
                                "gid": gid,
                                "code": self._group_code(state, gid),
                                "disposition": "归并",
                                "old_count": old,
                                "new_count": current,
                                "base_version": disp.get("base_version", 1),
                                "current_version": state["version"],
                                "message": (
                                    f"{self._group_code(state, gid)} 组归并快照为 {old} 人，"
                                    f"重新检查后为 {current} 人；旧处置与新检查结果冲突"
                                ),
                            })
            state["conflicts"] = conflicts
            row = self._check_row(check_id)
            if row is not None:
                min_size = min(
                    (self._group_count(g) for g in state["groups"] if not g.get("merged_into")),
                    default=0,
                )
                row["最小等价类大小"] = str(min_size)
                row["检查结论"] = (
                    f"第 {state['version']} 次核查：阈值 K={state['threshold']}，"
                    + ("存在处置版本冲突" if conflicts else "分组与处置一致")
                )
            snap = self.snapshot(check_id)
            snap["conflict"] = bool(conflicts)
            return snap

    # ------------------------------------------------------------- confirm / order

    def _segment_invariant(self, state: dict[str, Any]) -> dict[str, Any]:
        """核对保留段 / 移除段互斥且人数不重复。"""
        retained = 0
        removed = 0
        assigned_groups: set[str] = set()
        for disp in state["dispositions"]:
            gids = disp["gids"]
            for gid in gids:
                if gid in assigned_groups:
                    raise BoardError(f"分组 {gid} 的人数被重复计入两个段",
                                     code="DOUBLE_COUNT")
                assigned_groups.add(gid)
            if disp["type"] == "isolate":
                removed += int(disp.get("count_snapshot", 0))
            elif disp["type"] == "merge":
                retained += int(disp.get("total_snapshot", 0))
        return {
            "assigned_groups": sorted(assigned_groups),
            "retained": retained,
            "removed": removed,
            "double_count": False,
        }

    def _plan_complete(self, state: dict[str, Any]) -> bool:
        """所有低于阈值的未归并原始组都必须已隔离。"""
        threshold = int(state["threshold"])
        handled: set[str] = set()
        for disp in state["dispositions"]:
            handled.update(disp["gids"])
        for group in state["groups"]:
            if group.get("merged_into"):
                continue
            count = self._group_count(group)
            gid = group["gid"]
            if count < threshold and gid not in handled:
                return False
        return True

    def _build_order(self, state: dict[str, Any], *, confirmed: bool) -> dict[str, Any] | None:
        if not state["dispositions"]:
            return state["orders"].get(state.get("publishable_order_id") or "")
        if not self._plan_complete(state):
            return state["orders"].get(state.get("publishable_order_id") or "")
        # 以处置快照为准冻结范围，保证之后补人 / 重检不改写本版放行单。
        retained_ids: list[str] = []
        removed_ids: list[str] = []
        lines: list[dict[str, Any]] = []
        for disp in state["dispositions"]:
            if disp["type"] == "isolate":
                gid = disp["gids"][0]
                group = self._raw_group(state, gid)
                members = group["members"] if group else []
                removed_ids.extend(m["样本编号"] for m in members[:disp["count_snapshot"]])
                lines.append({
                    "kind": "isolate",
                    "gid": gid,
                    "code": self._group_code(state, gid),
                    "count": disp["count_snapshot"],
                    "retained": 0,
                    "removed": disp["count_snapshot"],
                    "reason": disp["reason"],
                    "text": self._line_text({
                        "kind": "isolate", "code": self._group_code(state, gid),
                        "count": disp["count_snapshot"]}),
                })
            elif disp["type"] == "merge":
                mgid = disp["merged_id"]
                mg = next((m for m in state["merged_groups"] if m["mgid"] == mgid), None)
                rows = mg["members"] if mg else []
                retained_ids.extend(m["样本编号"] for m in rows)
                lines.append({
                    "kind": "merge",
                    "gids": disp["gids"],
                    "codes": [self._group_code(state, g) for g in disp["gids"]],
                    "counts": [disp["counts_snapshot"][g] for g in disp["gids"]],
                    "merged_id": mgid,
                    "merged_code": mg["code"] if mg else mgid,
                    "total": disp["total_snapshot"],
                    "retained": disp["total_snapshot"],
                    "removed": 0,
                    "reason": disp["reason"],
                    "text": self._line_text({
                        "kind": "merge",
                        "codes": [self._group_code(state, g) for g in disp["gids"]],
                        "counts": [disp["counts_snapshot"][g] for g in disp["gids"]],
                        "merged_code": mg["code"] if mg else mgid,
                        "total": disp["total_snapshot"]}),
                })
        # 达标且未处置的独立组：自然进入保留段。
        threshold = int(state["threshold"])
        for group in state["groups"]:
            gid = group["gid"]
            if group.get("merged_into") or self._disposition_of(state, gid):
                continue
            if self._group_count(group) >= threshold:
                retained_ids.extend(m["样本编号"] for m in group["members"])
                lines.append({
                    "kind": "retain", "gid": gid,
                    "code": group.get("code", gid),
                    "count": self._group_count(group),
                    "retained": self._group_count(group), "removed": 0,
                    "text": self._line_text({
                        "kind": "retain", "code": group.get("code", gid),
                        "count": self._group_count(group)}),
                })
        # 互斥校验：同一样本不能同时在两段。
        overlap = set(retained_ids) & set(removed_ids)
        if overlap:
            raise BoardError(f"样本 {sorted(overlap)} 被同时计入保留段与移除段",
                             code="DOUBLE_COUNT")
        id_to_member: dict[str, dict[str, Any]] = {}
        for group in state["groups"]:
            for m in group["members"]:
                id_to_member[m["样本编号"]] = m
        frozen_rows = [copy.deepcopy(id_to_member[mid]) for mid in retained_ids if mid in id_to_member]
        removed_rows = [copy.deepcopy(id_to_member[mid]) for mid in removed_ids if mid in id_to_member]
        state["order_seq"] += 1
        order_id = f"FXD-{state['check_id']}-{state['order_seq']:02d}"
        order = {
            "id": order_id,
            "title": "稀有组放行单",
            "check_id": state["check_id"],
            "check_no": state["check_no"],
            "classify_tag_id": self.classify_tag_for(state["check_id"]),
            "version_no": state["order_seq"],
            "base_check_version": state["version"],
            "threshold": threshold,
            "status": "可发布" if confirmed or not state["conflicts"] else "旧版仍可发布",
            "publishable": True,
            "superseded": False,
            "conflicted_with_new_check": bool(state["conflicts"]),
            "created_at": _now(),
            "confirmed": confirmed,
            "lines": lines,
            "retained_count": len(frozen_rows),
            "removed_count": len(removed_rows),
            "retained_member_ids": retained_ids,
            "removed_member_ids": removed_ids,
            "rows": frozen_rows,
            "removed_rows": removed_rows,
        }
        state["orders"][order_id] = order
        state["publishable_order_id"] = order_id
        state["order_versions"].append({
            "id": order_id,
            "version_no": order["version_no"],
            "base_check_version": order["base_check_version"],
            "status": order["status"],
            "publishable": True,
            "conflicted": bool(state["conflicts"]),
            "created_at": order["created_at"],
            "retained_count": order["retained_count"],
            "removed_count": order["removed_count"],
        })
        return order

    def _refresh_order(self, state: dict[str, Any]) -> None:
        """处置变化后，若计划完整则滚动生成新一版可发布放行单。"""
        try:
            self._build_order(state, confirmed=False)
        except BoardError:
            # 计划不完整时保留上一版可用放行单。
            pass

    def _publishable_order(self, state: dict[str, Any]) -> dict[str, Any] | None:
        oid = state.get("publishable_order_id")
        order = state["orders"].get(oid) if oid else None
        return copy.deepcopy(order) if order else None

    def confirm(
        self,
        check_id: int,
        *,
        base_version: int | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """确认处置。显式携带 base_version 时做乐观版本冲突校验。"""
        with self._lock:
            state = self.ensure_state(check_id)
            current = int(state["version"])
            if base_version is not None and int(base_version) < current:
                raise VersionConflict(
                    f"版本冲突：该处置基于检查版本 v{base_version}，"
                    f"服务端已重新检查到 v{current}，旧处置不能覆盖新检查结果；"
                    f"过去的确认与回执仍按当时人数保留",
                    base_version=int(base_version), current_version=current,
                    conflicts=state["conflicts"],
                )
            if not state["dispositions"]:
                raise BoardError("还没有可确认的分组处置，请先隔离或归并稀有分组",
                                 code="NO_DISPOSITION")
            if not self._plan_complete(state):
                raise BoardError(
                    "仍有低于阈值的分组未处置：只能隔离，或与确实相容的组归并到达标",
                    code="PLAN_INCOMPLETE")
            order = self._build_order(state, confirmed=True)
            assert order is not None
            confirm_reason = (reason or "").strip() or "审核员复核确认：隔离与归并范围核对无误，同意生成放行单"
            self._append_receipt(
                state, action="处置确认",
                lines=[{"kind": "order", "text": f"确认 {order['id']}，获准范围 {order['retained_count']} 行，"
                                                 f"移除段 {order['removed_count']} 人"}],
                reason=confirm_reason, base_version=current)
            snap = self.snapshot(check_id)
            snap["order_id"] = order["id"]
            return snap

    def submit_stale(self, check_id: int, base_version: int | None = None) -> dict[str, Any]:
        """“交错提交旧处置”：用旧版本号提交，服务端必须判冲突且不改写历史。"""
        with self._lock:
            state = self.ensure_state(check_id)
            old = int(base_version or 1)
            current = int(state["version"])
            if old < current:
                raise VersionConflict(
                    f"版本冲突：旧处置停留在检查版本 v{old}，新检查已到 v{current}；"
                    f"该提交未生效，历史回执仍按旧人数列明处置",
                    base_version=old, current_version=current,
                    conflicts=state["conflicts"],
                )
            return self.confirm(check_id, base_version=old)

    # ------------------------------------------------------------- classify view

    def classify_detail(self, tag_id: int, order_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            tag = store.find("classify_tag", tag_id)
            # 汇总所有批次的放行单，供分级分类详情选择版本。
            all_orders: list[dict[str, Any]] = []
            all_receipts: list[dict[str, Any]] = []
            conflicts: list[dict[str, Any]] = []
            for cid, state in self._states.items():
                for order in state["orders"].values():
                    item = copy.deepcopy(order)
                    item["check_id"] = cid
                    all_orders.append(item)
                for receipt in state["receipts"]:
                    r = copy.deepcopy(receipt)
                    r["check_id"] = cid
                    all_receipts.append(r)
                for c in state["conflicts"]:
                    c = dict(c)
                    c["check_id"] = cid
                    conflicts.append(c)
            selected: dict[str, Any] | None = None
            if order_id:
                for order in all_orders:
                    if order["id"] == order_id:
                        selected = order
                        break
            if selected is None and all_orders:
                # 默认取最近生成的可发布放行单。
                selected = all_orders[-1]
            # 版本视图：已确认 / 最近可发布版本仍可发布；冲突的新检查草稿不可发布。
            conflict_check_ids: set[int] = set()
            for cid2, state2 in self._states.items():
                if state2.get("conflicts"):
                    conflict_check_ids.add(cid2)
            versions: list[dict[str, Any]] = []
            for order in all_orders:
                still_publishable = order["check_id"] in conflict_check_ids
                versions.append({
                    "id": order["id"],
                    "label": f"{order['id']}（检查 v{order['base_check_version']}）",
                    "publishable": True,
                    "state_text": "仍可发布" if still_publishable or order.get("conflicted_with_new_check") else "可发布",
                    "retained_count": order["retained_count"],
                    "removed_count": order["removed_count"],
                    "created_at": order["created_at"],
                    "conflicted": order.get("conflicted_with_new_check", False),
                })
            for c in conflicts:
                versions.append({
                    "id": f"conflict-{c.get('gid')}-{c.get('current_version')}",
                    "label": f"新检查 v{c.get('current_version')} 与旧处置冲突",
                    "publishable": False,
                    "state_text": "冲突待复核，不可发布",
                    "message": c.get("message"),
                    "conflicted": True,
                })
            return {
                "ok": True,
                "tag": tag or {"id": tag_id, "标签编号": f"CLAS-{tag_id:04d}"},
                "orders": list(reversed(all_orders)),
                "versions": versions,
                "receipts": list(reversed(all_receipts)),
                "conflicts": conflicts,
                "publishable_order": selected,
            }

    def scope_csv(self, tag_id: int, order_id: str | None = None) -> tuple[str, dict[str, Any]]:
        detail = self.classify_detail(tag_id, order_id)
        order = detail["publishable_order"]
        if order is None:
            raise BoardError("当前还没有可下载的获准范围，请先在 K 匿名检查页完成分组处置并生成放行单",
                             code="NO_SCOPE")
        return self.render_scope_csv(order), order

    @staticmethod
    def render_scope_csv(order: dict[str, Any]) -> str:
        import csv
        import io

        output = io.StringIO()
        output.write("\ufeff")  # UTF-8 BOM，便于 Excel 正确识别中文
        headers = ["样本编号", *QI_FIELDS, "随访项目"]
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore",
                                lineterminator="\n")
        writer.writeheader()
        for row in order.get("rows", []):
            writer.writerow({h: row.get(h, "") for h in headers})
        return output.getvalue()


board = GroupReleaseBoard()
