from __future__ import annotations

import logging

from .config import load_config
from .feishu import FIELD_INPUT_MARKER, FeishuClient, normalize_field_label


MANUAL_FIELDS: dict[str, set[str]] = {
    "产品池": {
        "产品ID",
        "产品名",
        "品类",
        "平台",
        "渠道",
        "负责人",
        "测试批次",
        "当前阶段",
        "人工确认动作",
        "确认人",
        "确认时间",
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
    },
    "链接表单": {"款式编码", "产品名称", "链接ID", "平台", "链接起售价格", "状态备注"},
    "每日数据": {"竞品动销备注", "人工确认动作", "确认人", "确认时间"},
    "规则配置": {
        "文本",
        "平台",
        "品类",
        "渠道",
        "最小曝光",
        "最小点击",
        "最小加购",
        "最小成交",
        "低点击率",
        "低成交转化率",
        "低加购成交率",
        "高退款率",
        "竞品低成交率",
        "放量点击率",
        "放量成交转化率",
        "放量退款率上限",
        "淘汰连续命中轮次",
    },
    "素材测试记录": {
        "产品ID",
        "产品名称",
        "平台",
        "链接ID",
        "方向ID",
        "方向名称",
        "素材编号",
        "素材类型",
        "素材说明",
        "上线日期",
        "下线日期",
        "测试状态",
        "测试结论",
    },
    "下一轮测试计划": {"计划状态"},
    "主图文案方案": {"状态"},
    "100链接计划-产品素材资料库": {
        "款式编码",
        "标准产品名称",
        "产品类目",
        "平台",
        "负责人",
        "每日目标链接数",
        "SKU数量",
        "SKU明细",
        "规格/型号/数量",
        "材质/成分",
        "基础卖点",
        "适用人群",
        "适用场景",
        "价格带",
        "白底图文件夹",
        "透明底图文件夹",
        "产品实拍文件夹",
        "注册证/资质文件夹",
        "可宣传范围",
        "备注",
    },
    "100链接计划-链接主题规划表": {"人工确认状态"},
    "100链接计划-素材生产任务表": {
        "人工审核状态",
        "制作状态",
        "上架包状态",
        "负责人",
        "完成时间",
        "下载文件路径",
        "人工质检结论",
    },
    "100链接计划-合规风险检查表": {"人工处理意见", "复检状态"},
    "100链接计划-参考素材池": {
        "参考素材名称",
        "素材来源",
        "来源链接/文件路径",
        "适用品类",
        "适用平台",
        "适用素材类型",
        "适用主题方向",
        "参考用途",
        "画面结构标签",
        "风格标签",
        "色调标签",
        "可借鉴点",
        "禁止复制点",
        "版权/授权状态",
        "合规审核状态",
        "优先级",
        "备注",
    },
}


def mark_manual_fields(logger: logging.Logger | None = None) -> int:
    logger = logger or logging.getLogger(__name__)
    client = FeishuClient(load_config().feishu)
    renamed_count = 0

    for table in client.list_tables():
        table_name = str(table.get("name") or table.get("table", {}).get("name") or "")
        table_id = str(table.get("table_id") or table.get("id") or "")
        manual_fields = MANUAL_FIELDS.get(table_name)
        if not table_id or not manual_fields:
            continue

        manual_normalized = {normalize_field_label(field) for field in manual_fields}
        for field in client.list_fields(table_id):
            field_name = str(field.get("field_name") or field.get("name") or "")
            if field_name.startswith(FIELD_INPUT_MARKER):
                continue
            if normalize_field_label(field_name) not in manual_normalized:
                continue

            field_id = str(field.get("field_id") or field.get("id") or "")
            field_type = int(field.get("type") or 1)
            if not field_id:
                continue

            new_name = f"{FIELD_INPUT_MARKER}{field_name}"
            try:
                client.update_field(table_id, field_id, new_name, field_type)
            except RuntimeError as exc:
                if "DataNotChange" in str(exc):
                    continue
                raise
            renamed_count += 1
            logger.info("%s: %s -> %s", table_name, field_name, new_name)

    return renamed_count


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    count = mark_manual_fields()
    print(f"已标注人工填写字段：{count} 个")


if __name__ == "__main__":
    main()
