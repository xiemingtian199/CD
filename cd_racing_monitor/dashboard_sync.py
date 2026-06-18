from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .config import AppConfig
from .dashboard import build_rankings, normalize_row
from .feishu import FeishuClient
from .schema import DATE, NUMBER, TEXT, FieldSpec, TableSpec, ensure_fields, table_id, table_name


RANKING_TABLE_NAME = "仪表盘-产品排行"
TREND_TABLE_NAME = "仪表盘-产品趋势"


@dataclass
class DashboardSyncResult:
    ranking_table_id: str
    trend_table_id: str
    ranking_created: int
    ranking_updated: int
    trend_created: int
    trend_updated: int
    product_count: int
    trend_row_count: int
    latest_date: str


RANKING_SPEC = TableSpec(
    name=RANKING_TABLE_NAME,
    fields=(
        FieldSpec("产品ID", TEXT),
        FieldSpec("排名", NUMBER),
        FieldSpec("产品名", TEXT),
        FieldSpec("访客数", NUMBER),
        FieldSpec("销售额", NUMBER),
        FieldSpec("成交", NUMBER),
        FieldSpec("已上架平台", TEXT),
        FieldSpec("平台汇总", TEXT),
        FieldSpec("最新日期", DATE),
        FieldSpec("更新时间", DATE),
    ),
)

TREND_SPEC = TableSpec(
    name=TREND_TABLE_NAME,
    fields=(
        FieldSpec("趋势键", TEXT),
        FieldSpec("排名", NUMBER),
        FieldSpec("产品ID", TEXT),
        FieldSpec("产品名", TEXT),
        FieldSpec("日期", DATE),
        FieldSpec("平台", TEXT),
        FieldSpec("访客数", NUMBER),
        FieldSpec("销售额", NUMBER),
        FieldSpec("成交", NUMBER),
        FieldSpec("更新时间", DATE),
    ),
)


