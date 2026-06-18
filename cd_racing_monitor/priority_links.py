from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .config import AppConfig
from .feishu import FeishuClient
from .normalizer import as_number, as_text
from .schema import DATE, NUMBER, TEXT, FieldSpec, TableSpec, ensure_fields


TABLE_NAME_PREFIX = "重点链接调整清单"
TEST_FOCUS_TABLE_NAME_PREFIX = "重点链接测试优化清单"
SIMPLE_TEST_FOCUS_TABLE_NAME_PREFIX = "重点链接简表"


@dataclass
class PriorityLinkResult:
    table_name: str
    table_id: str
    created_rows: int
    source_links: int
    selected_links: int
    latest_date: str


ADJUSTMENT_SPEC = TableSpec(
    name=TABLE_NAME_PREFIX,
    fields=(
        FieldSpec("链接键", TEXT),
        FieldSpec("优先级", NUMBER),
        FieldSpec("调整等级", TEXT),
        FieldSpec("产品ID", TEXT),
        FieldSpec("产品名", TEXT),
        FieldSpec("平台", TEXT),
        FieldSpec("链接ID", TEXT),
        FieldSpec("链接起售价格", NUMBER),
        FieldSpec("最近日期", DATE),
        FieldSpec("数据日期范围", TEXT),
        FieldSpec("现在的情况", TEXT),
        FieldSpec("需要调整和关注", TEXT),
        FieldSpec("主问题", TEXT),
        FieldSpec("建议动作", TEXT),
        FieldSpec("命中天数", NUMBER),
        FieldSpec("访客数", NUMBER),
        FieldSpec("加购", NUMBER),
        FieldSpec("成交", NUMBER),
        FieldSpec("销售额", NUMBER),
        FieldSpec("退款", NUMBER),
        FieldSpec("成交转化率", NUMBER),
        FieldSpec("加购成交率", NUMBER),
        FieldSpec("退款率", NUMBER),
        FieldSpec("命中规则", TEXT),
        FieldSpec("判断日志摘要", TEXT),
        FieldSpec("生成时间", DATE),
    ),
)

TEST_FOCUS_SPEC = TableSpec(
    name=TEST_FOCUS_TABLE_NAME_PREFIX,
    fields=(
        FieldSpec("链接键", TEXT),
        FieldSpec("关注排序", NUMBER),
        FieldSpec("关注等级", TEXT),
        FieldSpec("测试建议", TEXT),
        FieldSpec("产品ID", TEXT),
        FieldSpec("产品名", TEXT),
        FieldSpec("平台", TEXT),
        FieldSpec("链接ID", TEXT),
        FieldSpec("最近日期", DATE),
        FieldSpec("近期情况", TEXT),
        FieldSpec("判断依据", TEXT),
        FieldSpec("需要调整和关注", TEXT),
        FieldSpec("近3天访客", NUMBER),
        FieldSpec("近3天加购", NUMBER),
        FieldSpec("近3天成交", NUMBER),
        FieldSpec("近3天销售额", NUMBER),
        FieldSpec("近3天曝光", NUMBER),
        FieldSpec("近3天点击率", NUMBER),
        FieldSpec("近3天成交转化率", NUMBER),
        FieldSpec("累计访客", NUMBER),
        FieldSpec("累计加购", NUMBER),
        FieldSpec("累计成交", NUMBER),
        FieldSpec("累计销售额", NUMBER),
        FieldSpec("累计成交转化率", NUMBER),
        FieldSpec("原系统主判断", TEXT),
        FieldSpec("原系统建议", TEXT),
        FieldSpec("生成时间", DATE),
    ),
)

SIMPLE_TEST_FOCUS_SPEC = TableSpec(
    name=SIMPLE_TEST_FOCUS_TABLE_NAME_PREFIX,
    fields=(
        FieldSpec("对应链接", TEXT),
        FieldSpec("产品名称", TEXT),
        FieldSpec("平台", TEXT),
        FieldSpec("日期", DATE),
        FieldSpec("我的判断", TEXT),
        FieldSpec("访客转化销售金额", TEXT),
    ),
)


