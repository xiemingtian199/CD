from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .config import AppConfig
from .feishu import FeishuClient
from .normalizer import as_text
from .schema import FieldSpec, ensure_fields


@dataclass
class LinkRecord:
    product_id: str
    product_name: str
    platform: str
    platform_item_id: str
    price: str
    status: str


class LinkSynchronizer:
    def __init__(self, config: AppConfig, logger) -> None:
        self.config = config
        self.logger = logger
        self.client = FeishuClient(config.feishu)

    def sync_to_products(self) -> dict[str, int]:
        if not self.config.feishu.link_table_id:
            raise RuntimeError("FEISHU_LINK_TABLE_ID is not configured")

        self._ensure_product_fields()
        links = self._read_links()
        product_records = self.client.list_records(self.config.feishu.product_table_id, page_size=100)
        product_record_by_id = {
            as_text(item.get("fields", {}).get("产品ID")): item.get("record_id", "")
            for item in product_records
            if as_text(item.get("fields", {}).get("产品ID"))
        }

        grouped: dict[str, list[LinkRecord]] = defaultdict(list)
        for link in links:
            grouped[link.product_id].append(link)

        updates: list[dict[str, Any]] = []
        missing_products = 0
        for product_id, product_links in grouped.items():
            record_id = product_record_by_id.get(product_id)
            if not record_id:
                missing_products += 1
                continue
            updates.append(
                {
                    "record_id": record_id,
                    "fields": {
                        "已上架平台": join_unique(link.platform for link in product_links),
                        "平台链接汇总": join_unique(
                            f"{link.platform}:{link.platform_item_id}"
                            for link in product_links
                            if link.platform_item_id
                        ),
                        "链接状态汇总": join_unique(
                            f"{link.platform}:{link.status}"
                            for link in product_links
                            if link.status
                        ),
                    },
                }
            )

        written = 0
        for chunk in chunks(updates, 100):
            written += self.client.update_records_batch(self.config.feishu.product_table_id, chunk)

        return {
            "links": len(links),
            "matched_products": len(updates),
            "missing_products": missing_products,
            "written_products": written,
        }

    def _ensure_product_fields(self) -> None:
        class TableLike:
            name = "产品池"
            fields = (
                FieldSpec("已上架平台"),
                FieldSpec("平台链接汇总"),
                FieldSpec("链接状态汇总"),
            )

        ensure_fields(self.client, self.config.feishu.product_table_id, TableLike(), self.logger)

    def _read_links(self) -> list[LinkRecord]:
        rows = self.client.list_records(self.config.feishu.link_table_id, page_size=100)
        links: list[LinkRecord] = []
        for row in rows:
            fields = row.get("fields", {})
            product_id = as_text(fields.get("款式编码") or fields.get("产品ID"))
            platform_item_id = as_text(fields.get("链接ID") or fields.get("平台商品ID"))
            if not product_id or not platform_item_id:
                continue
            links.append(
                LinkRecord(
                    product_id=product_id,
                    product_name=as_text(fields.get("产品名称") or fields.get("产品名")),
                    platform=as_text(fields.get("平台")),
                    platform_item_id=platform_item_id,
                    price=as_text(fields.get("链接起售价格") or fields.get("链接起售价")),
                    status=as_text(fields.get("状态备注") or fields.get("状态")),
                )
            )
        return links


def join_unique(values) -> str:
    output: list[str] = []
    for value in values:
        text = as_text(value)
        if text and text not in output:
            output.append(text)
    return ",".join(output)


def chunks(items: list[dict[str, Any]], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]
