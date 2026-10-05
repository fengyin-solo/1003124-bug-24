"""隐患整改跟踪业务规则：待办清单直接读应急演练的复盘结论，两边始终是同一份数据。

不单独建表复制复盘结论；待办项由应急演练记录实时派生，整改状态写回演练记录本身，
应急演练页和隐患整改跟踪页看到的永远是同一条数据。
"""
from __future__ import annotations

from typing import Any

from app.store import store

SOURCE_MODULE = "emergencydrill"
# 只有复盘结论（演练评估）非空且已复盘/已归档的演练才进入隐患整改待办
TODO_STATUSES = ["已复盘", "已归档"]
RECTIFY_ORDER = ["待整改", "整改中", "已闭环"]
ACTION_RULES = {"开始整改": "整改中", "整改闭环": "已闭环"}


def _to_todo(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "来源模块": "应急演练",
        "演练编号": row.get("演练编号"),
        "演练主题": row.get("演练主题"),
        "演练区域": row.get("演练区域"),
        "演练日期": row.get("演练日期"),
        "演练状态": row.get("status"),
        "复盘结论": row.get("演练评估"),
        "改进措施": row.get("改进措施"),
        "整改状态": row.get("整改状态") or "待整改",
    }


class HazardrectifyService:
    def _source_rows(self) -> list[dict[str, Any]]:
        rows = []
        for row in store.rows(SOURCE_MODULE):
            if row.get("status") not in TODO_STATUSES:
                continue
            if not str(row.get("演练评估") or "").strip():
                continue
            rows.append(row)
        # 存量演练按演练日期回填待办清单，日期越早越靠前
        rows.sort(key=lambda row: str(row.get("演练日期") or ""))
        return rows

    def list_todos(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        todos = [_to_todo(row) for row in self._source_rows()]
        if keyword:
            todos = [todo for todo in todos if keyword in str(todo.get("演练编号", ""))]
        if status:
            todos = [todo for todo in todos if todo.get("整改状态") == status]
        total = len(todos)
        start = max(page - 1, 0) * size
        return todos[start:start + size], total

    def run_action(self, todo_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于隐患整改可执行范围"
        row = store.find(SOURCE_MODULE, todo_id)
        if row is None or row.get("status") not in TODO_STATUSES or not str(row.get("演练评估") or "").strip():
            return None, f"整改待办 {todo_id} 不存在或复盘结论尚未形成"
        current = row.get("整改状态") or "待整改"
        target = ACTION_RULES[action]
        if current not in RECTIFY_ORDER or RECTIFY_ORDER.index(target) != RECTIFY_ORDER.index(current) + 1:
            return None, f"整改待办当前状态为「{current}」，不能执行「{action}」"
        row["整改状态"] = target
        return _to_todo(row), f"整改待办已{action}"
