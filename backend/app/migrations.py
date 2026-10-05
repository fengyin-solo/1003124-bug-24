"""存量数据回填：应急演练规则升级后，把老数据补齐到新口径。

回填只做两件事，且可重复执行：

1. 演练评估为空（含空串）的存量演练，按演练日期先后统一写成「暂无评估」，
   这样空评估是一条明确的结论，而不是「漏填还是没有」的糊涂账；
2. 已经复盘、已归档的存量演练，按演练日期先后在隐患整改跟踪里补一条待办，
   整改事项直接引用演练的复盘结论（读取时实时取，天然是同一份）。
"""
from __future__ import annotations

from app.store import store

DRILL_MODULE = "emergencydrill"
TODO_MODULE = "hazardrectify"
NO_ASSESSMENT = "暂无评估"
BACKFILLED_SOURCE = "存量回填"


def _drill_date(row: dict) -> str:
    return str(row.get("演练日期") or "")


def _existing_todo_ids() -> set[int]:
    return {
        int(row["演练记录id"])
        for row in store.rows(TODO_MODULE)
        if row.get("演练记录id") is not None
    }


def backfill_legacy_drills() -> dict[str, int]:
    """启动时执行一次（幂等）。返回各项回填条数，便于在日志/测试里核对。"""
    drills = store.rows(DRILL_MODULE)

    filled_assessment = 0
    for row in drills:
        if not str(row.get("演练评估") or "").strip():
            row["演练评估"] = NO_ASSESSMENT
            filled_assessment += 1

    linked = _existing_todo_ids()
    created_todos = 0
    # 存量演练按演练日期回填：日期早的先在待办清单里落位。
    for row in sorted(drills, key=_drill_date):
        if row.get("status") not in ("已复盘", "已归档"):
            continue
        entry_id = int(row.get("id", 0))
        if entry_id in linked:
            continue
        store.rows(TODO_MODULE).append(_build_todo(row))
        linked.add(entry_id)
        created_todos += 1

    return {"filled_assessment": filled_assessment, "created_todos": created_todos}


def _build_todo(row: dict) -> dict:
    """为一条已复盘演练补待办。整改事项/结论不复制，列表读取时实时引用。"""
    return {
        "id": len(store.rows(TODO_MODULE)) + 1,
        "演练记录id": int(row.get("id", 0)),
        "跟踪编号": f"HAZ-{int(row.get('id', 0)):04d}",
        "整改事项": None,  # 读取时取演练复盘结论，保证两边永远是同一份
        "来源": BACKFILLED_SOURCE,
        "责任人": "",
        "期限": "",
        "完成情况": "待整改",
        "status": "待整改",
        "pending": True,
        "abnormal": False,
    }
