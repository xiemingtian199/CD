from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .config import AppConfig
from .feishu import FeishuClient
from .normalizer import as_number, as_text
from .schema import DATE, NUMBER, TEXT, FieldSpec, TableSpec, ensure_fields, table_id, table_name


DIRECTION_TABLE = "宣传方向库"
MATERIAL_TABLE = "素材测试记录"
RESULT_TABLE = "方向测试结果"
PLAN_TABLE = "下一轮测试计划"


@dataclass
class DirectionTestingResult:
    direction_table_id: str
    material_table_id: str
    result_table_id: str
    plan_table_id: str
    direction_rows_created: int
    plan_rows_created: int
    source_links: int
    planned_links: int
    latest_date: str


DIRECTION_SPEC = TableSpec(
    name=DIRECTION_TABLE,
    fields=(
        FieldSpec("方向ID", TEXT),
        FieldSpec("产品ID", TEXT),
        FieldSpec("产品名称", TEXT),
        FieldSpec("平台", TEXT),
        FieldSpec("方向名称", TEXT),
        FieldSpec("目标人群", TEXT),
        FieldSpec("使用场景", TEXT),
        FieldSpec("核心痛点", TEXT),
        FieldSpec("核心卖点", TEXT),
        FieldSpec("信任背书", TEXT),
        FieldSpec("素材建议", TEXT),
        FieldSpec("状态", TEXT),
        FieldSpec("优先级", NUMBER),
        FieldSpec("备注", TEXT),
        FieldSpec("创建时间", DATE),
    ),
)

MATERIAL_SPEC = TableSpec(
    name=MATERIAL_TABLE,
    fields=(
        FieldSpec("测试ID", TEXT),
        FieldSpec("产品ID", TEXT),
        FieldSpec("产品名称", TEXT),
        FieldSpec("平台", TEXT),
        FieldSpec("链接ID", TEXT),
        FieldSpec("方向ID", TEXT),
        FieldSpec("方向名称", TEXT),
        FieldSpec("素材编号", TEXT),
        FieldSpec("素材类型", TEXT),
        FieldSpec("素材说明", TEXT),
        FieldSpec("上线日期", DATE),
        FieldSpec("下线日期", DATE),
        FieldSpec("测试状态", TEXT),
        FieldSpec("测试结论", TEXT),
    ),
)

RESULT_SPEC = TableSpec(
    name=RESULT_TABLE,
    fields=(
        FieldSpec("结果ID", TEXT),
        FieldSpec("测试ID", TEXT),
        FieldSpec("方向ID", TEXT),
        FieldSpec("产品ID", TEXT),
        FieldSpec("平台", TEXT),
        FieldSpec("链接ID", TEXT),
        FieldSpec("测试日期", DATE),
        FieldSpec("曝光", NUMBER),
        FieldSpec("访客", NUMBER),
        FieldSpec("加购", NUMBER),
        FieldSpec("成交", NUMBER),
        FieldSpec("销售额", NUMBER),
        FieldSpec("点击率", NUMBER),
        FieldSpec("成交转化率", NUMBER),
        FieldSpec("结果判断", TEXT),
        FieldSpec("下一步动作", TEXT),
    ),
)

PLAN_SPEC = TableSpec(
    name=PLAN_TABLE,
    fields=(
        FieldSpec("计划ID", TEXT),
        FieldSpec("产品ID", TEXT),
        FieldSpec("产品名称", TEXT),
        FieldSpec("平台", TEXT),
        FieldSpec("链接ID", TEXT),
        FieldSpec("计划方向", TEXT),
        FieldSpec("素材类型", TEXT),
        FieldSpec("素材要求", TEXT),
        FieldSpec("测试目标", TEXT),
        FieldSpec("建议动作", TEXT),
        FieldSpec("优先级", NUMBER),
        FieldSpec("计划状态", TEXT),
        FieldSpec("生成日期", DATE),
        FieldSpec("依据数据", TEXT),
    ),
)


