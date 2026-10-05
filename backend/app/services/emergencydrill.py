"""应急演练业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "emergencydrill"
REQUIRED_FIELDS = ["演练编号", "演练主题", "演练区域"]
OPTIONAL_FIELDS = ["参演人数", "演练日期"]
STATUS_ORDER = ["待组织", "已组织", "已完成", "已复盘", "已归档"]
ACTION_RULES = {"组织演练": "已组织", "完成演练": "已完成", "复盘总结": "已复盘", "归档": "已归档"}
NEGATIVE_ACTIONS = []

# 改进措施相关口径
NO_EVALUATION_TEXT = "暂无评估"
IMPROVEMENT_EDITABLE_STATUSES = ["已完成", "已复盘", "已归档"]
DRAFT = "草稿"
SUBMITTED = "已提交"


class EmergencydrillService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("演练编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry.update({field: values.get(field) for field in OPTIONAL_FIELDS if values.get(field) is not None})
        entry["演练评估"] = str(values.get("演练评估") or "").strip()
        entry["改进措施"] = str(values.get("改进措施") or "").strip()
        entry["改进措施状态"] = ""
        entry["整改状态"] = ""
        entry["status"] = STATUS_ORDER[0]
        entry["演练状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"演练记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于应急演练可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        if target == "已归档" and entry.get("status") != "已复盘":
            return None, f"演练记录当前状态为「{entry.get('status')}」，尚未复盘总结，不能归档"
        entry["status"] = target
        entry["演练状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if target == "已复盘" and str(entry.get("演练评估") or "").strip() and not entry.get("整改状态"):
            entry["整改状态"] = "待整改"
        return entry, f"演练记录已{action}"

    def save_improvement(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str, bool]:
        """保存改进措施：评估为空时按草稿落库并记为暂无评估；归档后只许补改进措施。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"演练记录 {entry_id} 不存在或已归档", False
        status = str(entry.get("status") or "")
        if status not in IMPROVEMENT_EDITABLE_STATUSES:
            return None, f"演练记录当前状态为「{status}」，演练完成后才能填写改进措施", False
        improvement = str(values.get("改进措施") or "").strip()
        if not improvement:
            return None, "改进措施内容为空，未保存；请填写后重试", False
        evaluation = str(values.get("演练评估") or "").strip()
        archived = status == "已归档"
        if archived and evaluation and evaluation != str(entry.get("演练评估") or "").strip():
            return None, "演练记录已归档，复盘结论（演练评估）不允许改动，只能补充改进措施", False
        # 改进措施只保留最新一版，直接覆盖
        entry["改进措施"] = improvement
        if archived:
            entry["改进措施状态"] = SUBMITTED if str(entry.get("演练评估") or "").strip() else DRAFT
            return entry, "改进措施已补充保存（仅保留最新一版，复盘结论未改动）", True
        if evaluation:
            entry["演练评估"] = evaluation
            entry["改进措施状态"] = SUBMITTED
            if status == "已复盘" and not entry.get("整改状态"):
                entry["整改状态"] = "待整改"
            return entry, "改进措施与演练评估已保存", True
        entry["改进措施状态"] = DRAFT
        return entry, f"演练评估为空，已记为「{NO_EVALUATION_TEXT}」，改进措施先存为草稿", True
