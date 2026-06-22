from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import logging
import sys
import time

from .config import load_config, load_feishu_schema_config
from .creative_briefs import CreativeBriefBuilder
from .dashboard import DashboardBuilder
from .dashboard_sync import FeishuDashboardDataSyncer
from .direction_testing import DirectionTestingBuilder
from .feishu import FeishuClient
from .legacy_migration import LegacyMigrator
from .links import LinkSynchronizer
from .local_import import LocalLinkDataImporter
from .pipeline import MonitorPipeline, evaluate_items
from .production_100_links import Production100LinksPlanBuilder
from .priority_links import TestFocusLinkTableBuilder
from .schema import setup_feishu_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="CD级产品赛马数据监控与判断程序")
    parser.add_argument("--once", action="store_true", help="读取飞书并运行一次")
    parser.add_argument("--schedule", help="每天固定时间运行，格式 HH:MM")
    parser.add_argument("--sample", action="store_true", help="运行本地样例，不连接飞书")
    parser.add_argument("--setup-feishu-schema", action="store_true", help="在飞书多维表中创建或补齐三张表结构")
    parser.add_argument("--preview-legacy", help="读取旧多维表 token，生成迁移预览 JSON，不写入新表")
    parser.add_argument("--preview-output", default="migration_preview.json", help="迁移预览输出文件")
    parser.add_argument("--migrate-legacy", help="读取旧多维表 token，并迁移到当前 .env 配置的新表")
    parser.add_argument("--sync-links-to-products", action="store_true", help="把链接表单里的平台链接汇总回产品池")
    parser.add_argument("--import-local-link-data", help="读取本地链接数据文件夹并导入每日数据")
    parser.add_argument("--preview-local-link-data", help="预览本地链接数据文件夹，不写入飞书")
    parser.add_argument("--build-dashboard", nargs="?", const="outputs/cd_product_dashboard.html", help="生成产品排行与趋势 HTML 仪表盘")
    parser.add_argument("--sync-feishu-dashboard-data", action="store_true", help="生成并同步飞书仪表盘需要的产品排行与趋势数据表")
    parser.add_argument("--create-priority-link-table", action="store_true", help="新建重点链接调整清单")
    parser.add_argument("--priority-link-limit", type=int, default=12, help="重点链接调整清单最多提取多少条")
    parser.add_argument("--setup-direction-testing", action="store_true", help="创建宣传方向测试管理表并生成下一轮测试计划")
    parser.add_argument("--direction-test-limit", type=int, default=20, help="下一轮测试计划最多生成多少条")
    parser.add_argument("--generate-creative-briefs", action="store_true", help="根据宣传方向库生成每个方向5张主图文案和画面描述")
    parser.add_argument("--setup-100-link-plan", action="store_true", help="创建每日100链接生产计划表并生成交接文档")
    parser.add_argument("--production-plan-doc", default="outputs/100链接日更生产计划.md", help="每日100链接生产计划 Markdown 输出路径")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("cd-racing-monitor")

    if args.sample:
        run_sample()
        return

    if args.setup_feishu_schema:
        config = load_feishu_schema_config()
        setup_feishu_schema(FeishuClient(config), logger)
        return

    if args.preview_legacy:
        base_config = load_feishu_schema_config()
        source_config = type(base_config)(
            base_config.app_id,
            base_config.app_secret,
            args.preview_legacy,
            base_config.product_table_id,
            base_config.daily_table_id,
            base_config.rule_table_id,
            base_config.link_table_id,
            base_config.base_url,
        )
        preview = LegacyMigrator(source_config).preview(args.preview_output)
        logger.info("迁移预览已生成：%s", args.preview_output)
        logger.info("可迁移产品 %s 条，每日数据 %s 条，跳过 %s 条。", preview.product_count, preview.daily_count, preview.skipped_daily_count)
        return

    if args.migrate_legacy:
        source_base = load_feishu_schema_config()
        target_config = load_config().feishu
        source_config = type(source_base)(
            source_base.app_id,
            source_base.app_secret,
            args.migrate_legacy,
            source_base.product_table_id,
            source_base.daily_table_id,
            source_base.rule_table_id,
            source_base.link_table_id,
            source_base.base_url,
        )
        result = LegacyMigrator(source_config, target_config).migrate(logger)
        logger.info("迁移完成：%s", result)
        return

    if args.sync_links_to_products:
        result = LinkSynchronizer(load_config(), logger).sync_to_products()
        logger.info("链接同步完成：%s", result)
        return

    if args.preview_local_link_data:
        result = LocalLinkDataImporter(load_config(), args.preview_local_link_data, logger).preview()
        logger.info("本地数据预览：%s", result)
        return

    if args.import_local_link_data:
        result = LocalLinkDataImporter(load_config(), args.import_local_link_data, logger).import_to_feishu()
        logger.info("本地数据导入完成：%s", result)
        return

    if args.build_dashboard:
        result = DashboardBuilder(load_config(), args.build_dashboard, logger).build()
        logger.info("仪表盘已生成：%s；产品 %s 个，数据 %s 行，最新日期 %s。", result.output_path, result.product_count, result.row_count, result.latest_date)
        return

    if args.sync_feishu_dashboard_data:
        result = FeishuDashboardDataSyncer(load_config(), logger).sync()
        logger.info(
            "飞书仪表数据已同步：排行表 %s（新增 %s，更新 %s），趋势表 %s（新增 %s，更新 %s），产品 %s 个，趋势 %s 行，最新日期 %s。",
            result.ranking_table_id,
            result.ranking_created,
            result.ranking_updated,
            result.trend_table_id,
            result.trend_created,
            result.trend_updated,
            result.product_count,
            result.trend_row_count,
            result.latest_date,
        )
        return

    if args.create_priority_link_table:
        result = TestFocusLinkTableBuilder(load_config(), logger, limit=args.priority_link_limit).build()
        logger.info(
            "重点链接调整清单已创建：%s (%s)，从 %s 个链接中提取 %s 个重点链接，写入 %s 行，最新日期 %s。",
            result.table_name,
            result.table_id,
            result.source_links,
            result.selected_links,
            result.created_rows,
            result.latest_date,
        )
        return

    if args.setup_direction_testing:
        result = DirectionTestingBuilder(load_config(), logger, limit=args.direction_test_limit).build()
        logger.info(
            "宣传方向测试管理已生成：方向库 %s，素材记录 %s，测试结果 %s，下一轮计划 %s；新增方向 %s 条，新增计划 %s 条，从 %s 个链接中规划 %s 个，最新日期 %s。",
            result.direction_table_id,
            result.material_table_id,
            result.result_table_id,
            result.plan_table_id,
            result.direction_rows_created,
            result.plan_rows_created,
            result.source_links,
            result.planned_links,
            result.latest_date,
        )
        return

    if args.generate_creative_briefs:
        result = CreativeBriefBuilder(load_config(), logger).build()
        logger.info(
            "主图文案方案已生成：表 %s；读取方向 %s 个，新增方案 %s 条。",
            result.creative_table_id,
            result.direction_count,
            result.created_rows,
        )
        return

    if args.setup_100_link_plan:
        result = Production100LinksPlanBuilder(load_config(), args.production_plan_doc, logger).build()
        logger.info(
            "100链接计划已创建：产品资料 %s，主题规划 %s，素材任务 %s，合规风险 %s，参考素材 %s；文档：%s",
            result.product_table_id,
            result.theme_table_id,
            result.task_table_id,
            result.risk_table_id,
            result.reference_table_id,
            result.doc_path,
        )
        return

    if args.schedule:
        run_schedule(args.schedule, logger)
        return

    if args.once:
        config = load_config()
        result = MonitorPipeline(config, logger).run_once()
        logger.info(
            "运行完成：读取 %s 条，写回 %s 条，跳过 %s 条。",
            result.read_records,
            result.written_records,
            result.skipped_records,
        )
        if result.errors:
            sys.exit(1)
        return

    parser.print_help()