class DirectionTestingBuilder:
    def __init__(self, config: AppConfig, logger, limit: int = 20) -> None:
        self.config = config
        self.logger = logger
        self.limit = limit
        self.client = FeishuClient(config.feishu)

    def build(self) -> DirectionTestingResult:
        tables = self._ensure_tables()
        links = self._link_index()
        daily_rows = [row.get("fields", {}) for row in self.client.list_records(self.config.feishu.daily_table_id, page_size=100)]
        groups = group_rows(daily_rows, links)
        candidates = select_candidates(groups, self.limit)

        existing_direction_ids = self._existing_keys(tables[DIRECTION_TABLE], "方向ID")
        existing_plan_ids = self._existing_keys(tables[PLAN_TABLE], "计划ID")
        existing_plan_signatures = self._existing_plan_signatures(tables[PLAN_TABLE])
        direction_rows: list[dict[str, Any]] = []
        plan_rows: list[dict[str, Any]] = []
        now_ms = timestamp_ms(datetime.now())
        for candidate in candidates:
            direction = direction_for_candidate(candidate)
            direction_id = direction_key(candidate, direction)
            if direction_id not in existing_direction_ids:
                direction_rows.append(
                    clean_fields(
                        {
                            "方向ID": direction_id,
                            "产品ID": candidate["product_id"],
                            "产品名称": candidate["product_name"],
                            "平台": candidate["platform"],
                            "方向名称": direction["name"],
                            "目标人群": direction["audience"],
                            "使用场景": direction["scene"],
                            "核心痛点": direction["pain"],
                            "核心卖点": direction["benefit"],
                            "信任背书": direction["trust"],
                            "素材建议": direction["material"],
                            "状态": "待测试",
                            "优先级": candidate["priority"],
                            "备注": direction["note"],
                            "创建时间": now_ms,
                        }
                    )
                )
                existing_direction_ids.add(direction_id)
            plan_row = to_plan_row(candidate, direction, direction_id, now_ms)
            plan_id = as_text(plan_row.get("计划ID"))
            signature = plan_signature(plan_row)
            if plan_id and plan_id not in existing_plan_ids and signature not in existing_plan_signatures:
                plan_rows.append(plan_row)
                existing_plan_ids.add(plan_id)
                existing_plan_signatures.add(signature)

        direction_created = self._create_rows(tables[DIRECTION_TABLE], direction_rows)
        plan_created = self._create_rows(tables[PLAN_TABLE], plan_rows)
        latest_date = max((item["latest_date"] for item in candidates), default="")
        return DirectionTestingResult(
            direction_table_id=tables[DIRECTION_TABLE],
            material_table_id=tables[MATERIAL_TABLE],
            result_table_id=tables[RESULT_TABLE],
            plan_table_id=tables[PLAN_TABLE],
            direction_rows_created=direction_created,
            plan_rows_created=plan_created,
            source_links=len(groups),
            planned_links=len(candidates),
            latest_date=latest_date,
        )

    def _ensure_tables(self) -> dict[str, str]:
        specs = (DIRECTION_SPEC, MATERIAL_SPEC, RESULT_SPEC, PLAN_SPEC)
        existing = {table_name(item): table_id(item) for item in self.client.list_tables()}
        output: dict[str, str] = {}
        for spec in specs:
            current_id = existing.get(spec.name)
            if current_id:
                self.logger.info("已找到测试管理表：%s (%s)", spec.name, current_id)
            else:
                current_id = self.client.create_table(spec.name, spec.fields[0].name)
                self.logger.info("已创建测试管理表：%s (%s)", spec.name, current_id)
            ensure_fields(self.client, current_id, spec, self.logger)
            output[spec.name] = current_id
        return output

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

    def _existing_keys(self, table_id_value: str, key_field: str) -> set[str]:
        rows = self.client.list_records(table_id_value, page_size=100)
        return {as_text(row.get("fields", {}).get(key_field)) for row in rows if as_text(row.get("fields", {}).get(key_field))}

    def _existing_plan_signatures(self, table_id_value: str) -> set[str]:
        rows = self.client.list_records(table_id_value, page_size=100)
        signatures = set()
        for row in rows:
            fields = row.get("fields", {})
            if as_text(fields.get("计划状态")) == "已完成":
                continue
            signatures.add(plan_signature(fields))
        return {value for value in signatures if value}

    def _create_rows(self, table_id_value: str, rows: list[dict[str, Any]]) -> int:
        created = 0
        for chunk in chunks(rows, 100):
            created += self.client.create_records_batch(table_id_value, chunk)
        return created


