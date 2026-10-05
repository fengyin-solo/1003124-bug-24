"""应急演练业务规则：状态流转、字段校验、落库与隐患待办联动都收在这里。

几条关键口径：

- 演练评估为空不是错误，统一记成「暂无评估」，改进措施可以先存草稿；
- 「内容缺失/状态不允许」和「落库失败」分开：前者返回可读原因、不可重试，
  后者抛 PersistenceError，数据原样保留、允许重试；
- 复盘总结必须给出复盘结论；复盘后评估与结论冻结，改进措施仍可补充，
  且改进措施只保留最新一版；
- 未复盘的演练不许归档；归档只锁结论，不影响改进措施继续补；
- 复盘结论是隐患整改跟踪待办的唯一数据源，待办侧实时读取，不复制。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.persistence import PersistenceError, commit_write
from app.store import store

MODULE = "emergencydrill"
TODO_MODULE = "hazardrectify"
REQUIRED_FIELDS = ["演练编号", "演练主题", "演练区域"]
NO_ASSESSMENT = "暂无评估"

STATUS_ORDER = ["待组织", "已组织", "已完成", "已复盘", "已归档"]
# 状态只许按顺序往下走，不允许跳步（例如待组织直接复盘）。
ACTION_RULES = {"组织演练": "已组织", "完成演练": "已完成", "复盘总结": "已复盘", "归档": "已归档"}
# 复盘后只读的字段：评估是当时的评估，结论是当时的结论，事后不能改。
FROZEN_AFTER_REVIEW = ("演练评估", "复盘结论")


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
        entry["参演人数"] = values.get("参演人数") or ""
        entry["演练日期"] = values.get("演练日期") or ""
        # 新登记的演练评估一律先落成明确的「暂无评估」，不留空白。
        entry["演练评估"] = str(values.get("演练评估") or "").strip() or NO_ASSESSMENT
        entry["改进措施"] = ""
        entry["复盘结论"] = ""
        entry["改进措施版本"] = 0
        entry["改进措施更新时间"] = ""
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        try:
            commit_write()
        except PersistenceError:
            # 登记还没写进列表前就失败，没有脏数据，直接把原因交回上层。
            raise
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str, values: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"演练记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于应急演练可执行范围"
        target = ACTION_RULES[action]
        current = entry.get("status")
        expected_current = STATUS_ORDER[STATUS_ORDER.index(target) - 1]
        if current == target:
            return None, f"演练已处于「{target}」，无需重复{action}"
        if current != expected_current:
            if target in STATUS_ORDER[STATUS_ORDER.index(current) + 1:]:
                return None, f"演练当前为「{current}」，需先完成「{expected_current}」前的流程，不能直接{action}"
            return None, f"演练当前为「{current}」，不能回退到「{target}」"

        # 复盘时把评估、改进措施、结论一起收口。
        if action == "复盘总结":
            ok, message, updates = self._collect_review(entry, values or {})
            if not ok:
                return None, message
            try:
                commit_write()
            except PersistenceError:
                raise
            entry.update(updates)
            entry["status"] = "已复盘"
            entry["pending"] = False
            self._sync_todo(entry)
            return entry, "演练已复盘，复盘结论已同步到隐患整改跟踪待办清单"

        # 能走到这里说明 current 一定是「已复盘」，归档门槛已由状态顺序保证；
        # 额外兜底一次结论缺失（历史脏数据），避免空结论被归档。
        if action == "归档":
            if not str(entry.get("复盘结论") or "").strip():
                return None, "缺少复盘结论，不能归档；请先补全复盘总结"
            try:
                commit_write()
            except PersistenceError:
                raise
            entry["status"] = "已归档"
            entry["pending"] = False
            return entry, "演练已归档；复盘结论不可修改，改进措施仍可继续补充"

        try:
            commit_write()
        except PersistenceError:
            raise
        entry["status"] = target
        entry["pending"] = target not in ("已复盘", "已归档")
        return entry, f"演练记录已{action}"

    def save_draft(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """保存评估与改进措施（不推进状态）。

        返回 (entry, message, assessment_defaulted)；entry 为 None 表示业务校验不过，
        此时 retryable=False、已填内容由前端保留。落库失败时抛 PersistenceError。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"演练记录 {entry_id} 不存在或已归档", False

        updates: dict[str, Any] = {}
        if "演练评估" in values:
            if entry.get("status") in ("已复盘", "已归档"):
                return None, "演练已复盘，评估结论已锁定，不能再修改", False
            assessment = str(values.get("演练评估") or "").strip()
            if not assessment:
                assessment = NO_ASSESSMENT
                updates["演练评估"] = assessment
            else:
                updates["演练评估"] = assessment

        if "改进措施" in values:
            measures = str(values.get("改进措施") or "").strip()
            # 改进措施只保留最新一版：直接覆盖，并累加版本号。
            updates["改进措施"] = measures
            updates["改进措施版本"] = int(entry.get("改进措施版本") or 0) + 1
            updates["改进措施更新时间"] = date.today().isoformat()

        try:
            commit_write()
        except PersistenceError:
            raise
        entry.update(updates)
        # 只有已经复盘（或归档）的演练才有整改待办；复盘前补措施不生成待办。
        if "改进措施" in updates and entry.get("status") in ("已复盘", "已归档"):
            self._sync_todo(entry)
        defaulted = updates.get("演练评估") == NO_ASSESSMENT
        message = "已保存草稿；评估结论为空时已按「暂无评估」记录" if defaulted else "内容已保存"
        return entry, message, defaulted

    def _collect_review(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[bool, str, dict[str, Any]]:
        """汇总复盘提交的评估、改进措施、结论；结论缺失时明确拒绝。"""
        updates: dict[str, Any] = {}
        assessment = str(values.get("演练评估") or entry.get("演练评估") or "").strip()
        if not assessment:
            assessment = NO_ASSESSMENT
        updates["演练评估"] = assessment

        measures = str(values.get("改进措施") or "").strip()
        if measures:
            updates["改进措施"] = measures
            updates["改进措施版本"] = int(entry.get("改进措施版本") or 0) + 1
            updates["改进措施更新时间"] = date.today().isoformat()

        conclusion = str(values.get("复盘结论") or "").strip()
        if not conclusion:
            # 这是「内容缺失」，不是落库失败：提示补齐，已填的评估/措施由前端保留。
            return False, "缺少复盘结论，不能完成复盘；请填写复盘结论后再提交（已填内容不会清空）", updates
        updates["复盘结论"] = conclusion
        return True, "", updates

    def _sync_todo(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """复盘后把待办与演练挂接。整改事项不复制文本，只存演练记录id，
        待办侧读取时实时取复盘结论，保证两边永远是同一份。
        没有复盘结论的演练不产生待办。"""
        if not str(entry.get("复盘结论") or "").strip():
            return None
        todos = store.rows(TODO_MODULE)
        entry_id = int(entry.get("id", 0))
        for todo in todos:
            if int(todo.get("演练记录id", -1)) == entry_id:
                todo["status"] = todo.get("status") or "待整改"
                todo["pending"] = todo.get("status") != "已完成"
                return todo

        todo = {
            "id": max((int(row.get("id", 0)) for row in todos), default=0) + 1,
            "演练记录id": entry_id,
            "跟踪编号": f"HAZ-{entry_id:04d}",
            "整改事项": None,  # 读取时实时引用演练的复盘结论
            "来源": "复盘同步",
            "责任人": "",
            "期限": "",
            "完成情况": "待整改",
            "status": "待整改",
            "pending": True,
            "abnormal": False,
        }
        todos.append(todo)
        return todo