def run_schedule(schedule_time: str, logger: logging.Logger) -> None:
    parse_schedule_time(schedule_time)
    logger.info("本地定时任务已启动，每天 %s 运行。", schedule_time)
    while True:
        now = datetime.now()
        next_run = next_run_at(now, schedule_time)
        sleep_seconds = max((next_run - now).total_seconds(), 1)
        logger.info("下一次运行时间：%s。", next_run.strftime("%Y-%m-%d %H:%M:%S"))
        time.sleep(sleep_seconds)
        config = load_config()
        MonitorPipeline(config, logger).run_once()


def next_run_at(now: datetime, schedule_time: str) -> datetime:
    hour, minute = parse_schedule_time(schedule_time)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def parse_schedule_time(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise ValueError("schedule must use HH:MM format") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("schedule must use HH:MM format")
    return hour, minute


def run_sample() -> None:
    rules = [{"fields": {"最小曝光": 300, "最小点击": 20, "最小加购": 5, "最小成交": 5}}]
    daily = [
        {"record_id": "rec_visual", "fields": {"产品ID": "P001", "平台": "通用", "渠道": "短视频", "曝光": 1000, "点击": 5}},
        {"record_id": "rec_landing", "fields": {"产品ID": "P002", "平台": "通用", "渠道": "搜索", "曝光": 1000, "点击": 80, "成交": 0}},
        {"record_id": "rec_trust", "fields": {"产品ID": "P003", "平台": "通用", "渠道": "直播", "曝光": 1000, "点击": 100, "加购": 20, "成交": 1}},
        {"record_id": "rec_promise", "fields": {"产品ID": "P004", "平台": "通用", "渠道": "直播", "曝光": 1000, "点击": 120, "加购": 30, "成交": 10, "退款": 4}},
        {
            "record_id": "rec_demand",
            "fields": {
                "产品ID": "P005",
                "平台": "通用",
                "渠道": "短视频",
                "曝光": 1000,
                "点击": 100,
                "成交": 0,
                "竞品点击": 100,
                "竞品成交": 0,
            },
        },
        {"record_id": "rec_scale", "fields": {"产品ID": "P006", "平台": "通用", "渠道": "投放", "曝光": 1000, "点击": 80, "加购": 20, "成交": 8, "退款": 0}},
    ]
    for record_id, decision in evaluate_items(daily, rules):
        print(f"{record_id}: {decision.reason} -> {decision.action} ({decision.confidence})")
        print(f"  {decision.log}")


if __name__ == "__main__":
    main()
