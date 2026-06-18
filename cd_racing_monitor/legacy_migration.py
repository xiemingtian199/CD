from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any

from .config import FeishuConfig
from .feishu import FeishuClient
from .normalizer import as_number, as_text, parse_date
from .schema import FieldSpec, NUMBER, TEXT, ensure_fields


LEGACY_TABLE_NAMES = {
    "product_master": "Sheet1",
    "links": "链接表单",
    "tmall_summary": "数据表——天猫",
    "red_summary": "数据表——小红书",
    "douyin_summary": "数据表——抖音",
    "kuaishou_summary": "数据表——快手",
    "sales_summary": "销售汇总表",
}


@dataclass
class MigrationPreview:
    source_token: str
    source_tables: dict[str, str]
    product_count: int
    daily_count: int
    skipped_daily_count: int
    missing_required: dict[str, int]
    recommended_product_extra_fields: list[str]
    recommended_daily_extra_fields: list[str]
    product_samples: list[dict[str, Any]]
    daily_samples: list[dict[str, Any]]


class LegacyMigrator:
    def __init__(self, source_config: FeishuConfig, target_config: FeishuConfig | None = None) -> None:
        self.source = FeishuClient(source_config)
        self.target = FeishuClient(target_config) if target_config else None

    def preview(self, output_path: str | Path) -> MigrationPreview:
        table_ids = self._table_ids()
        products = self._build_products(table_ids)
        daily_records, skipped_daily, missing = self._build_daily_records(table_ids)
        preview = MigrationPreview(
            source_token=self.source.config.app_token,
            source_tables=table_ids,
            product_count=len(products),
            daily_count=len(daily_records),
            skipped_daily_count=skipped_daily,
            missing_required=dict(sorted(missing.items())),
            recommended_product_extra_fields=[
                "历史产品等级",
                "品牌",
                "标签",
                "库存",
                "销售毛利",
                "公司控价",
                "平台商品ID",
                "起售价",
                "链接状态",
                "运营姓名",
            ],
            recommended_daily_extra_fields=[
                "平台商品ID",
                "推广状态",
                "推广费",
                "推广ROI",
            ],
            product_samples=products[:10],
            daily_samples=daily_records[:10],
        )
        Path(output_path).write_text(json.dumps(asdict(preview), ensure_ascii=False, indent=2), encoding="utf-8")
        return preview

    def migrate(self, logger) -> dict[str, int]:
        if not self.target:
            raise RuntimeError("target_config is required for migration")
        table_ids = self._table_ids()
        products = self._build_products(table_ids)
        daily_records, skipped_daily, _ = self._build_daily_records(table_ids)

        self._ensure_target_extra_fields(logger)
        existing_products = self._existing_product_ids()
        existing_daily_keys = self._existing_daily_keys()

        created_products = 0
        skipped_products = 0
        product_batch: list[dict[str, Any]] = []
        for product in products:
            product_id = as_text(product.get("产品ID"))
            if not product_id or product_id in existing_products:
                skipped_products += 1
                continue
            product_batch.append(sanitize_fields(product, product_table=True))
            existing_products.add(product_id)
            created_products += 1
            if len(product_batch) >= 100:
                self._flush_batch(self.target.config.product_table_id, product_batch, logger)
                product_batch = []
                logger.info("已迁移产品 %s 条。", created_products)
        self._flush_batch(self.target.config.product_table_id, product_batch, logger)

        created_daily = 0
        duplicate_daily = 0
        daily_batch: list[dict[str, Any]] = []
        for record in daily_records:
            key = daily_key(record)
            if key in existing_daily_keys:
                duplicate_daily += 1
                continue
            daily_batch.append(sanitize_fields(record, daily_table=True))
            existing_daily_keys.add(key)
            created_daily += 1
            if len(daily_batch) >= 100:
                self._flush_batch(self.target.config.daily_table_id, daily_batch, logger)
                daily_batch = []
                logger.info("已迁移每日数据 %s 条。", created_daily)
        self._flush_batch(self.target.config.daily_table_id, daily_batch, logger)

        return {
            "created_products": created_products,
            "skipped_products": skipped_products,
            "created_daily": created_daily,
            "duplicate_daily": duplicate_daily,
            "skipped_daily": skipped_daily,
        }

    def _flush_batch(self, table_id: str, rows: list[dict[str, Any]], logger) -> None:
        if not rows:
            return
        try:
            self.target.create_records_batch(table_id, rows)
        except Exception as exc:
            logger.warning("批量写入失败，改用逐条写入：%s", exc)
            for row in rows:
                self.target.create_record(table_id, row)

    def _ensure_target_extra_fields(self, logger) -> None:
        class TableLike:
            def __init__(self, name: str, fields: tuple[FieldSpec, ...]) -> None:
                self.name = name
                self.fields = fields

        ensure_fields(
            self.target,
            self.target.config.product_table_id,
            TableLike(
                "产品池",
                (
                    FieldSpec("历史产品等级"),
                    FieldSpec("品牌"),
                    FieldSpec("标签"),
                    FieldSpec("库存", NUMBER),
                    FieldSpec("销售毛利", NUMBER),
                    FieldSpec("公司控价"),
                    FieldSpec("平台商品ID"),
                    FieldSpec("起售价"),
                    FieldSpec("链接状态"),
                    FieldSpec("运营姓名"),
                ),
            ),
            logger,
        )
        ensure_fields(
            self.target,
            self.target.config.daily_table_id,
            TableLike(
                "每日数据",
                (
                    FieldSpec("平台商品ID"),
                    FieldSpec("推广状态"),
                    FieldSpec("推广费", NUMBER),
                    FieldSpec("推广ROI", NUMBER),
                    FieldSpec("历史访客汇总", NUMBER),
                    FieldSpec("历史销售额汇总", NUMBER),
                    FieldSpec("历史支付人数汇总", NUMBER),
                ),
            ),
            logger,
        )

    def _existing_product_ids(self) -> set[str]:
        product_ids: set[str] = set()
        for item in self.target.list_records(self.target.config.product_table_id, page_size=100):
            product_id = as_text(item.get("fields", {}).get("产品ID"))
            if product_id:
                product_ids.add(product_id)
        return product_ids

    def _existing_daily_keys(self) -> set[tuple[str, str, str, str]]:
        keys: set[tuple[str, str, str, str]] = set()
        for item in self.target.list_records(self.target.config.daily_table_id, page_size=100):
            fields = item.get("fields", {})
            product_id = as_text(fields.get("产品ID"))
            if product_id:
                keys.add(daily_key(fields))
        return keys

    def _table_ids(self) -> dict[str, str]:
        tables = {item.get("name", ""): item.get("table_id", "") for item in self.source.list_tables()}
        return {key: tables[name] for key, name in LEGACY_TABLE_NAMES.items() if name in tables}

    def _build_products(self, table_ids: dict[str, str]) -> list[dict[str, Any]]:
        products: dict[str, dict[str, Any]] = {}

        if "product_master" in table_ids:
            for item in self.source.list_records(table_ids["product_master"], page_size=100):
                fields = item.get("fields", {})
                product_id = text_field(fields, "款式编码")
                if not product_id:
                    continue
                products[product_id] = {
                    "产品ID": product_id,
                    "产品名": text_field(fields, "商品简称"),
                    "品类": category_from(fields, "一级类目", "二级类目", "三级类目"),
                    "平台": "",
                    "渠道": "",
                    "负责人": text_field(fields, "运营"),
                    "运营姓名": text_field(fields, "运营"),
                    "测试批次": "旧表迁移",
                    "当前阶段": "上架测试",
                    "历史产品等级": text_field(fields, "5月产品等级"),
                    "品牌": text_field(fields, "品牌"),
                    "标签": text_field(fields, "标签"),
                    "库存": as_number_or_none(fields.get("可用数")),
                    "销售毛利": as_number_or_none(fields.get("销售毛利")),
                    "公司控价": text_field(fields, "公司控价"),
                }

        if "links" in table_ids:
            for item in self.source.list_records(table_ids["links"], page_size=100):
                fields = item.get("fields", {})
                product_id = text_field(fields, "款式编码")
                if not product_id:
                    continue
                product = products.setdefault(
                    product_id,
                    {
                        "产品ID": product_id,
                        "产品名": text_field(fields, "产品名称"),
                        "品类": "",
                        "平台": text_field(fields, "平台"),
                        "渠道": "",
                        "负责人": "",
                        "测试批次": "旧表迁移",
                        "当前阶段": "上架测试",
                    },
                )
                product["产品名"] = product.get("产品名") or text_field(fields, "产品名称")
                product["平台商品ID"] = join_unique(product.get("平台商品ID"), text_field(fields, "链接ID"))
                product["平台"] = join_unique(product.get("平台"), text_field(fields, "平台"))
                product["起售价"] = first_non_empty(product.get("起售价"), text_field(fields, "链接起售价"))
                product["链接状态"] = join_unique(product.get("链接状态"), text_field(fields, "状态"))

        return sorted(products.values(), key=lambda item: item.get("产品ID", ""))

    def _build_daily_records(self, table_ids: dict[str, str]) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
        records: list[dict[str, Any]] = []
        missing: dict[str, int] = defaultdict(int)
        skipped = 0
        summary_sources = [
            ("tmall_summary", "天猫"),
            ("red_summary", "小红书"),
            ("douyin_summary", "抖音"),
            ("kuaishou_summary", "快手"),
        ]

        for table_key, platform in summary_sources:
            if table_key not in table_ids:
                continue
            for item in self.source.list_records(table_ids[table_key], page_size=100):
                fields = item.get("fields", {})
                product_id = text_field(fields, "产品编码")
                if not product_id:
                    skipped += 1
                    missing[f"{platform}.产品编码"] += 1
                    continue
                record_date = legacy_text_date(fields.get("时间"))
                record = {
                    "日期": record_date.isoformat() if record_date else "",
                    "产品ID": product_id,
                    "产品名": text_field(fields, "产品名称"),
                    "品类": "",
                    "平台": text_field(fields, "平台") or platform,
                    "渠道": "平台汇总",
                    "曝光": as_number_or_none(fields.get("曝光量")),
                    "点击": as_number_or_none(fields.get("访客数")),
                    "加购": None,
                    "成交": as_number_or_none(fields.get("支付人数")),
                    "成交金额": as_number_or_none(fields.get("支付金额")),
                    "退款": None,
                    "平台商品ID": text_field(fields, "ID"),
                    "推广状态": text_field(fields, "推广状态"),
                    "推广费": as_number_or_none(fields.get("推广费")),
                    "推广ROI": as_number_or_none(fields.get("推广ROI")),
                }
                records.append(record)

        for table_key, platform in (("tmall_raw", "天猫"), ("red_raw", "小红书")):
            pass

        if "sales_summary" in table_ids:
            self._merge_sales_summary(table_ids["sales_summary"], records)

        return records, skipped, missing

    def _merge_sales_summary(self, table_id: str, records: list[dict[str, Any]]) -> None:
        sales_by_product: dict[str, dict[str, Any]] = {}
        for item in self.source.list_records(table_id, page_size=100):
            fields = item.get("fields", {})
            product_id = text_field(fields, "款式编码")
            if not product_id:
                continue
            sales_by_product[product_id] = {
                "历史访客汇总": as_number_or_none(fields.get("访客汇总")),
                "历史销售额汇总": as_number_or_none(fields.get("销售额汇总")),
                "历史支付人数汇总": as_number_or_none(fields.get("支付人数汇总")),
            }
        for record in records:
            record.update(sales_by_product.get(record.get("产品ID", ""), {}))


