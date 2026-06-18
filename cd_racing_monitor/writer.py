from __future__ import annotations

from .feishu import FeishuClient
from .models import Decision


WRITEBACK_FIELDS = {
    "node": "判断节点",
    "reason": "原因归类",
    "action": "建议动作",
    "confidence": "置信度",
    "matched_rules": "命中规则",
    "log": "判断日志",
    "decided_at": "判断时间",
}


class DecisionWriter:
    def __init__(self, client: FeishuClient, daily_table_id: str) -> None:
        self.client = client
        self.daily_table_id = daily_table_id

    def write(self, record_id: str, decision: Decision) -> None:
        self.client.update_record(self.daily_table_id, record_id, decision_fields(decision))

    def write_many(self, items: list[tuple[str, Decision]]) -> int:
        total = 0
        for chunk in chunks(items, 100):
            records = [
                {
                    "record_id": record_id,
                    "fields": decision_fields(decision),
                }
                for record_id, decision in chunk
            ]
            total += self.client.update_records_batch(self.daily_table_id, records)
        return total


def decision_fields(decision: Decision) -> dict:
    return {
        WRITEBACK_FIELDS["node"]: decision.node,
        WRITEBACK_FIELDS["reason"]: decision.reason,
        WRITEBACK_FIELDS["action"]: decision.action,
        WRITEBACK_FIELDS["confidence"]: decision.confidence,
        WRITEBACK_FIELDS["matched_rules"]: ",".join(decision.matched_rules),
        WRITEBACK_FIELDS["log"]: decision.log,
        WRITEBACK_FIELDS["decided_at"]: int(decision.decided_at.timestamp() * 1000),
    }


def chunks(items: list[tuple[str, Decision]], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]
