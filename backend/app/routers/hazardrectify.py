"""隐患整改跟踪接口：展示由演练复盘结论同步而来的待办，维护整改进度。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.hazardrectify import HazardrectifyService

router = APIRouter(prefix="/api/hazardrectify", tags=["隐患整改跟踪"])

service = HazardrectifyService()

LIST_FIELDS = ["跟踪编号", "演练编号", "演练主题", "演练日期", "整改事项", "责任人", "期限", "完成情况"]
STATUSES = ["待整改", "整改中", "已完成"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按跟踪编号或演练编号检索"),
    status: str | None = Query(default=None, description="待整改、整改中、已完成"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """列出整改待办；整改事项实时读取演练复盘结论，始终与演练侧同一份。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出隐患整改跟踪清单。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "hazardrectify", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"整改跟踪记录 {entry_id} 不存在")
    return entry


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """更新责任人、期限或完成情况；不允许从这里改整改事项（它属于演练复盘结论）。"""
    entry, message = service.update_entry(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message, reason_code="business_rule_rejected")
    return ActionResult(ok=True, message=message, entry=entry)
