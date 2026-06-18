from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .config import AppConfig
from .feishu import FeishuClient
from .models import Decision
from .normalizer import DataNormalizer, is_blank_fields
from .rules import RuleEngine
from .writer import DecisionWriter


class Logger(Protocol):
    def info(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...


@dataclass
class PipelineResult:
    read_records: int = 0
    written_records: int = 0
    skipped_records: int = 0
    errors: list[str] | None = None


class MonitorPipeline:
    def __init__(self, config: AppConfig, logger: Logger) -> None:
        self.config = config
        self.logger = logger
        self.client = FeishuClient(config.feishu)
        self.normalizer = DataNormalizer()
        self.engine = RuleEngine()
        self.writer = DecisionWriter(self.client, config.feishu.daily_table_id)

    def run_once(self) -> PipelineResult:
        result = PipelineResult(errors=[])
        product_items = self.client.list_records(self.config.feishu.product_table_id)
        daily_items = self.client.list_records(self.config.feishu.daily_table_id)
        rule_items = []
        if self.config.feishu.rule_table_id:
            rule_items = self.client.list_records(self.config.feishu.rule_table_id)
        else:
            self.logger.warning("未配置规则配置表 ID，本次使用程序内置默认阈值。")
        result.read_records = len(daily_items)
        daily_items = merge_product_fields(daily_items, product_items)
        configs = self.normalizer.rule_configs(rule_items)
        self.logger.info(f"读取产品池 {len(product_items)} 条，每日数据 {len(daily_items)} 条，规则配置 {len(configs)} 条。")

        decisions_to_write = []
        for item in daily_items:
            record_id = str(item.get("record_id", ""))
            try:
                if is_blank_fields(item.get("fields", item)):
                    result.skipped_records += 1
                    self.logger.info(f"跳过空白占位记录 {record_id or '<unknown>'}。")
                    continue
                record = self.normalizer.daily_records([item])[0]
                rule_config = self.normalizer.select_rule(record, configs)
                decision = self.engine.evaluate(record, rule_config)
                decisions_to_write.append((record.record_id, decision))
                self.logger.info(f"{record.product_id} / {record.channel}: {decision.reason} -> {decision.action}")
            except Exception as exc:
                result.skipped_records += 1
                message = f"跳过记录 {record_id or '<unknown>'}: {exc}"
                result.errors.append(message)
                self.logger.error(message)
        result.written_records = self.writer.write_many(decisions_to_write)
        return result


def evaluate_items(
    daily_items: list[dict],
    rule_items: list[dict],
    product_items: list[dict] | None = None,
) -> list[tuple[str, Decision]]:
    normalizer = DataNormalizer()
    if product_items:
        daily_items = merge_product_fields(daily_items, product_items)
    configs = normalizer.rule_configs(rule_items)
    engine = RuleEngine()
    output: list[tuple[str, Decision]] = []
    for record in normalizer.daily_records(daily_items):
        output.append((record.record_id, engine.evaluate(record, normalizer.select_rule(record, configs))))
    return output


def merge_product_fields(daily_items: list[dict], product_items: list[dict]) -> list[dict]:
    product_by_id: dict[str, dict] = {}
    normalizer = DataNormalizer()
    for item in product_items:
        try:
            record = normalizer.daily_records([item])[0]
        except Exception:
            continue
        product_by_id[record.product_id] = item.get("fields", item)

    merged: list[dict] = []
    for item in daily_items:
        fields = dict(item.get("fields", item))
        try:
            record = normalizer.daily_records([item])[0]
            product_fields = product_by_id.get(record.product_id, {})
        except Exception:
            product_fields = {}
        for key in ("产品名", "品类", "平台", "渠道", "负责人", "测试批次", "当前阶段"):
            if fields.get(key) in (None, "") and key in product_fields:
                fields[key] = product_fields[key]
        merged.append({**item, "fields": fields})
    return merged
