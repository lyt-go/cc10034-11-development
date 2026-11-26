"""分组处置面板 + 稀有组放行单 + 分级分类获准范围下载。

路径分两组：
- /api/group-release/...  审核页工作台使用；
- /api/classify_tag/{id}/...  分级分类详情页使用（详情聚合 + 获准范围下载）。

业务失败沿用项目约定返回 200 + {ok:False,message,code}，前端直接展示 message；
冲突同时带 conflict / extra 明细，便于页面指出哪一版范围仍可发布。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.group_release import BoardError, VersionConflict, board
from app.store import store

router = APIRouter(prefix="/api", tags=["分组处置与放行单"])


class ThresholdPayload(BaseModel):
    threshold: int = 3


class IsolatePayload(BaseModel):
    gid: str
    reason: str | None = None


class MergePayload(BaseModel):
    gids: list[str] = Field(default_factory=list)
    group_ids: list[str] | None = None
    reason: str | None = None


class MemberPayload(BaseModel):
    gid: str


class ConfirmPayload(BaseModel):
    base_version: int | None = None
    version: int | None = None
    reason: str | None = None


def _fail(exc: BoardError) -> dict[str, Any]:
    body: dict[str, Any] = {"ok": False, "code": exc.code, "message": exc.message}
    if isinstance(exc, VersionConflict):
        body.update(exc.extra)
        body["conflict"] = True
    return body


@router.get("/group-release/batches")
def list_batches() -> dict[str, Any]:
    """可选检查批次：直接来自 k_anonymity 模块列表。"""
    rows = store.rows("k_anonymity")
    items = [
        {
            "check_id": row.get("id"),
            "id": row.get("id"),
            "check_no": row.get("检查编号", ""),
            "dataset": row.get("数据集名称", ""),
            "threshold": row.get("K值要求", "3"),
            "status": row.get("status", ""),
            "label": f"{row.get('检查编号', '')}｜{row.get('数据集名称', '')}",
        }
        for row in rows
    ]
    return {"ok": True, "items": items, "total": len(items)}


@router.get("/group-release/batches/{check_id}")
def get_board(check_id: int) -> dict[str, Any]:
    try:
        return board.snapshot(check_id)
    except BoardError as exc:
        return _fail(exc)


@router.post("/group-release/batches/{check_id}/threshold")
def set_threshold(check_id: int, payload: ThresholdPayload) -> dict[str, Any]:
    try:
        return board.set_threshold(check_id, payload.threshold)
    except BoardError as exc:
        return _fail(exc)


@router.post("/group-release/batches/{check_id}/recheck")
def recheck(check_id: int) -> dict[str, Any]:
    try:
        return board.recheck(check_id)
    except BoardError as exc:
        return _fail(exc)


# 语义化别名：提交新检查。
@router.post("/group-release/batches/{check_id}/new-check")
def new_check(check_id: int) -> dict[str, Any]:
    return recheck(check_id)


@router.post("/group-release/batches/{check_id}/isolate")
def isolate(check_id: int, payload: IsolatePayload) -> dict[str, Any]:
    try:
        return board.isolate(check_id, payload.gid, payload.reason)
    except BoardError as exc:
        return _fail(exc)


@router.post("/group-release/batches/{check_id}/merge")
def merge(check_id: int, payload: MergePayload) -> dict[str, Any]:
    gids = payload.gids or payload.group_ids or []
    try:
        return board.merge(check_id, gids, payload.reason)
    except BoardError as exc:
        return _fail(exc)


@router.post("/group-release/batches/{check_id}/members")
def add_member(check_id: int, payload: MemberPayload) -> dict[str, Any]:
    try:
        return board.add_member(check_id, payload.gid)
    except BoardError as exc:
        return _fail(exc)


# REST 风格别名：/groups/{gid}/members
@router.post("/group-release/batches/{check_id}/groups/{gid}/members")
def add_member_nested(check_id: int, gid: str) -> dict[str, Any]:
    try:
        return board.add_member(check_id, gid)
    except BoardError as exc:
        return _fail(exc)


@router.post("/group-release/batches/{check_id}/confirm")
def confirm(check_id: int, payload: ConfirmPayload) -> dict[str, Any]:
    base = payload.base_version if payload.base_version is not None else payload.version
    try:
        return board.confirm(check_id, base_version=base, reason=payload.reason)
    except BoardError as exc:
        return _fail(exc)


@router.post("/group-release/batches/{check_id}/submit-disposition")
def submit_disposition(check_id: int, payload: ConfirmPayload) -> dict[str, Any]:
    """提交（可能是旧版）处置：携带 base_version 时做冲突校验。"""
    base = payload.base_version if payload.base_version is not None else payload.version
    try:
        if base is not None:
            return board.submit_stale(check_id, base)
        return board.confirm(check_id)
    except BoardError as exc:
        return _fail(exc)


@router.post("/group-release/batches/{check_id}/submit-old")
def submit_old(check_id: int, payload: ConfirmPayload) -> dict[str, Any]:
    try:
        return board.submit_stale(check_id, payload.base_version or 1)
    except BoardError as exc:
        return _fail(exc)


@router.get("/group-release/orders/{order_id}/download")
def download_order(order_id: str) -> Response:
    # 遍历找到对应放行单。
    for state in board._states.values():  # noqa: SLF001 - 下载需要按单号定位
        order = state["orders"].get(order_id)
        if order:
            csv_text = board.render_scope_csv(order)
            return _csv_response(csv_text, order_id)
    return Response(content="放行单不存在或尚未生成".encode("utf-8"), status_code=404,
                    media_type="text/plain; charset=utf-8")


@router.get("/classify_tag/{tag_id}/detail")
def classify_detail(tag_id: int, order: str | None = None) -> dict[str, Any]:
    return board.classify_detail(tag_id, order)


@router.get("/classify_tag/{tag_id}/approved-scope")
def approved_scope(tag_id: int, order: str | None = None) -> dict[str, Any]:
    detail = board.classify_detail(tag_id, order)
    current = detail["publishable_order"]
    return {"ok": current is not None, "scope": current, "versions": detail["versions"]}


@router.get("/classify_tag/{tag_id}/approved-scope/export")
def approved_scope_export(tag_id: int, order: str | None = None) -> Response:
    try:
        csv_text, scope_order = board.scope_csv(tag_id, order)
    except BoardError as exc:
        return Response(
            content=exc.message.encode("utf-8"), status_code=409,
            media_type="text/plain; charset=utf-8")
    return _csv_response(csv_text, scope_order["id"])


# 语义化别名：获准范围下载 / 交付下载。
@router.get("/classify_tag/{tag_id}/delivery/export")
def delivery_export(tag_id: int, order: str | None = None) -> Response:
    return approved_scope_export(tag_id, order)


def _csv_response(csv_text: str, order_id: str) -> Response:
    from urllib.parse import quote

    filename_ascii = f"approved-scope-{order_id}.csv"
    filename_utf8 = quote(f"获准范围-{order_id}.csv")
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{filename_ascii}\"; filename*=UTF-8''{filename_utf8}"
            )
        },
    )
