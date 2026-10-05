"""应急演练接口：维护演练记录，覆盖组织演练、完成演练、复盘总结、归档与改进措施保存。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.persistence import PersistenceError, inject_persistence_failure
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.emergencydrill import EmergencydrillService

router = APIRouter(prefix="/api/emergencydrill", tags=["应急演练"])

service = EmergencydrillService()

LIST_FIELDS = ["演练编号", "演练主题", "演练区域", "参演人数", "演练日期", "演练评估", "改进措施", "演练状态"]
STATUSES = ["待组织", "已组织", "已完成", "已复盘", "已归档"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按演练编号检索"),
    status: str | None = Query(default=None, description="待组织、已组织、已完成、已复盘、已归档"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按演练编号与状态过滤应急演练列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


# 固定路径必须排在 /{entry_id} 前面，否则 /export 会被当成演练 id 解析。
@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出应急演练清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "emergencydrill", "total": total, "items": items}


@router.post("/debug/fail-next-write", response_model=ActionResult)
def fail_next_write(payload: EntryPayload | None = None) -> ActionResult:
    """演练故障注入：让接下来的 N 次写入落库失败，用于验证失败提示与重试。"""
    times = 1
    if payload is not None:
        times = int(payload.values.get("times") or 1)
    inject_persistence_failure(times=times)
    return ActionResult(ok=True, message=f"已设置接下来 {times} 次写入返回落库失败")


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条演练记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"演练记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条演练记录，缺字段时说明原因而不是静默丢弃；落库失败说明可重试。"""
    try:
        entry, missing = service.create_entry(payload.values)
    except PersistenceError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": exc.message,
                "retryable": exc.retryable,
                "reason_code": exc.reason_code,
            },
        ) from exc
    if missing:
        return ActionResult(
            ok=False,
            message=f"缺少必填字段：{'、'.join(missing)}",
            reason_code="missing_required",
        )
    return ActionResult(ok=True, message="演练记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条演练记录执行组织演练、完成演练、复盘总结、归档。

    业务校验不过（缺结论、状态不到位）返回 ok=False，不可重试；
    落库失败转成可读原因 + 重试入口，已填内容保留在前端。
    """
    action = str(payload.values.get("action") or "").strip()
    try:
        entry, message = service.run_action(entry_id, action, payload.values)
    except PersistenceError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": exc.message,
                "retryable": exc.retryable,
                "reason_code": exc.reason_code,
            },
        ) from exc
    if entry is None:
        return ActionResult(ok=False, message=message, reason_code="business_rule_rejected")
    return ActionResult(ok=True, message=message, entry=entry)


@router.put("/{entry_id}/draft", response_model=ActionResult)
def save_draft(entry_id: int, payload: EntryPayload) -> ActionResult:
    """保存演练评估与改进措施，不推进状态，可反复存草稿。

    - 评估为空：服务端归一化成「暂无评估」，仍然保存成功；
    - 已复盘后评估只读、复盘结论不接受此接口修改；
    - 落库失败返回 503 + retryable，前端保留全部已填内容并提供重试。
    """
    try:
        entry, message, defaulted = service.save_draft(entry_id, payload.values)
    except PersistenceError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": exc.message,
                "retryable": exc.retryable,
                "reason_code": exc.reason_code,
            },
        ) from exc
    if entry is None:
        return ActionResult(ok=False, message=message, reason_code="business_rule_rejected")
    return ActionResult(
        ok=True,
        message=message,
        entry=entry,
        reason_code="assessment_defaulted" if defaulted else None,
    )
