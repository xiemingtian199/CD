from __future__ import annotations

from dataclasses import dataclass
import logging

from .feishu import FeishuClient


TEXT = 1
NUMBER = 2
DATE = 5


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: int = TEXT


@dataclass(frozen=True)
class TableSpec:
    name: str
    fields: tuple[FieldSpec, ...]
    seed_records: tuple[dict[str, object], ...] = ()


SCHEMA: tuple[TableSpec, ...] = (
    TableSpec(
        name="产品池",
        fields=(
            FieldSpec("产品ID"),
            FieldSpec("产品名"),
            FieldSpec("品类"),
            FieldSpec("平台"),
            FieldSpec("渠道"),
            FieldSpec("负责人"),
            FieldSpec("测试批次"),
            FieldSpec("当前阶段"),
            FieldSpec("人工确认动作"),
            FieldSpec("确认人"),
            FieldSpec("确认时间", DATE),
        ),
    ),
    TableSpec(
        name="每日数据",
        fields=(
            FieldSpec("日期", DATE),
            FieldSpec("产品ID"),
            FieldSpec("产品名"),
            FieldSpec("品类"),
            FieldSpec("平台"),
            FieldSpec("渠道"),
            FieldSpec("曝光", NUMBER),
            FieldSpec("点击", NUMBER),
            FieldSpec("加购", NUMBER),
            FieldSpec("成交", NUMBER),
            FieldSpec("成交金额", NUMBER),
            FieldSpec("退款", NUMBER),
            FieldSpec("竞品曝光", NUMBER),
            FieldSpec("竞品点击", NUMBER),
            FieldSpec("竞品成交", NUMBER),
            FieldSpec("竞品动销备注"),
            FieldSpec("判断节点"),
            FieldSpec("原因归类"),
            FieldSpec("建议动作"),
            FieldSpec("置信度", NUMBER),
            FieldSpec("命中规则"),
            FieldSpec("判断日志"),
            FieldSpec("判断时间", DATE),
            FieldSpec("人工确认动作"),
            FieldSpec("确认人"),
            FieldSpec("确认时间", DATE),
            FieldSpec("数据来源"),
        ),
    ),
    TableSpec(
        name="规则配置",
        fields=(
            FieldSpec("平台"),
            FieldSpec("品类"),
            FieldSpec("渠道"),
            FieldSpec("最小曝光", NUMBER),
            FieldSpec("最小点击", NUMBER),
            FieldSpec("最小加购", NUMBER),
            FieldSpec("最小成交", NUMBER),
            FieldSpec("低点击率", NUMBER),
            FieldSpec("低成交转化率", NUMBER),
            FieldSpec("低加购成交率", NUMBER),
            FieldSpec("高退款率", NUMBER),
            FieldSpec("竞品低成交率", NUMBER),
            FieldSpec("放量点击率", NUMBER),
            FieldSpec("放量成交转化率", NUMBER),
            FieldSpec("放量退款率上限", NUMBER),
            FieldSpec("淘汰连续命中轮次", NUMBER),
        ),
        seed_records=(
            {
                "平台": "通用",
                "最小曝光": 300,
                "最小点击": 20,
                "最小加购": 5,
                "最小成交": 5,
                "低点击率": 0.01,
                "低成交转化率": 0.01,
                "低加购成交率": 0.15,
                "高退款率": 0.25,
                "竞品低成交率": 0.005,
                "放量点击率": 0.03,
                "放量成交转化率": 0.03,
                "放量退款率上限": 0.12,
                "淘汰连续命中轮次": 3,
            },
        ),
    ),
)


def setup_feishu_schema(client: FeishuClient, logger: logging.Logger) -> dict[str, str]:
    table_ids: dict[str, str] = {}
    existing_tables = {table_name(item): table_id(item) for item in client.list_tables()}
    configured_ids = {
        "产品池": client.config.product_table_id,
        "每日数据": client.config.daily_table_id,
        "规则配置": client.config.rule_table_id,
    }

    for table_spec in SCHEMA:
        table_id_value = configured_ids.get(table_spec.name) or existing_tables.get(table_spec.name)
        if table_spec.name == "每日数据" and not table_id_value:
            table_id_value = existing_tables.get("数据表")
        if table_id_value:
            logger.info("已存在数据表：%s (%s)", table_spec.name, table_id_value)
        else:
            try:
                table_id_value = client.create_table(table_spec.name, table_spec.fields[0].name)
                logger.info("已创建数据表：%s (%s)", table_spec.name, table_id_value)
            except Exception as exc:
                if table_spec.name == "规则配置":
                    logger.warning("无法创建规则配置表：%s。程序会继续使用内置默认阈值。", exc)
                    continue
                raise
        table_ids[table_spec.name] = table_id_value
        ensure_fields(client, table_id_value, table_spec, logger)
        seed_defaults(client, table_id_value, table_spec, logger)

    logger.info("请把下面三个表 ID 填入 .env：")
    logger.info("FEISHU_PRODUCT_TABLE_ID=%s", table_ids.get("产品池", ""))
    logger.info("FEISHU_DAILY_TABLE_ID=%s", table_ids.get("每日数据", ""))
    logger.info("FEISHU_RULE_TABLE_ID=%s", table_ids.get("规则配置", ""))
    return table_ids


def ensure_fields(client: FeishuClient, table_id_value: str, table_spec: TableSpec, logger: logging.Logger) -> None:
    existing_fields = {field_name(item) for item in client.list_fields(table_id_value)}
    for field in table_spec.fields:
        if field.name in existing_fields:
            continue
        client.create_field(table_id_value, field.name, field.type)
        logger.info("已补齐字段：%s.%s", table_spec.name, field.name)


def seed_defaults(client: FeishuClient, table_id_value: str, table_spec: TableSpec, logger: logging.Logger) -> None:
    if not table_spec.seed_records:
        return
    try:
        existing_records = client.list_records(table_id_value, page_size=20)
    except Exception:
        existing_records = []
    if existing_records:
        return
    for fields in table_spec.seed_records:
        client.create_record(table_id_value, fields)
    logger.info("已写入默认配置：%s %s 条", table_spec.name, len(table_spec.seed_records))


def table_name(item: dict) -> str:
    return str(item.get("name") or item.get("table", {}).get("name") or "")


def table_id(item: dict) -> str:
    return str(item.get("table_id") or item.get("id") or item.get("table", {}).get("table_id") or "")


def field_name(item: dict) -> str:
    return str(item.get("field_name") or item.get("name") or "")
