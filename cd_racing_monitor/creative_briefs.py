from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .config import AppConfig
from .feishu import FeishuClient
from .normalizer import as_number, as_text
from .schema import DATE, NUMBER, TEXT, FieldSpec, TableSpec, ensure_fields, table_id, table_name


DIRECTION_TABLE = "宣传方向库"
CREATIVE_TABLE = "主图文案方案"


@dataclass
class CreativeBriefResult:
    creative_table_id: str
    direction_count: int
    created_rows: int


CREATIVE_SPEC = TableSpec(
    name=CREATIVE_TABLE,
    fields=(
        FieldSpec("方案ID", TEXT),
        FieldSpec("产品ID", TEXT),
        FieldSpec("产品名称", TEXT),
        FieldSpec("平台", TEXT),
        FieldSpec("方向ID", TEXT),
        FieldSpec("方向名称", TEXT),
        FieldSpec("主图序号", NUMBER),
        FieldSpec("主图目的", TEXT),
        FieldSpec("主文案", TEXT),
        FieldSpec("辅助文案", TEXT),
        FieldSpec("角标/信任点", TEXT),
        FieldSpec("画面描述词", TEXT),
        FieldSpec("设计备注", TEXT),
        FieldSpec("状态", TEXT),
        FieldSpec("生成时间", DATE),
    ),
)


class CreativeBriefBuilder:
    def __init__(self, config: AppConfig, logger) -> None:
        self.config = config
        self.logger = logger
        self.client = FeishuClient(config.feishu)

    def build(self) -> CreativeBriefResult:
        tables = {table_name(item): table_id(item) for item in self.client.list_tables()}
        direction_table_id = tables.get(DIRECTION_TABLE)
        if not direction_table_id:
            raise RuntimeError("请先运行宣传方向测试管理，创建“宣传方向库”。")
        creative_table_id = tables.get(CREATIVE_TABLE)
        if creative_table_id:
            self.logger.info("已找到主图方案表：%s (%s)", CREATIVE_TABLE, creative_table_id)
        else:
            creative_table_id = self.client.create_table(CREATIVE_TABLE, CREATIVE_SPEC.fields[0].name)
            self.logger.info("已创建主图方案表：%s (%s)", CREATIVE_TABLE, creative_table_id)
        ensure_fields(self.client, creative_table_id, CREATIVE_SPEC, self.logger)

        directions = [row.get("fields", {}) for row in self.client.list_records(direction_table_id, page_size=100)]
        existing_ids = self._existing_ids(creative_table_id)
        rows: list[dict[str, Any]] = []
        now_ms = timestamp_ms(datetime.now())
        for direction in directions:
            for brief in build_briefs(direction):
                fields = to_row(direction, brief, now_ms)
                brief_id = as_text(fields.get("方案ID"))
                if brief_id and brief_id not in existing_ids:
                    rows.append(fields)
                    existing_ids.add(brief_id)
        created = 0
        for chunk in chunks(rows, 100):
            created += self.client.create_records_batch(creative_table_id, chunk)
        return CreativeBriefResult(
            creative_table_id=creative_table_id,
            direction_count=len(directions),
            created_rows=created,
        )

    def _existing_ids(self, table_id_value: str) -> set[str]:
        rows = self.client.list_records(table_id_value, page_size=100)
        return {as_text(row.get("fields", {}).get("方案ID")) for row in rows if as_text(row.get("fields", {}).get("方案ID"))}


def build_briefs(direction: dict[str, Any]) -> list[dict[str, str]]:
    product = as_text(direction.get("产品名称"))
    direction_name = as_text(direction.get("方向名称"))
    audience = as_text(direction.get("目标人群"))
    scene = as_text(direction.get("使用场景"))
    pain = as_text(direction.get("核心痛点"))
    benefit = as_text(direction.get("核心卖点"))
    trust = as_text(direction.get("信任背书"))
    category = category_for_product(product)
    tone = platform_tone(as_text(direction.get("平台")))

    return [
        {
            "index": "1",
            "purpose": "痛点直击",
            "headline": pain_headline(product, pain, category),
            "sub": f"{benefit}，适合{scene}。",
            "badge": trust_badge(trust),
            "visual": f"{tone}，产品居中大图，左侧放大痛点文字，背景呈现{scene}，画面干净明亮，突出使用前的困扰和产品解决方案",
            "note": "用于测试第一眼是否能抓住真实痛点，文字控制在两行内。",
        },
        {
            "index": "2",
            "purpose": "场景代入",
            "headline": scene_headline(product, scene, category),
            "sub": f"给{audience}的日常解决方案。",
            "badge": "场景化测试",
            "visual": f"{tone}，真实生活场景图，人物正在{scene.split('、')[0] if scene else '日常使用'}，产品在手边或正在使用，加入少量箭头标注核心卖点",
            "note": "用于测试哪类使用场景最容易带来点击和成交。",
        },
        {
            "index": "3",
            "purpose": "利益点强化",
            "headline": benefit_headline(product, benefit, category),
            "sub": f"把“{pain}”变得更好处理。",
            "badge": "核心卖点",
            "visual": f"{tone}，产品细节特写，三点式卖点标签围绕产品展开，背景用浅色块区分信息层级，整体电商主图风格",
            "note": "用于测试用户是否更吃明确利益点，而不是泛场景表达。",
        },
        {
            "index": "4",
            "purpose": "信任背书",
            "headline": trust_headline(product, trust),
            "sub": f"先解决不敢买，再推动下单。",
            "badge": trust_badge(trust),
            "visual": f"{tone}，产品包装/资质/评价元素同屏展示，右侧放信任背书信息，底部放售后或使用说明提示，避免夸大医疗效果",
            "note": "用于测试加购不成交时，信任信息能否提升转化。",
        },
        {
            "index": "5",
            "purpose": "促销转化",
            "headline": promo_headline(product, direction_name),
            "sub": "适合小预算推广测试，观察成交转化是否稳定。",
            "badge": "限时测试",
            "visual": f"{tone}，产品大图加价格/优惠信息占位，主视觉突出购买理由，加入简洁促销角标和行动引导，背景保留平台电商感",
            "note": "用于测试有成交或有加购后的临门一脚，不要堆太多文字。",
        },
    ]