def group_rows(rows: list[dict[str, Any]], links: dict[tuple[str, str], dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for fields in rows:
        product_id = as_text(fields.get("产品ID"))
        platform = as_text(fields.get("平台"))
        link_id = as_text(fields.get("平台商品ID")) or product_id
        if not product_id or not platform:
            continue
        link_fields = links.get((platform, link_id), {})
        key = f"{platform}|{link_id}|{product_id}"
        item = groups.setdefault(
            key,
            {
                "key": key,
                "product_id": product_id,
                "product_name": as_text(link_fields.get("产品名称")) or as_text(fields.get("产品名")) or product_id,
                "platform": platform,
                "link_id": link_id,
                "dates": set(),
                "latest_date": "",
                "impressions": 0.0,
                "visitors": 0.0,
                "carts": 0.0,
                "orders": 0.0,
                "sales": 0.0,
                "reasons": Counter(),
                "actions": Counter(),
                "daily": [],
            },
        )
        date_text = normalize_date(fields.get("日期"))
        if date_text:
            item["dates"].add(date_text)
            item["latest_date"] = max(item["latest_date"], date_text)
        metrics = {
            "impressions": as_number(fields.get("曝光")),
            "visitors": as_number(fields.get("点击")),
            "carts": as_number(fields.get("加购")),
            "orders": as_number(fields.get("成交")),
            "sales": as_number(fields.get("成交金额")),
        }
        for metric, value in metrics.items():
            item[metric] += value
        item["reasons"][as_text(fields.get("原因归类")) or "未判断"] += 1
        item["actions"][as_text(fields.get("建议动作")) or "未判断"] += 1
        item["daily"].append({"date": date_text, **metrics})
    return groups


def select_candidates(groups: dict[str, dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    latest_date = max((item["latest_date"] for item in groups.values()), default="")
    output = []
    for item in groups.values():
        recent = recent_rows(item["daily"], latest_date, 3)
        if not recent:
            continue
        item["recent_impressions"] = sum(row["impressions"] for row in recent)
        item["recent_visitors"] = sum(row["visitors"] for row in recent)
        item["recent_carts"] = sum(row["carts"] for row in recent)
        item["recent_orders"] = sum(row["orders"] for row in recent)
        item["recent_sales"] = sum(row["sales"] for row in recent)
        item["recent_click_rate"] = safe_rate(item["recent_visitors"], item["recent_impressions"])
        item["recent_conversion_rate"] = safe_rate(item["recent_orders"], item["recent_visitors"])
        item["conversion_rate"] = safe_rate(item["orders"], item["visitors"])
        item["main_reason"] = top_key(item["reasons"])
        item["main_action"] = top_key(item["actions"])
        item["test_action"] = choose_action(item)
        item["priority"] = priority_score(item)
        if has_signal(item):
            output.append(item)
    return sorted(output, key=lambda item: (item["priority"], item["recent_orders"], item["recent_visitors"]), reverse=True)[:limit]


def has_signal(item: dict[str, Any]) -> bool:
    return (
        item["recent_orders"] > 0
        or item["recent_carts"] > 0
        or item["recent_visitors"] >= 3
        or item["recent_impressions"] >= 100
    )


def choose_action(item: dict[str, Any]) -> str:
    if item["recent_orders"] > 0 and item["recent_visitors"] < 30:
        return "增加推广测流量"
    if item["recent_carts"] > 0 and item["recent_orders"] == 0:
        return "调整价格/促销活动"
    if item["recent_visitors"] >= 5 and item["recent_orders"] == 0:
        return "换宣传方向"
    if item["recent_impressions"] >= 100 and item["recent_click_rate"] < 0.015:
        return "调整视觉"
    return "继续小流量观察"


def priority_score(item: dict[str, Any]) -> float:
    base = {
        "增加推广测流量": 90,
        "调整价格/促销活动": 82,
        "换宣传方向": 74,
        "调整视觉": 68,
        "继续小流量观察": 35,
    }.get(item["test_action"], 30)
    return base + item["recent_orders"] * 80 + item["recent_carts"] * 24 + min(item["recent_visitors"], 50) * 2


def direction_for_candidate(item: dict[str, Any]) -> dict[str, str]:
    product_name = item["product_name"]
    category = infer_category(product_name)
    action = item["test_action"]
    if action == "增加推广测流量":
        return {
            "name": "成交信号放量验证",
            "audience": category["audience"],
            "scene": category["scene"],
            "pain": category["pain"],
            "benefit": category["benefit"],
            "trust": "保持当前已出单表达，补充评价、售后和资质承诺",
            "material": "保留当前主卖点，新做1条推广短视频或投放图，突出已验证卖点",
            "note": "不要大改承接，先验证流量扩大后转化是否稳定。",
        }
    if action == "调整价格/促销活动":
        return {
            "name": "价格促销与信任增强",
            "audience": category["audience"],
            "scene": category["scene"],
            "pain": "想买但临门一脚犹豫",
            "benefit": "更明确的价格利益、组合装或限时优惠",
            "trust": "评价、资质、售后承诺、退换保障",
            "material": "主图角标/标题/详情首屏加入优惠利益点，准备券、满减或组合装素材",
            "note": "重点看加购到成交是否提升。",
        }
    if action == "换宣传方向":
        return {
            "name": category["direction"],
            "audience": category["audience"],
            "scene": category["scene"],
            "pain": category["pain"],
            "benefit": category["benefit"],
            "trust": category["trust"],
            "material": "重做首屏卖点、标题和1条场景化短视频/图文",
            "note": "用新场景或新人群验证，而不是只微调图片。",
        }
    if action == "调整视觉":
        return {
            "name": "首屏点击吸引力测试",
            "audience": category["audience"],
            "scene": category["scene"],
            "pain": "第一眼没有被点开",
            "benefit": "更直观展示用途、效果或价格利益",
            "trust": category["trust"],
            "material": "至少准备2版主图/封面：痛点版、场景版",
            "note": "只先看点击和访客变化。",
        }
    return {
        "name": "小流量继续观察",
        "audience": category["audience"],
        "scene": category["scene"],
        "pain": category["pain"],
        "benefit": category["benefit"],
        "trust": category["trust"],
        "material": "保留当前素材，等更多访客或加购信号",
        "note": "样本不足，暂不做大改。",
    }


def infer_category(product_name: str) -> dict[str, str]:
    name = product_name.lower()
    if any(word in product_name for word in ("固定器", "护具", "髌骨", "腰部", "腕关节")):
        return {
            "direction": "疼痛支撑场景",
            "audience": "久坐办公、运动恢复、关节不适人群",
            "scene": "办公久坐、运动后、日常支撑、防护恢复",
            "pain": "支撑不稳、活动不方便、疼痛反复",
            "benefit": "稳定支撑、佩戴舒适、行动更安心",
            "trust": "医疗器械资质、规格说明、佩戴教程、售后承诺",
        }
    if any(word in product_name for word in ("漱口", "口腔", "含漱", "牙刷")):
        return {
            "direction": "口腔清洁安心场景",
            "audience": "关注口气、口腔清洁、家庭护理人群",
            "scene": "饭后、睡前、办公室、外出随身护理",
            "pain": "口气尴尬、清洁不彻底、刺激感强",
            "benefit": "清洁更方便、口气更清爽、使用更安心",
            "trust": "成分说明、检测资质、使用方法、用户评价",
        }
    if any(word in product_name for word in ("湿厕纸", "洗衣液", "纸", "清洁")):
        return {
            "direction": "家庭囤货与日常消耗场景",
            "audience": "家庭用户、精致生活、清洁护理人群",
            "scene": "家庭常备、卫生间、换季清洁、囤货",
            "pain": "用得快、怕不干净、怕刺激、选择麻烦",
            "benefit": "更干净、更温和、更划算、更省心",
            "trust": "成分/材质说明、评价、优惠组合、售后保障",
        }
    if any(word in product_name for word in ("胸贴", "防走光", "内衣")):
        return {
            "direction": "穿搭应急与隐形防护场景",
            "audience": "女性穿搭、通勤、约会、旅行人群",
            "scene": "夏季穿搭、礼服、通勤、旅行应急",
            "pain": "尴尬、防走光、不舒适、不服帖",
            "benefit": "隐形自然、贴合稳定、使用安心",
            "trust": "材质安全、使用教程、真实评价、售后承诺",
        }
    if any(word in product_name for word in ("体温计", "冰袋", "敷贴")):
        return {
            "direction": "家庭应急常备场景",
            "audience": "家庭用户、老人小孩照护、应急护理人群",
            "scene": "家中常备、发热/受伤应急、外出备用",
            "pain": "临时需要买不到、不会选、担心不专业",
            "benefit": "常备安心、使用方便、应急更快",
            "trust": "资质、使用说明、家庭场景评价、售后承诺",
        }
    return {
        "direction": "核心需求场景验证",
        "audience": "当前品类潜在人群",
        "scene": "高频使用或应急购买场景",
        "pain": "当前需求不够明确或卖点没有打中",
        "benefit": "把用途、利益和购买理由说得更直接",
        "trust": "评价、资质、售后、真实使用反馈",
    }


def to_plan_row(item: dict[str, Any], direction: dict[str, str], direction_id: str, now_ms: int) -> dict[str, Any]:
    plan_id = f"PLAN-{item['platform']}-{item['link_id']}-{item['latest_date']}-{direction_id}"
    return clean_fields(
        {
            "计划ID": plan_id,
            "产品ID": item["product_id"],
            "产品名称": item["product_name"],
            "平台": item["platform"],
            "链接ID": item["link_id"],
            "计划方向": direction["name"],
            "素材类型": material_type(item["test_action"]),
            "素材要求": direction["material"],
            "测试目标": test_goal(item["test_action"]),
            "建议动作": item["test_action"],
            "优先级": round(item["priority"], 2),
            "计划状态": "待执行",
            "生成日期": now_ms,
            "依据数据": basis_text(item),
        }
    )


def plan_signature(fields: dict[str, Any]) -> str:
    platform = as_text(fields.get("平台"))
    link_id = as_text(fields.get("链接ID"))
    direction = as_text(fields.get("计划方向"))
    if not platform or not link_id or not direction:
        return ""
    return f"{platform}|{link_id}|{direction}"


def material_type(action: str) -> str:
    if action == "调整视觉":
        return "主图/封面"
    if action == "换宣传方向":
        return "标题+详情首屏+短视频"
    if action == "调整价格/促销活动":
        return "促销图+详情首屏"
    if action == "增加推广测流量":
        return "投放素材"
    return "保留当前素材"


def test_goal(action: str) -> str:
    if action == "增加推广测流量":
        return "验证放量后成交转化是否稳定"
    if action == "调整价格/促销活动":
        return "提升加购到成交转化"
    if action == "换宣传方向":
        return "验证新人群/新场景是否带来成交"
    if action == "调整视觉":
        return "提升点击和访客"
    return "继续积累样本"


def basis_text(item: dict[str, Any]) -> str:
    return (
        f"近3天访客{item['recent_visitors']:.0f}、加购{item['recent_carts']:.0f}、"
        f"成交{item['recent_orders']:.0f}、销售额{item['recent_sales']:.2f}；"
        f"累计访客{item['visitors']:.0f}、成交{item['orders']:.0f}、转化率{item['conversion_rate']:.1%}。"
    )


def direction_key(item: dict[str, Any], direction: dict[str, str]) -> str:
    safe_name = direction["name"].replace(" ", "")
    return f"DIR-{item['product_id']}-{item['platform']}-{safe_name}"


def recent_rows(rows: list[dict[str, Any]], latest_date: str, days: int) -> list[dict[str, Any]]:
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


def normalize_date(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    return as_text(value)[:10]


def safe_rate(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def top_key(counter: Counter) -> str:
    return counter.most_common(1)[0][0] if counter else ""


def date_to_ms(value: str) -> int:
    dt = datetime.strptime(value, "%Y-%m-%d")
    return timestamp_ms(dt)


def timestamp_ms(value: datetime) -> int:
    return int(datetime(value.year, value.month, value.day).timestamp() * 1000)


def clean_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value not in (None, "", [])}


def chunks(items: list[dict[str, Any]], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]
