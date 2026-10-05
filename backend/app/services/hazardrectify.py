"""隐患整改跟踪业务规则。

待办清单里的「整改事项」不是复制的文本，而是每次读取时实时引用应急演练的
「复盘结论」。演练侧改了什么（事实上复盘结论不可改，只会在复盘时写入一次），
这边读到的永远是同一份，杜绝两边对不上。

本地只维护整改进度类字段（责任人、期限、完成情况）。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "hazardrectify"
DRILL_MODULE = "emergencydrill"
EDITABLE_FIELDS = ("责任人", "期限", "完成情况")
VALID_RESULTS = ("待整改", "整改中", "已完成")


class HazardrectifyService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._materialize(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("跟踪编号", ""))
                or keyword in str(row.get("演练编号", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return self._materialize(row) if row else None

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """只更新整改进度字段；整改事项（复盘结论）不接受从这里修改。"""
        row = store.find(MODULE, entry_id)
        if row is None:
            return None, f"整改跟踪记录 {entry_id} 不存在"
        for field in EDITABLE_FIELDS:
            if field in values:
                value = str(values.get(field) or "").strip()
                if field == "完成情况" and value and value not in VALID_RESULTS:
                    return None, f"完成情况只支持：{'、'.join(VALID_RESULTS)}"
                row[field] = value
        result = str(row.get("完成情况") or "待整改")
        row["status"] = result
        row["pending"] = result != "已完成"
        return self._materialize(row), "整改跟踪信息已更新"

    def _materialize(self, row: dict[str, Any]) -> dict[str, Any]:
        """把一条待办记录展开成前端要的样子：结论实时取演练侧数据。"""
        view = dict(row)
        drill = self._linked_drill(row)
        view["演练编号"] = drill.get("演练编号", "") if drill else ""
        view["演练主题"] = drill.get("演练主题", "") if drill else ""
        view["演练日期"] = drill.get("演练日期", "") if drill else ""
        # 关键：整改事项就是演练的复盘结论本身，引用而不是复制。
        view["整改事项"] = drill.get("复盘结论", "") if drill else ""
        view["复盘结论"] = view["整改事项"]
        result = str(view.get("完成情况") or "待整改")
        view["status"] = result
        view["pending"] = result != "已完成"
        return view

    def _linked_drill(self, row: dict[str, Any]) -> dict[str, Any] | None:
        drill_id = row.get("演练记录id")
        if drill_id is None:
            return None
        return store.find(DRILL_MODULE, int(drill_id))
