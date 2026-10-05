"""隐患整改跟踪接口：待办清单由应急演练的复盘结论实时派生，两边读的是同一份数据。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.hazardrectify import HazardrectifyService

router = APIRouter(prefix="/api/hazardrectify", tags=["隐患整改跟踪"])

service = HazardrectifyService()

STATUSES = ["待整改", "整改中", "已闭环"]


@router.get("/todos", response_model=PageResult[dict])
def list_todos(
    keyword: str | None = Query(default=None, description="按演练编号检索"),
    status: str | None = Query(default=None, description="待整改、整改中、已闭环"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """隐患整改待办清单：来源是应急演练的复盘结论，存量演练按演练日期回填。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_todos(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/todos/{todo_id}/actions", response_model=ActionResult)
def run_action(todo_id: int, payload: EntryPayload) -> ActionResult:
    """对待办执行开始整改、整改闭环；状态写回演练记录本身，保证两边一致。"""
    action = str(payload.values.get("action") or "").strip()
    todo, message = service.run_action(todo_id, action)
    if todo is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=todo)