class PriorityLinkTableBuilder:
    def __init__(self, config: AppConfig, logger, limit: int = 12) -> None:
        self.config = config
        self.logger = logger
        self.limit = limit
        self.client = FeishuClient(config.feishu)

    def build(self) -> PriorityLinkResult:
        link_index = self._link_index()
        daily_rows = [row.get("fields", {}) for row in self.client.list_records(self.config.feishu.daily_table_id, page_size=100)]
        groups = group_daily_rows(daily_rows, link_index)
        selected = select_priority_links(groups, self.limit)
        table_name = f"{TABLE_NAME_PREFIX}-{datetime.now().strftime('%Y%m%d-%H%M')}"
        table_id = self.client.create_table(table_name, SIMPLE_TEST_FOCUS_SPEC.fields[0].name)
        ensure_fields(self.client, table_id, ADJUSTMENT_SPEC, self.logger)

        rows = [to_table_row(item) for item in selected]
        created = 0
        for chunk in chunks(rows, 100):
            created += self.client.create_records_batch(table_id, chunk)

        latest_date = max((item["latest_date"] for item in selected), default="")
        return PriorityLinkResult(
            table_name=table_name,
            table_id=table_id,
            created_rows=created,
            source_links=len(groups),
            selected_links=len(selected),
            latest_date=latest_date,
        )

    def _link_index(self) -> dict[tuple[str, str], dict[str, Any]]:
        if not self.config.feishu.link_table_id:
            return {}
        rows = self.client.list_records(self.config.feishu.link_table_id, page_size=100)
        output: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            fields = row.get("fields", {})
            platform = as_text(fields.get("平台"))
            link_id = as_text(fields.get("链接ID"))
            if platform and link_id:
                output[(platform, link_id)] = fields
        return output


class TestFocusLinkTableBuilder(PriorityLinkTableBuilder):
    def build(self) -> PriorityLinkResult:
        link_index = self._link_index()
        daily_rows = [row.get("fields", {}) for row in self.client.list_records(self.config.feishu.daily_table_id, page_size=100)]
        groups = group_daily_rows(daily_rows, link_index)
        selected = select_test_focus_links(groups, self.limit)
        table_name = f"{SIMPLE_TEST_FOCUS_TABLE_NAME_PREFIX}-{datetime.now().strftime('%Y%m%d-%H%M')}"
        table_id = self.client.create_table(table_name, SIMPLE_TEST_FOCUS_SPEC.fields[0].name)
        ensure_fields(self.client, table_id, SIMPLE_TEST_FOCUS_SPEC, self.logger)

        rows = [to_simple_test_focus_row(item) for item in selected]
        created = 0
        for chunk in chunks(rows, 100):
            created += self.client.create_records_batch(table_id, chunk)

        latest_date = max((item["latest_date"] for item in selected), default="")
        return PriorityLinkResult(
            table_name=table_name,
            table_id=table_id,
            created_rows=created,
            source_links=len(groups),
            selected_links=len(selected),
            latest_date=latest_date,
        )