def category_for_product(product: str) -> str:
    if any(word in product for word in ("固定器", "护具", "髌骨", "腰部", "腕关节")):
        return "support"
    if any(word in product for word in ("漱口", "口腔", "含漱", "牙刷")):
        return "oral"
    if any(word in product for word in ("湿厕纸", "洗衣液", "纸", "清洁")):
        return "clean"
    if any(word in product for word in ("胸贴", "防走光", "内衣")):
        return "wear"
    if any(word in product for word in ("体温计", "冰袋", "敷贴")):
        return "homecare"
    return "general"


def platform_tone(platform: str) -> str:
    if platform == "小红书":
        return "小红书种草风，真实生活感，柔和自然光"
    return "天猫电商主图风，清晰产品展示，高对比但不过度花哨"


def pain_headline(product: str, pain: str, category: str) -> str:
    if category == "support":
        return f"{product}，支撑不稳就该换个思路"
    if category == "oral":
        return f"口腔尴尬，别等别人提醒"
    if category == "clean":
        return f"日常清洁，别只看便宜"
    if category == "wear":
        return f"穿得好看，也要防尴尬"
    if category == "homecare":
        return f"家里常备，临时需要不慌"
    return f"{product}，解决{short_text(pain, 8)}"


def scene_headline(product: str, scene: str, category: str) -> str:
    first_scene = scene.split("、")[0] if scene else "日常使用"
    if category == "support":
        return f"{first_scene}，多一层稳定支撑"
    if category == "oral":
        return f"{first_scene}，口气清爽一点"
    if category == "clean":
        return f"{first_scene}，干净省心一点"
    if category == "wear":
        return f"{first_scene}，隐形更安心"
    if category == "homecare":
        return f"{first_scene}，先把应急备好"
    return f"{first_scene}，试试{product}"


def benefit_headline(product: str, benefit: str, category: str) -> str:
    if category == "support":
        return "稳稳支撑，活动更安心"
    if category == "oral":
        return "清爽入口，护理更方便"
    if category == "clean":
        return "干净、温和、用得放心"
    if category == "wear":
        return "隐形贴合，不抢穿搭"
    if category == "homecare":
        return "应急常备，用时更快"
    return short_text(benefit, 14)


def trust_headline(product: str, trust: str) -> str:
    if "资质" in trust or "医疗" in trust:
        return "看得见的资质，买得更安心"
    if "评价" in trust:
        return "先看真实反馈，再决定"
    if "售后" in trust:
        return "售后有承诺，下单少顾虑"
    return "把信任信息放到第一屏"


def promo_headline(product: str, direction_name: str) -> str:
    if "放量" in direction_name or "成交" in direction_name:
        return "已有人买，值得再测一轮"
    if "价格" in direction_name or "促销" in direction_name:
        return "加购了？差一个下单理由"
    return "这一版，换个理由让你点"


def trust_badge(trust: str) -> str:
    if "资质" in trust or "医疗" in trust:
        return "资质/说明"
    if "评价" in trust:
        return "真实评价"
    if "售后" in trust:
        return "售后承诺"
    return "安心背书"


def short_text(value: str, size: int) -> str:
    return value[:size] if len(value) > size else value


def to_row(direction: dict[str, Any], brief: dict[str, str], now_ms: int) -> dict[str, Any]:
    direction_id = as_text(direction.get("方向ID"))
    index = int(as_number(brief["index"]))
    return {
        "方案ID": f"{direction_id}-IMG{index}",
        "产品ID": as_text(direction.get("产品ID")),
        "产品名称": as_text(direction.get("产品名称")),
        "平台": as_text(direction.get("平台")),
        "方向ID": direction_id,
        "方向名称": as_text(direction.get("方向名称")),
        "主图序号": index,
        "主图目的": brief["purpose"],
        "主文案": brief["headline"],
        "辅助文案": brief["sub"],
        "角标/信任点": brief["badge"],
        "画面描述词": brief["visual"],
        "设计备注": brief["note"],
        "状态": "待制作",
        "生成时间": now_ms,
    }


def timestamp_ms(value: datetime) -> int:
    return int(datetime(value.year, value.month, value.day).timestamp() * 1000)


def chunks(items: list[dict[str, Any]], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]