def text_field(fields: dict[str, Any], name: str) -> str:
    return as_text(fields.get(name))


def category_from(fields: dict[str, Any], *names: str) -> str:
    parts = [text_field(fields, name) for name in names]
    return " / ".join(part for part in parts if part)


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", []):
            return value
    return ""


def join_unique(existing: Any, value: str) -> str:
    existing_text = as_text(existing)
    if not value:
        return existing_text
    parts = [part for part in existing_text.split(",") if part] if existing_text else []
    if value not in parts:
        parts.append(value)
    return ",".join(parts)


def as_number_or_none(value: Any) -> float | None:
    text = as_text(value)
    if not text or text in {"#DIV/0!", "#ERROR!", "NULL", "-"}:
        return None
    try:
        return as_number(value)
    except Exception:
        return None


def legacy_text_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return parse_date(value)
    except Exception:
        pass
    text = as_text(value)
    try:
        return datetime.strptime(f"{datetime.now().year}年{text}", "%Y年%m月%d日").date()
    except Exception:
        return None


def daily_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        as_text(record.get("日期")),
        as_text(record.get("产品ID")),
        as_text(record.get("平台")),
        as_text(record.get("渠道")),
    )


def sanitize_fields(
    fields: dict[str, Any],
    product_table: bool = False,
    daily_table: bool = False,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in fields.items():
        if value in (None, "", []):
            continue
        if key == "日期":
            parsed = legacy_text_date(value)
            if parsed:
                output[key] = int(datetime(parsed.year, parsed.month, parsed.day).timestamp() * 1000)
            continue
        if isinstance(value, float) and value.is_integer():
            output[key] = int(value)
        else:
            output[key] = value

    if product_table:
        # Existing target fields use single-select values for these columns. Keep
        # them simple to avoid invalid joined option values.
        output.pop("平台", None)
        output.pop("渠道", None)
        output.pop("负责人", None)
    if daily_table:
        output.setdefault("渠道", "平台汇总")
    return output