def group_daily_rows(
    rows: list[dict[str, Any]],
    link_index: dict[tuple[str, str], dict[str, Any]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for fields in rows:
        product_id = as_text(fields.get("产品ID"))
        platform = as_text(fields.get("平台"))
        link_id = as_text(fields.get("平台商品ID"))
        if not product_id or not platform:
            continue
        if not link_id:
            link_id = product_id
        link_fields = link_index.get((platform, link_id), {})
        key = (platform, link_id, product_id)
        item = groups.setdefault(
            key,
            {
                "key": "|".join(key),
                "product_id": product_id,
                "product_name": as_text(link_fields.get("产品名称")) or as_text(fields.get("产品名")) or product_id,
                "platform": platform,
                "link_id": link_id,
                "start_price": as_number(link_fields.get("链接起售价格")),
                "dates": set(),
                "latest_date": "",
                "visitors": 0.0,
                "carts": 0.0,
                "orders": 0.0,
                "sales": 0.0,
                "refunds": 0.0,
                "impressions": 0.0,
                "actions": Counter(),
                "reasons": Counter(),
                "rules": Counter(),
                "logs": [],
                "daily": [],
                "confidence_sum": 0.0,
                "confidence_count": 0,
            },
        )
        date_text = normalize_date(fields.get("日期"))
        if date_text:
            item["dates"].add(date_text)
            item["latest_date"] = max(item["latest_date"], date_text)
        item["visitors"] += as_number(fields.get("点击"))
        item["carts"] += as_number(fields.get("加购"))
        item["orders"] += as_number(fields.get("成交"))
        item["sales"] += as_number(fields.get("成交金额"))
        item["refunds"] += as_number(fields.get("退款"))
        item["impressions"] += as_number(fields.get("曝光"))

        action = as_text(fields.get("建议动作")) or "未判断"
        reason = as_text(fields.get("原因归类")) or "未判断"
        rule = as_text(fields.get("命中规则"))
        log = as_text(fields.get("判断日志"))
        confidence = as_number(fields.get("置信度"))
        item["actions"][action] += 1
        item["reasons"][reason] += 1
        if rule:
            item["rules"][rule] += 1
        if log:
            item["logs"].append(log)
        if confidence:
            item["confidence_sum"] += confidence
            item["confidence_count"] += 1
        item["daily"].append(
            {
                "date": date_text,
                "impressions": as_number(fields.get("曝光")),
                "visitors": as_number(fields.get("点击")),
                "carts": as_number(fields.get("加购")),
                "orders": as_number(fields.get("成交")),
                "sales": as_number(fields.get("成交金额")),
                "refunds": as_number(fields.get("退款")),
                "action": action,
                "reason": reason,
            }
        )
    return groups


def select_priority_links(groups: dict[tuple[str, str, str], dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    enriched = []
    for item in groups.values():
        action = top_key(item["actions"])
        reason = top_key(item["reasons"])
        item["main_action"] = action
        item["main_reason"] = reason
        item["hit_days"] = sum(count for name, count in item["actions"].items() if name not in {"继续观察", "放量", "未判断"})
        item["conversion_rate"] = safe_rate(item["orders"], item["visitors"])
        item["cart_to_order_rate"] = safe_rate(item["orders"], item["carts"])
        item["refund_rate"] = safe_rate(item["refunds"], item["orders"])
        item["score"] = score_item(item)
        if item["hit_days"] > 0:
            enriched.append(item)
    return sorted(enriched, key=lambda item: (item["score"], item["hit_days"], item["visitors"]), reverse=True)[:limit]


def select_test_focus_links(groups: dict[tuple[str, str, str], dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    latest_date = max((item["latest_date"] for item in groups.values()), default="")
    enriched = []
    for item in groups.values():
        recent_rows = recent_daily_rows(item["daily"], latest_date, days=3)
        if not recent_rows:
            continue
        item["recent_impressions"] = sum(row["impressions"] for row in recent_rows)
        item["recent_visitors"] = sum(row["visitors"] for row in recent_rows)
        item["recent_carts"] = sum(row["carts"] for row in recent_rows)
        item["recent_orders"] = sum(row["orders"] for row in recent_rows)
        item["recent_sales"] = sum(row["sales"] for row in recent_rows)
        item["recent_click_rate"] = safe_rate(item["recent_visitors"], item["recent_impressions"])
        item["recent_conversion_rate"] = safe_rate(item["recent_orders"], item["recent_visitors"])
        item["conversion_rate"] = safe_rate(item["orders"], item["visitors"])
        item["cart_to_order_rate"] = safe_rate(item["orders"], item["carts"])
        item["main_action"] = top_key(item["actions"])
        item["main_reason"] = top_key(item["reasons"])
        item["test_action"] = choose_test_action(item)
        item["test_score"] = score_test_focus_item(item)
        if has_recent_test_signal(item):
            enriched.append(item)
    return sorted(enriched, key=lambda item: (item["test_score"], item["recent_orders"], item["recent_visitors"]), reverse=True)[:limit]


def recent_daily_rows(rows: list[dict[str, Any]], latest_date: str, days: int) -> list[dict[str, Any]]:
    if not latest_date:
        return rows
    latest = datetime.strptime(latest_date, "%Y-%m-%d").date()
    cutoff = latest.toordinal() - days + 1
    output = []
    for row in rows:
        if not row["date"]:
            continue
        current = datetime.strptime(row["date"], "%Y-%m-%d").date()
        if current.toordinal() >= cutoff:
            output.append(row)
    return output


def has_recent_test_signal(item: dict[str, Any]) -> bool:
    if item["recent_orders"] > 0:
        return True
    if item["recent_carts"] > 0 and item["recent_visitors"] > 0:
        return True
    if item["recent_visitors"] >= 3:
        return True
    return item["recent_impressions"] >= 100 and item["recent_click_rate"] < 0.015


def choose_test_action(item: dict[str, Any]) -> str:
    if item["recent_orders"] > 0 and item["recent_visitors"] < 30 and item["refunds"] == 0:
        return "增加推广测流量"
    if item["recent_carts"] > 0 and item["recent_orders"] == 0:
        return "调整价格/促销活动"
    if item["recent_visitors"] >= 5 and item["recent_orders"] == 0:
        return "换宣传方向"
    if item["recent_impressions"] >= 100 and item["recent_click_rate"] < 0.015:
        return "调整视觉"
    if item["recent_orders"] > 0:
        return "增加推广测流量"
    return "继续小流量观察"


def score_test_focus_item(item: dict[str, Any]) -> float:
    action_score = {
        "增加推广测流量": 90,
        "调整价格/促销活动": 82,
        "换宣传方向": 74,
        "调整视觉": 68,
        "继续小流量观察": 35,
    }.get(item["test_action"], 30)
    signal_score = (
        item["recent_orders"] * 80
        + item["recent_carts"] * 24
        + min(item["recent_visitors"], 60) * 2.2
        + min(item["recent_sales"], 300) * 0.2
    )
    if item["recent_orders"] > 0 and item["recent_visitors"] <= 10:
        signal_score += 25
    if item["recent_visitors"] > 0 and item["recent_orders"] == 0:
        signal_score += min(item["recent_visitors"], 25)
    return action_score + signal_score


def score_item(item: dict[str, Any]) -> float:
    action_score = {
        "淘汰": 100,
        "修产品/承诺": 88,
        "调价格/信任": 78,
        "改承接": 68,
        "改视觉": 62,
        "复测": 55,
        "继续观察": 15,
        "放量": -20,
        "未判断": 0,
    }.get(item["main_action"], 40)
    reason_score = {
        "产品与承诺问题": 18,
        "价格与信任问题": 14,
        "方向与承接问题": 12,
        "视觉/首屏吸引力问题": 10,
        "需求不足": 16,
        "数据量不足": -20,
    }.get(item["main_reason"], 0)
    volume_score = min(item["visitors"], 50) * 0.3 + min(item["sales"], 200) * 0.05
    return action_score + reason_score + item["hit_days"] * 8 + volume_score


def to_table_row(item: dict[str, Any]) -> dict[str, Any]:
    dates = sorted(item["dates"])
    level = priority_level(item["score"])
    situation = build_situation(item)
    adjustment = build_adjustment(item)
    latest_date_ms = date_to_ms(item["latest_date"]) if item["latest_date"] else None
    return clean_fields(
        {
            "链接键": item["key"],
            "优先级": round(item["score"], 2),
            "调整等级": level,
            "产品ID": item["product_id"],
            "产品名": item["product_name"],
            "平台": item["platform"],
            "链接ID": item["link_id"],
            "链接起售价格": item["start_price"],
            "最近日期": latest_date_ms,
            "数据日期范围": f"{dates[0]} 至 {dates[-1]}" if dates else "",
            "现在的情况": situation,
            "需要调整和关注": adjustment,
            "主问题": item["main_reason"],
            "建议动作": item["main_action"],
            "命中天数": item["hit_days"],
            "访客数": round(item["visitors"], 2),
            "加购": round(item["carts"], 2),
            "成交": round(item["orders"], 2),
            "销售额": round(item["sales"], 2),
            "退款": round(item["refunds"], 2),
            "成交转化率": round(item["conversion_rate"], 4),
            "加购成交率": round(item["cart_to_order_rate"], 4),
            "退款率": round(item["refund_rate"], 4),
            "命中规则": format_counter(item["rules"]),
            "判断日志摘要": "\n".join(item["logs"][-3:]),
            "生成时间": timestamp_ms(datetime.now()),
        }
    )


def to_test_focus_row(item: dict[str, Any]) -> dict[str, Any]:
    return clean_fields(
        {
            "链接键": item["key"],
            "关注排序": round(item["test_score"], 2),
            "关注等级": test_focus_level(item["test_score"]),
            "测试建议": item["test_action"],
            "产品ID": item["product_id"],
            "产品名": item["product_name"],
            "平台": item["platform"],
            "链接ID": item["link_id"],
            "最近日期": date_to_ms(item["latest_date"]) if item["latest_date"] else None,
            "近期情况": build_recent_situation(item),
            "判断依据": build_test_basis(item),
            "需要调整和关注": build_test_adjustment(item),
            "近3天访客": round(item["recent_visitors"], 2),
            "近3天加购": round(item["recent_carts"], 2),
            "近3天成交": round(item["recent_orders"], 2),
            "近3天销售额": round(item["recent_sales"], 2),
            "近3天曝光": round(item["recent_impressions"], 2),
            "近3天点击率": round(item["recent_click_rate"], 4),
            "近3天成交转化率": round(item["recent_conversion_rate"], 4),
            "累计访客": round(item["visitors"], 2),
            "累计加购": round(item["carts"], 2),
            "累计成交": round(item["orders"], 2),
            "累计销售额": round(item["sales"], 2),
            "累计成交转化率": round(item["conversion_rate"], 4),
            "原系统主判断": item["main_reason"],
            "原系统建议": item["main_action"],
            "生成时间": timestamp_ms(datetime.now()),
        }
    )


def to_simple_test_focus_row(item: dict[str, Any]) -> dict[str, Any]:
    return clean_fields(
        {
            "对应链接": format_link_reference(item),
            "产品名称": item["product_name"],
            "平台": item["platform"],
            "日期": date_to_ms(item["latest_date"]) if item["latest_date"] else None,
            "我的判断": build_simple_judgement(item),
            "访客转化销售金额": build_simple_metrics(item),
        }
    )


def format_link_reference(item: dict[str, Any]) -> str:
    return f"{item['platform']}：{item['link_id']}"


def build_simple_judgement(item: dict[str, Any]) -> str:
    action = item["test_action"]
    if action == "增加推广测流量":
        return "已有成交信号，建议增加小预算推广，验证放量后转化是否稳定。"
    if action == "调整价格/促销活动":
        return "有人加购但未成交，优先测试价格、优惠和信任背书。"
    if action == "换宣传方向":
        return "有访客但没有转化，建议换卖点/场景/人群方向重新测试。"
    if action == "调整视觉":
        return "有曝光但点击弱，先调整主图、标题、封面和首屏表达。"
    return "近期有少量信号但样本还小，建议继续小流量观察。"


def build_simple_metrics(item: dict[str, Any]) -> str:
    return (
        f"近3天：访客 {item['recent_visitors']:.0f}，成交 {item['recent_orders']:.0f}，"
        f"销售额 {item['recent_sales']:.2f}，转化率 {item['recent_conversion_rate']:.1%}；"
        f"累计：访客 {item['visitors']:.0f}，成交 {item['orders']:.0f}，销售额 {item['sales']:.2f}。"
    )


def build_recent_situation(item: dict[str, Any]) -> str:
    return (
        f"近3天访客 {item['recent_visitors']:.0f}，加购 {item['recent_carts']:.0f}，"
        f"成交 {item['recent_orders']:.0f}，销售额 {item['recent_sales']:.2f}。"
        f"累计访客 {item['visitors']:.0f}，累计成交 {item['orders']:.0f}，"
        f"累计成交转化率 {item['conversion_rate']:.2%}。"
    )


def build_test_basis(item: dict[str, Any]) -> str:
    action = item["test_action"]
    if action == "增加推广测流量":
        return "最近已经出现成交信号，且当前访客量仍偏小，适合用更多流量验证成交稳定性。"
    if action == "调整价格/促销活动":
        return "最近有人加购但没有完成成交，优先怀疑价格、优惠力度、信任背书或售后承诺影响临门一脚。"
    if action == "换宣传方向":
        return "最近有访客但没有成交，说明入口有一定吸引力，但卖点方向、详情承接或人群匹配可能不对。"
    if action == "调整视觉":
        return "最近有曝光但点击率偏低，优先检查主图、标题、封面和首屏卖点表达。"
    return "近期仍有少量测试信号，但样本不足以做强动作，先继续观察。"


def build_test_adjustment(item: dict[str, Any]) -> str:
    action = item["test_action"]
    if action == "增加推广测流量":
        return "给链接增加一轮小预算推广，保持当前承接不大改；重点看新增流量下成交转化率、退款和评价是否稳定。"
    if action == "调整价格/促销活动":
        return "测试价格带、券、满减或组合装；同步补强评价、资质、售后承诺，重点看加购到成交是否提升。"
    if action == "换宣传方向":
        return "重写投放卖点和详情首屏，换一个使用场景或人群切入；重点看成交转化率是否从 0 起量。"
    if action == "调整视觉":
        return "先换主图/封面/标题表达，不急着改价格；复测重点看点击率和访客是否提升。"
    return "继续保留小流量，等近3天访客或加购达到更明确样本后再判断。"


def test_focus_level(score: float) -> str:
    if score >= 200:
        return "P0 本轮重点"
    if score >= 130:
        return "P1 优先关注"
    return "P2 保留观察"


def build_situation(item: dict[str, Any]) -> str:
    return (
        f"近 {len(item['dates'])} 天累计访客 {item['visitors']:.0f}，加购 {item['carts']:.0f}，"
        f"成交 {item['orders']:.0f}，销售额 {item['sales']:.2f}，退款 {item['refunds']:.0f}。"
        f"主要判断为“{item['main_reason']}”，系统建议“{item['main_action']}”，"
        f"问题命中 {item['hit_days']} 天。"
    )


def build_adjustment(item: dict[str, Any]) -> str:
    reason = item["main_reason"]
    action = item["main_action"]
    if action == "淘汰":
        return "先暂停新增流量，复盘该链接是否已经多轮同类问题未改善；若没有明确改法，进入淘汰候选。"
    if "视觉" in reason:
        return "优先改主图、标题、短视频封面和首屏卖点；复测时重点看点击率和访客增长。"
    if "方向与承接" in reason:
        return "检查详情页承接、卖点一致性、商品定位和渠道人群匹配；复测重点看成交转化率。"
    if "价格与信任" in reason:
        return "检查价格带、优惠表达、评价、背书和售后承诺；复测重点看加购到成交转化。"
    if "产品与承诺" in reason:
        return "检查质量、规格/尺码、使用预期和宣传承诺偏差；复测重点看退款率和差评反馈。"
    if "需求" in reason:
        return "优先验证需求场景，减少继续优化视觉或承接的投入；必要时换场景或淘汰。"
    return "继续补充样本，关注访客、成交转化、加购成交和退款信号是否持续恶化。"


def priority_level(score: float) -> str:
    if score >= 140:
        return "P0 立即处理"
    if score >= 105:
        return "P1 本轮处理"
    return "P2 观察复测"


def normalize_date(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    text = as_text(value)
    return text[:10]


def date_to_ms(value: str) -> int:
    dt = datetime.strptime(value, "%Y-%m-%d")
    return timestamp_ms(dt)


def timestamp_ms(value: datetime) -> int:
    return int(datetime(value.year, value.month, value.day).timestamp() * 1000)


def safe_rate(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def top_key(counter: Counter) -> str:
    return counter.most_common(1)[0][0] if counter else ""


def format_counter(counter: Counter) -> str:
    return "；".join(f"{name}×{count}" for name, count in counter.most_common() if name)


def clean_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value not in (None, "", [])}


def chunks(items: list[dict[str, Any]], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]
