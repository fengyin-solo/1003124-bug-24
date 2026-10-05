"""落库环节的故障模型与模拟。

业务校验不过（内容缺失、状态不允许）和落库失败（写不进去）是两类问题，
页面提示和处理方式完全不同：

- 业务校验不过：Service 直接返回 ok=False / retryable=False，用户改内容；
- 落库失败：抛 PersistenceError，携带人话原因与 retryable=True，
  用户填写的内容不丢，前端给出重试入口，原样再交一次即可。
"""
from __future__ import annotations


class PersistenceError(Exception):
    """内容已通过校验、但没能落库。message 必须是可以直接展示给用户的中文原因。"""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        reason_code: str = "persistence_unavailable",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.reason_code = reason_code


# 故障注入：联调/演练时让接下来的 N 次写入失败，用来验证前端的失败提示与重试。
_injected_failures = 0
_injected_reason = "存储服务暂时不可用，数据未能保存。你填写的内容已保留，请直接点击「重试」。"


def inject_persistence_failure(times: int = 1, reason: str | None = None) -> None:
    """让接下来 times 次 commit_write 抛 PersistenceError（仅用于演练/测试）。"""
    global _injected_failures, _injected_reason
    _injected_failures = max(times, 0)
    if reason:
        _injected_reason = reason


def commit_write() -> None:
    """模拟一次事务提交。内存仓库里写入本身不会失败，这里承接故障注入，
    让「落库失败」这条分支可以被真实地走到。"""
    global _injected_failures
    if _injected_failures > 0:
        _injected_failures -= 1
        raise PersistenceError(_injected_reason)