class FeishuDashboardDataSyncer:
    def __init__(self, config: AppConfig, logger) -> None:
        self.config = config
        self.logger = logger
        self.client = FeishuClient(config.feishu)

    def sync(self) -> DashboardSyncResult:
        daily_rows = [
            normalize_row(item.get("fields", {}))
            for item in self.client.list_records(self.config.feishu.daily_table_id, page_size=100)
        ]
        daily_rows = [row for row in daily_rows if row["product_id"] and row["date"]]
        rankings = build_rankings(daily_rows)
        trend_rows = build_flat_trend_rows(daily_rows, rankings)

        ranking_table_id = self._ensure_table(RANKING_SPEC)
        trend_table_id = self._ensure_table(TREND_SPEC)

        now_ms = timestamp_ms(datetime.now())
        latest_date = max((row["date"] for row in daily_rows), default="")
        latest_ms = date_text_to_ms(latest_date) if latest_date else None

        ranking_payload = [
            clean_fields(
                {
                    "产品ID": row["productId"],
                    "排名": row["rank"],
                    "产品名": row["productName"],
                    "访客数": row["visitors"],
                    "销售额": row["sales"],
                    "成交": row["orders"],
                    "已上架平台": " / ".join(row["platforms"]),
                    "平台汇总": format_platform_summary(row["platformSummary"]),
                    "最新日期": latest_ms,
                    "更新时间": now_ms,
                }
            )
            for row in rankings
        ]
        trend_payload = [
            clean_fields(
                {
                    "趋势键": row["key"],
                    "排名": row["rank"],
                    "产品ID": row["product_id"],
                    "产品名": row["product_name"],
                    "日期": date_text_to_ms(row["date"]),
                    "平台": row["platform"],
                    "访客数": row["visitors"],
                    "销售额": row["sales"],
                    "成交": row["orders"],
                    "更新时间": now_ms,
                }
            )
            for row in trend_rows
        ]

        ranking_created, ranking_updated = self._upsert_records(ranking_table_id, "产品ID", ranking_payload)
        trend_created, trend_updated = self._upsert_records(trend_table_id, "趋势键", trend_payload)

        return DashboardSyncResult(
            ranking_table_id=ranking_table_id,
            trend_table_id=trend_table_id,
            ranking_created=ranking_created,
            ranking_updated=ranking_updated,
            trend_created=trend_created,
            trend_updated=trend_updated,
            product_count=len(rankings),
            trend_row_count=len(trend_payload),
            latest_date=latest_date,
        )

    def _ensure_table(self, spec: TableSpec) -> str:
        existing_tables = {table_name(item): table_id(item) for item in self.client.list_tables()}
        table_id_value = existing_tables.get(spec.name)
        if table_id_value:
            self.logger.info("已找到仪表数据表：%s (%s)", spec.name, table_id_value)
        else:
            table_id_value = self.client.create_table(spec.name, spec.fields[0].name)
            self.logger.info("已创建仪表数据表：%s (%s)", spec.name, table_id_value)
        ensure_fields(self.client, table_id_value, spec, self.logger)
        return table_id_value

    def _upsert_records(self, table_id_value: str, key_field: str, rows: list[dict[str, Any]]) -> tuple[int, int]:
        existing = self.client.list_records(table_id_value, page_size=100)
        index: dict[str, str] = {}
        for item in existing:
            fields = item.get("fields", {})
            key = str(fields.get(key_field) or "").strip()
            if key:
                index[key] = str(item.get("record_id", ""))

        create_rows: list[dict[str, Any]] = []
        update_rows: list[dict[str, Any]] = []
        for row in rows:
            key = str(row.get(key_field) or "").strip()
            record_id = index.get(key)
            if record_id:
                update_rows.append({"record_id": record_id, "fields": row})
            else:
                create_rows.append(row)

        created = 0
        for chunk in chunks(create_rows, 100):
            created += self.client.create_records_batch(table_id_value, chunk)
        updated = 0
        for chunk in chunks(update_rows, 100):
            updated += self.client.update_records_batch(table_id_value, chunk)
        return created, updated


def build_flat_trend_rows(rows: list[dict[str, Any]], rankings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank_by_product = {row["productId"]: row["rank"] for row in rankings}
    name_by_product = {row["product_id"]: row["product_name"] or row["product_id"] for row in rows}
    grouped: dict[tuple[str, str, str], dict[str, float]] = defaultdict(
        lambda: {"visitors": 0.0, "sales": 0.0, "orders": 0.0}
    )
    for row in rows:
        key = (row["date"], row["product_id"], row["platform"])
        grouped[key]["visitors"] += row["visitors"]
        grouped[key]["sales"] += row["sales"]
        grouped[key]["orders"] += row["orders"]

    output = []
    for (date_text, product_id, platform), values in grouped.items():
        output.append(
            {
                "key": f"{date_text}|{product_id}|{platform}",
                "date": date_text,
                "rank": rank_by_product.get(product_id, 999999),
                "product_id": product_id,
                "product_name": name_by_product.get(product_id, product_id),
                "platform": platform,
                "visitors": round(values["visitors"], 2),
                "sales": round(values["sales"], 2),
                "orders": round(values["orders"], 2),
            }
        )
    return sorted(output, key=lambda item: (item["rank"], item["product_id"], item["date"], item["platform"]))


def format_platform_summary(items: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{item['platform']}：访客 {item['visitors']:.0f} / 销售额 {item['sales']:.2f}"
        for item in items
    )


def date_text_to_ms(value: str) -> int:
    dt = datetime.strptime(value, "%Y-%m-%d")
    return timestamp_ms(dt)


def timestamp_ms(value: datetime) -> int:
    return int(datetime(value.year, value.month, value.day).timestamp() * 1000)


def clean_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value not in (None, "", [])}


def chunks(items: list[dict[str, Any]], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]
