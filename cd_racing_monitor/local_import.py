from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import re

import pandas as pd

from .config import AppConfig
from .feishu import FeishuClient
from .normalizer import as_text


@dataclass
class ImportRow:
    fields: dict[str, Any]
    source_file: str
    matched: bool
    skip_reason: str = ""


class LocalLinkDataImporter:
    def __init__(self, config: AppConfig, folder: str | Path, logger) -> None:
        self.config = config
        self.folder = Path(folder)
        self.logger = logger
        self.client = FeishuClient(config.feishu)

    def preview(self) -> dict[str, Any]:
        rows = self._build_rows()
        return self._summary(rows)

    def import_to_feishu(self) -> dict[str, Any]:
        rows = self._build_rows()
        existing_keys = self._existing_daily_keys()
        write_rows = []
        skipped_duplicate = 0
        for row in rows:
            if not row.matched:
                continue
            key = daily_key(row.fields)
            if key in existing_keys:
                skipped_duplicate += 1
                continue
            write_rows.append(row.fields)
            existing_keys.add(key)

        created = 0
        for chunk in chunks(write_rows, 100):
            created += self.client.create_records_batch(self.config.feishu.daily_table_id, chunk)

        summary = self._summary(rows)
        summary["created"] = created
        summary["skipped_duplicate"] = skipped_duplicate
        return summary

    def _build_rows(self) -> list[ImportRow]:
        if not self.folder.exists():
            raise RuntimeError(f"Folder does not exist: {self.folder}")
        link_index = self._link_index()
        rows: list[ImportRow] = []
        for path in sorted(self.folder.glob("*.xlsx")):
            if path.name.startswith("~$"):
                continue
            if "小红书" in path.name:
                rows.extend(self._read_red_file(path, link_index))
            else:
                rows.extend(self._read_tmall_file(path, link_index))
        return rows

    def _link_index(self) -> dict[tuple[str, str], dict[str, Any]]:
        links = self.client.list_records(self.config.feishu.link_table_id, page_size=100)
        index: dict[tuple[str, str], dict[str, Any]] = {}
        for row in links:
            fields = row.get("fields", {})
            platform = as_text(fields.get("平台"))
            link_id = as_text(fields.get("链接ID") or fields.get("平台商品ID"))
            if platform and link_id:
                index[(platform, link_id)] = fields
        return index

    def _read_tmall_file(self, path: Path, link_index: dict[tuple[str, str], dict[str, Any]]) -> list[ImportRow]:
        df = pd.read_excel(path, sheet_name=0)
        rows: list[ImportRow] = []
        for _, item in df.iterrows():
            link_id = clean_id(item.get("商品ID"))
            if not link_id:
                rows.append(ImportRow({}, path.name, False, "missing 商品ID"))
                continue
            link = link_index.get(("天猫", link_id))
            if not link:
                rows.append(ImportRow({"平台商品ID": link_id}, path.name, False, "link not found"))
                continue
            dt = parse_date_value(item.get("统计日期"))
            product_id = as_text(link.get("款式编码"))
            fields = {
                "日期": date_to_ms(dt),
                "产品ID": product_id,
                "产品名": as_text(link.get("产品名称")) or as_text(item.get("商品名称")),
                "品类": join_category(item.get("一级类目名称"), item.get("二级类目名称"), item.get("叶子类目名称")),
                "平台": "天猫",
                "渠道": "平台汇总",
                "曝光": number_or_zero(item.get("PC端曝光量")),
                "点击": number_or_zero(item.get("商品访客数")),
                "加购": number_or_zero(item.get("加购人数") or item.get("加购件数")),
                "成交": number_or_zero(item.get("支付买家数") or item.get("支付件数")),
                "成交金额": number_or_zero(item.get("支付金额")),
                "退款": refund_count_from_amount(item.get("成功退款金额")),
                "平台商品ID": link_id,
                "推广状态": "自然/未拆分",
                "数据来源": path.name,
            }
            rows.append(ImportRow(clean_fields(fields), path.name, True))
        return rows

    def _read_red_file(self, path: Path, link_index: dict[tuple[str, str], dict[str, Any]]) -> list[ImportRow]:
        df = pd.read_excel(path, sheet_name=0)
        dt = date_from_filename(path.name)
        rows: list[ImportRow] = []
        for _, item in df.iterrows():
            link_id = clean_id(item.get("商品ID"))
            if not link_id:
                rows.append(ImportRow({}, path.name, False, "missing 商品ID"))
                continue
            link = link_index.get(("小红书", link_id))
            if not link:
                rows.append(ImportRow({"平台商品ID": link_id}, path.name, False, "link not found"))
                continue
            product_id = as_text(link.get("款式编码"))
            fields = {
                "日期": date_to_ms(dt),
                "产品ID": product_id,
                "产品名": as_text(link.get("产品名称")) or as_text(item.get("商品NAME")),
                "品类": join_category(item.get("一级品类"), item.get("二级品类")),
                "平台": "小红书",
                "渠道": as_text(item.get("载体")) or "平台汇总",
                "曝光": number_or_zero(item.get("商品浏览量")),
                "点击": number_or_zero(item.get("商品访客数")),
                "加购": number_or_zero(item.get("新增加购人数") or item.get("新增加购件数")),
                "成交": number_or_zero(item.get("支付买家数") or item.get("支付订单数")),
                "成交金额": number_or_zero(item.get("支付金额")),
                "退款": number_or_zero(item.get("退款订单数（支付时间）") or item.get("退款订单数（退款时间）")),
                "平台商品ID": link_id,
                "推广状态": as_text(item.get("载体")),
                "数据来源": path.name,
            }
            rows.append(ImportRow(clean_fields(fields), path.name, True))
        return rows

    def _existing_daily_keys(self) -> set[tuple[str, str, str, str, str]]:
        rows = self.client.list_records(self.config.feishu.daily_table_id, page_size=100)
        keys = set()
        for row in rows:
            fields = row.get("fields", {})
            if fields.get("产品ID"):
                keys.add(daily_key(fields))
        return keys

    def _summary(self, rows: list[ImportRow]) -> dict[str, Any]:
        by_file: dict[str, dict[str, int]] = {}
        skip_reasons: dict[str, int] = {}
        matched = 0
        for row in rows:
            stats = by_file.setdefault(row.source_file, {"matched": 0, "skipped": 0})
            if row.matched:
                matched += 1
                stats["matched"] += 1
            else:
                stats["skipped"] += 1
                skip_reasons[row.skip_reason] = skip_reasons.get(row.skip_reason, 0) + 1
        samples = [row.fields for row in rows if row.matched][:5]
        return {
            "folder": str(self.folder),
            "total_source_rows": len(rows),
            "matched_rows": matched,
            "skipped_rows": len(rows) - matched,
            "skip_reasons": skip_reasons,
            "by_file": by_file,
            "samples": samples,
        }


