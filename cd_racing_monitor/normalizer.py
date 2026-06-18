from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .models import DailyRecord, RuleConfig


FIELD_ALIASES = {
    "date": ["日期", "date"],
    "product_id": ["产品ID", "商品ID", "product_id"],
    "product_name": ["产品名", "商品名", "product_name"],
    "category": ["品类", "category"],
    "platform": ["平台", "platform"],
    "channel": ["渠道", "channel"],
    "impressions": ["曝光", "曝光量", "impressions"],
    "clicks": ["点击", "点击量", "clicks"],
    "add_to_cart": ["加购", "加购数", "add_to_cart"],
    "orders": ["成交", "订单", "成交订单数", "orders"],
    "revenue": ["成交金额", "GMV", "revenue"],
    "refunds": ["退款", "退款订单数", "refunds"],
    "competitor_impressions": ["竞品曝光", "competitor_impressions"],
    "competitor_clicks": ["竞品点击", "competitor_clicks"],
    "competitor_orders": ["竞品成交", "competitor_orders"],
    "competitor_note": ["竞品动销备注", "competitor_note"],
}

RULE_FIELD_ALIASES = {
    "platform": ["平台", "platform"],
    "category": ["品类", "category"],
    "channel": ["渠道", "channel"],
    "min_impressions": ["最小曝光", "min_impressions"],
    "min_clicks": ["最小点击", "min_clicks"],
    "min_add_to_cart": ["最小加购", "min_add_to_cart"],
    "min_orders": ["最小成交", "min_orders"],
    "low_click_rate": ["低点击率", "low_click_rate"],
    "low_conversion_rate": ["低成交转化率", "low_conversion_rate"],
    "low_cart_to_order_rate": ["低加购成交率", "low_cart_to_order_rate"],
    "high_refund_rate": ["高退款率", "high_refund_rate"],
    "competitor_low_conversion_rate": ["竞品低成交率", "competitor_low_conversion_rate"],
    "scale_click_rate": ["放量点击率", "scale_click_rate"],
    "scale_conversion_rate": ["放量成交转化率", "scale_conversion_rate"],
    "scale_refund_rate_max": ["放量退款率上限", "scale_refund_rate_max"],
    "eliminate_consecutive_hits": ["淘汰连续命中轮次", "eliminate_consecutive_hits"],
}


class DataNormalizer:
    def daily_records(self, items: list[dict[str, Any]]) -> list[DailyRecord]:
        records: list[DailyRecord] = []
        for item in items:
            fields = item.get("fields", item)
            record_id = str(item.get("record_id", item.get("id", "")))
            product_id = as_text(pick(fields, FIELD_ALIASES["product_id"]))
            if not product_id:
                raise ValueError(f"Daily record {record_id or '<unknown>'} is missing 产品ID")
            records.append(
                DailyRecord(
                    record_id=record_id,
                    date=parse_date(pick(fields, FIELD_ALIASES["date"])),
                    product_id=product_id,
                    product_name=as_text(pick(fields, FIELD_ALIASES["product_name"])),
                    category=as_text(pick(fields, FIELD_ALIASES["category"])),
                    platform=as_text(pick(fields, FIELD_ALIASES["platform"])),
                    channel=as_text(pick(fields, FIELD_ALIASES["channel"])),
                    impressions=as_number(pick(fields, FIELD_ALIASES["impressions"])),
                    clicks=as_number(pick(fields, FIELD_ALIASES["clicks"])),
                    add_to_cart=as_number(pick(fields, FIELD_ALIASES["add_to_cart"])),
                    orders=as_number(pick(fields, FIELD_ALIASES["orders"])),
                    revenue=as_number(pick(fields, FIELD_ALIASES["revenue"])),
                    refunds=as_number(pick(fields, FIELD_ALIASES["refunds"])),
                    competitor_impressions=as_number(pick(fields, FIELD_ALIASES["competitor_impressions"])),
                    competitor_clicks=as_number(pick(fields, FIELD_ALIASES["competitor_clicks"])),
                    competitor_orders=as_number(pick(fields, FIELD_ALIASES["competitor_orders"])),
                    competitor_note=as_text(pick(fields, FIELD_ALIASES["competitor_note"])),
                    raw=fields,
                )
            )
        return records

    def rule_configs(self, items: list[dict[str, Any]]) -> list[RuleConfig]:
        configs: list[RuleConfig] = []
        for item in items:
            fields = item.get("fields", item)
            if is_blank_fields(fields):
                continue
            base = RuleConfig()
            values = {}
            for key, aliases in RULE_FIELD_ALIASES.items():
                raw_value = pick(fields, aliases)
                if raw_value in (None, ""):
                    continue
                if key in {"platform", "category", "channel"}:
                    values[key] = as_text(raw_value)
                elif key == "eliminate_consecutive_hits":
                    values[key] = int(as_number(raw_value))
                else:
                    values[key] = as_number(raw_value)
            configs.append(replace_rule_config(base, values))
        return configs

    def select_rule(self, record: DailyRecord, configs: list[RuleConfig]) -> RuleConfig:
        candidates = [config for config in configs if rule_matches(config, record)]
        if not candidates:
            return RuleConfig()
        return sorted(candidates, key=lambda item: item.specificity(), reverse=True)[0]


def replace_rule_config(base: RuleConfig, values: dict[str, Any]) -> RuleConfig:
    data = base.__dict__.copy()
    data.update(values)
    return RuleConfig(**data)


def rule_matches(config: RuleConfig, record: DailyRecord) -> bool:
    return (
        match_blank_or_equal(config.platform, record.platform)
        and match_blank_or_equal(config.category, record.category)
        and match_blank_or_equal(config.channel, record.channel)
    )


def match_blank_or_equal(expected: str, actual: str) -> bool:
    return not expected or expected.strip().lower() == actual.strip().lower()


def pick(fields: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in fields:
            return fields[name]
    return None


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ",".join(as_text(item) for item in value)
    if isinstance(value, dict):
        if "text" in value:
            return as_text(value["text"])
        if "name" in value:
            return as_text(value["name"])
        if "value" in value:
            return as_text(value["value"])
        return str(value)
    return str(value).strip()


def as_number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list):
        return as_number(value[0]) if value else 0.0
    if isinstance(value, dict):
        for key in ("value", "text", "name"):
            if key in value:
                return as_number(value[key])
        return 0.0
    text = str(value).strip().replace(",", "")
    if text.endswith("%"):
        return float(text[:-1]) / 100
    return float(text)


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(timestamp).date()
    text = as_text(value)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return datetime.fromisoformat(text).date()


def is_blank_fields(fields: dict[str, Any]) -> bool:
    return all(value in (None, "", []) for value in fields.values())