def clean_id(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def number_or_zero(value: Any) -> float:
    if value is None or pd.isna(value):
        return 0.0
    text = str(value).strip().replace(",", "")
    if not text or text in {"NULL", "-", "#DIV/0!", "#ERROR!"}:
        return 0.0
    if text.endswith("%"):
        return float(text[:-1]) / 100
    return float(text)


def refund_count_from_amount(value: Any) -> float:
    return 1.0 if number_or_zero(value) > 0 else 0.0


def parse_date_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return pd.to_datetime(value).to_pydatetime()


def date_from_filename(name: str) -> datetime:
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", name)
    if not match:
        raise RuntimeError(f"Cannot parse date from filename: {name}")
    return datetime.strptime(match.group(1), "%Y-%m-%d")


def date_to_ms(value: datetime) -> int:
    return int(datetime(value.year, value.month, value.day).timestamp() * 1000)


def join_category(*values: Any) -> str:
    parts = [as_text(value) for value in values if as_text(value)]
    return " / ".join(parts)


def clean_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value not in (None, "", [])}


def daily_key(fields: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(fields.get("日期") or ""),
        as_text(fields.get("产品ID")),
        as_text(fields.get("平台")),
        as_text(fields.get("渠道")),
        as_text(fields.get("平台商品ID")),
    )


def chunks(items: list[dict[str, Any]], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]
