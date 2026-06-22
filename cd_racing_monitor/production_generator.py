from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

from .config import AppConfig
from .feishu import FeishuClient
from .normalizer import as_number, as_text
from .platform_requirements import read_platform_requirements
from .production_100_links import PRODUCT_TABLE, RISK_TABLE, TASK_TABLE, THEME_TABLE
from .schema import table_id, table_name


THEME_LIBRARY = [
    {
        "name": "日常口腔护理",
        "style": "清爽专业",
        "audience": "重视日常口腔清洁与护理的人群",
        "scene": "早晚刷牙后、饭后、出门前的日常护理",
        "pain": "口腔护理步骤容易被忽略，日常清洁后缺少便捷护理补充",
        "angle": "按说明书用于日常口腔护理场景，突出规格、用法和清爽体验",
        "trust": "以注册证/说明书/标签信息为准，不夸大功效",
        "promo": "基础价格带测试",
    },
    {
        "name": "正畸人群护理",
        "style": "干净理性",
        "audience": "牙齿矫正、佩戴牙套或保持器的人群",
        "scene": "正畸期间的居家口腔护理",
        "pain": "正畸期间口腔清洁步骤更多，需要清晰、方便的护理用品",
        "angle": "强调正畸护理场景和便捷含漱，不使用治疗承诺",
        "trust": "规格、成分、适用范围清晰展示",
        "promo": "组合装价格测试",
    },
    {
        "name": "家庭备用护理",
        "style": "家庭实用",
        "audience": "家庭日常护理用品采购人群",
        "scene": "家庭洗漱台、收纳柜、家庭备用场景",
        "pain": "家庭护理用品需要看得懂、放得住、用得方便",
        "angle": "突出家庭备用、规格清楚、使用提醒明确",
        "trust": "真实产品包装、资质文件夹和说明信息支撑",
        "promo": "多瓶装优惠测试",
    },
    {
        "name": "饭后清爽护理",
        "style": "轻快生活",
        "audience": "上班族、外出就餐后关注口腔状态的人群",
        "scene": "饭后、午休、办公室洗漱区",
        "pain": "饭后口腔状态不够清爽，需要简单护理动作",
        "angle": "表达饭后清爽护理体验，避免疾病和疗效表达",
        "trust": "成分和规格明确，按说明合理使用",
        "promo": "单瓶低门槛测试",
    },
    {
        "name": "出行便携护理",
        "style": "轻便场景",
        "audience": "出差、旅行、通勤人群",
        "scene": "行李箱、洗漱包、办公室抽屉",
        "pain": "外出时口腔护理用品需要便于携带和识别",
        "angle": "强调出行收纳、便捷使用和规格信息",
        "trust": "展示真实瓶身、包装和使用步骤",
        "promo": "单瓶/多瓶便携组合测试",
    },
    {
        "name": "成分信息透明",
        "style": "成分科普",
        "audience": "购买前会看成分和说明的人群",
        "scene": "详情页成分说明、主图卖点拆解",
        "pain": "用户担心产品信息不透明，不知道如何判断是否适合",
        "angle": "展示成分、规格、适用范围和说明书提醒",
        "trust": "不做功效承诺，以资料信息建立信任",
        "promo": "信任背书优先测试",
    },
    {
        "name": "使用步骤清晰",
        "style": "教程说明",
        "audience": "第一次购买或不熟悉含漱类产品的人群",
        "scene": "使用教程图、详情页步骤说明、短视频口播",
        "pain": "用户不知道什么时候用、怎么用、注意什么",
        "angle": "用步骤图降低理解成本，强调按说明书合理使用",
        "trust": "步骤清楚、注意事项清楚、资质真实",
        "promo": "教程型链接测试",
    },
    {
        "name": "规格组合清楚",
        "style": "电商转化",
        "audience": "在单瓶、2瓶、3瓶之间比较的用户",
        "scene": "SKU选择、价格对比、囤货选择",
        "pain": "SKU数量和价格不清楚会影响下单决策",
        "angle": "清楚展示1瓶、2瓶、3瓶区别，避免低价误导",
        "trust": "规格、数量、价格带一致，减少误解",
        "promo": "SKU组合转化测试",
    },
    {
        "name": "资质安心说明",
        "style": "稳重可信",
        "audience": "重视资质、说明书和正规信息的用户",
        "scene": "详情页资质模块、主图信任角标",
        "pain": "医疗器械相关产品购买前需要确认资质和适用边界",
        "angle": "展示资质与说明书信息，避免医生/机构背书",
        "trust": "注册证/资质图真实展示，宣传不超范围",
        "promo": "信任转化测试",
    },
    {
        "name": "温和口感体验",
        "style": "柔和亲近",
        "audience": "关注使用口感和日常体验的人群",
        "scene": "浴室、洗漱台、晨间护理、晚间护理",
        "pain": "护理用品如果口感不友好，容易难以坚持使用",
        "angle": "突出香橙香精等体验信息，避免疗效夸张",
        "trust": "成分信息和使用体验表达分开，不做保证",
        "promo": "体验感方向测试",
    },
]


ASSET_VARIANTS: dict[str, list[dict[str, str]]] = {
    "方图": [
        {
            "purpose": "首屏产品识别",
            "main": "含氟口腔含漱液",
            "sub": "用产品核心属性做首屏点击点，补充“二类医疗器械/资质可查/200ml规格”等背书角标，真实瓶身与包装正面展示。",
            "visual": "电商主图构图，产品居中偏大，浅色干净背景；右侧放主标题，旁边点缀2-3个小图标卖点：含氟配方、200ml/瓶、资质信息可查。底部可放简洁规格条。",
        },
        {
            "purpose": "场景痛点引入",
            "main": "饭后口腔不清爽？",
            "sub": "用消费者日常痛点引导点击，解释为什么在饭后、通勤、办公场景使用含漱护理，不出现疗效承诺。",
            "visual": "洗漱台或办公室洗手区场景，产品放在前景；画面用小图标表达饭后、出门前、办公午休三个使用场景，配少量信息卡说明“口腔护理多一步”。",
        },
        {
            "purpose": "规格与SKU说明",
            "main": "1瓶/2瓶/3瓶可选",
            "sub": "把购买选择说清楚，突出家庭备用、周期使用、组合更清楚等购买理由，减少SKU疑虑，避免低价误导。",
            "visual": "产品瓶身与1瓶、2瓶、3瓶组合阶梯式陈列；旁边用对比信息块说明“尝鲜装/家庭备用/多人共享”等场景，不出现虚假优惠和最低价承诺。",
        },
        {
            "purpose": "使用步骤说明",
            "main": "含漱护理更方便",
            "sub": "把买点落在使用便利性上，说明使用门槛低、步骤清楚、适合日常场景，用步骤图表达护理流程，强调阅读说明书和合理使用。",
            "visual": "三步流程信息图：取用、含漱、收纳；每一步用图标和短标签表达，产品主体在左侧，右侧是流程卡片，整体像专业电商卖点图。",
        },
        {
            "purpose": "资质与信任背书",
            "main": "资质信息清楚可查",
            "sub": "用信任买点降低决策顾虑，表达医疗器械相关产品购买前应看资质、说明书、标签信息；展示真实资质来源，不使用专家或机构背书。",
            "visual": "产品与资质文件局部排版，加入“资质可查、说明书为准、规范使用”三个图标角标；文件内容可虚化或用占位信息，整体专业可信。",
        },
    ],
    "长图": [
        {
            "purpose": "竖版首屏",
            "main": "口腔护理多一步",
            "sub": "产品大图+核心场景，一屏看懂购买理由。",
            "visual": "竖版海报，上半部分场景，下半部分产品和卖点，留白充足。",
        },
        {
            "purpose": "人群场景",
            "main": "正畸/饭后/居家都好放",
            "sub": "用真实生活场景表达适用场景，不制造焦虑。",
            "visual": "竖版生活方式图，人物只作场景辅助，产品保持清晰露出。",
        },
        {
            "purpose": "卖点拆解",
            "main": "含氟配方 200ml/瓶",
            "sub": "信息模块化展示核心卖点，避免堆字。",
            "visual": "竖版信息卡布局，3个卖点模块，配产品图和浅色背景。",
        },
        {
            "purpose": "步骤教程",
            "main": "倒出-含漱-吐出",
            "sub": "用步骤型买点承接内容流。",
            "visual": "竖版教程图，步骤编号清晰，动作示意克制，不出现口腔病灶画面。",
        },
        {
            "purpose": "信任收口",
            "main": "规格资质看得明白",
            "sub": "资质、规格、SKU、售后信息统一呈现。",
            "visual": "竖版信任背书图，产品、资质、规格、品牌说明分层排版。",
        },
    ],
    "详情页": [
        {
            "purpose": "痛点场景",
            "main": "日常口腔护理，先看真实使用场景",
            "sub": "用温和场景引入，不夸大问题。",
            "visual": "详情页第一屏，生活场景+产品完整露出。",
        },
        {
            "purpose": "产品方案",
            "main": "口腔含漱液，护理步骤更清楚",
            "sub": "承接首屏，说明产品定位。",
            "visual": "产品解决方案模块，瓶身、包装、规格清楚。",
        },
        {
            "purpose": "核心信息",
            "main": "成分与规格清楚展示",
            "sub": "只展示真实可核验信息。",
            "visual": "成分/规格信息模块，文字清晰但不拥挤。",
        },
        {
            "purpose": "使用方法",
            "main": "按说明合理使用",
            "sub": "步骤化表达，降低理解成本。",
            "visual": "使用步骤模块，图标+简短说明。",
        },
        {
            "purpose": "资质信任",
            "main": "商品信息以资质与说明书为准",
            "sub": "展示真实资质来源，不做背书夸大。",
            "visual": "资质文件与产品同屏，排版专业。",
        },
        {
            "purpose": "品牌背书",
            "main": "恒品日常护理用品",
            "sub": "收束详情页，提醒按说明使用。",
            "visual": "品牌简介模块，与前面详情页风格连续。",
        },
    ],
    "笔记图": [
        {
            "purpose": "种草封面",
            "main": "饭后口腔护理好物",
            "sub": "真实分享感，避免功效承诺。",
            "visual": "小红书笔记封面风格，产品+洗漱台+手写感标签。",
        },
        {
            "purpose": "场景分享",
            "main": "出门前含漱一下",
            "sub": "强调使用时机和便利感。",
            "visual": "生活方式拼图，产品、包包、洗漱台细节组合。",
        },
        {
            "purpose": "规格选择",
            "main": "家庭备用选几瓶？",
            "sub": "按使用频率选择，信息透明。",
            "visual": "笔记型信息图，SKU组合对比，字体清楚可读。",
        },
    ],
    "基础图": [
        {
            "purpose": "白底图",
            "main": "",
            "sub": "真实产品白底展示。",
            "visual": "纯白背景，产品完整居中，无营销文字。",
        },
        {
            "purpose": "透明底图",
            "main": "",
            "sub": "方便后续组合设计。",
            "visual": "透明背景或可抠图效果，产品边缘干净。",
        },
    ],
}


@dataclass(frozen=True)
class ProductionGenerationResult:
    product_count: int
    created_themes: int
    created_tasks: int
    created_risks: int
    updated_tasks: int = 0


class ProductionGenerator:
    def __init__(self, config: AppConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.client = FeishuClient(config.feishu)

    def generate(self, limit: int = 5) -> ProductionGenerationResult:
        table_ids = self._table_ids()
        product_records = self.client.list_records(table_ids[PRODUCT_TABLE], page_size=100)
        products = [row for row in product_records if as_text(row.get("fields", {}).get("款式编码"))]
        products = products[:limit]

        existing_theme_ids = {
            as_text(row.get("fields", {}).get("主题ID"))
            for row in self.client.list_records(table_ids[THEME_TABLE], page_size=500)
        }
        existing_task_ids = {
            as_text(row.get("fields", {}).get("任务ID"))
            for row in self.client.list_records(table_ids[TASK_TABLE], page_size=500)
        }
        existing_risk_ids = {
            as_text(row.get("fields", {}).get("风险ID"))
            for row in self.client.list_records(table_ids[RISK_TABLE], page_size=500)
        }

        platform_requirements = read_platform_requirements()
        theme_rows: list[dict[str, Any]] = []
        task_rows: list[dict[str, Any]] = []
        risk_rows: list[dict[str, Any]] = []

        today = int(datetime.now().timestamp() * 1000)
        for product in products:
            fields = product.get("fields", {})
            product_id = as_text(fields.get("款式编码"))
            product_name = as_text(fields.get("标准产品名称"))
            title = as_text(fields.get("商品标题（埋词）")) or self._title(fields)
            platform = as_text(fields.get("平台")) or "全平台"
            target_count = int(as_number(fields.get("每日目标链接数")) or 10)
            sku_count = int(as_number(fields.get("SKU数量")) or 0)

            for index, theme in enumerate(THEME_LIBRARY[:target_count], start=1):
                theme_id = f"{product_id}-T{index:02d}"
                if theme_id not in existing_theme_ids:
                    theme_rows.append(
                        {
                            "主题ID": theme_id,
                            "款式编码": product_id,
                            "标准产品名称": product_name,
                            "商品标题（埋词）": title,
                            "平台": platform,
                            "链接序号": index,
                            "主题名称": theme["name"],
                            "主题风格": theme["style"],
                            "目标人群": theme["audience"],
                            "使用场景": theme["scene"],
                            "核心痛点": theme["pain"],
                            "核心卖点": theme["angle"],
                            "信任背书": theme["trust"],
                            "价格/促销方向": theme["promo"],
                            "需要生成方图数": 5,
                            "需要生成长图数": 5,
                            "需要生成详情页数": 6,
                            "需要生成笔记图数": 3,
                            "需要生成视频数": 1,
                            "SKU图数量": sku_count,
                            "基础图数量": 2,
                            "场景图数量": 1,
                            "资质图数量": 1,
                            "主题合规注意事项": self._compliance_note(fields, platform_requirements),
                            "人工确认状态": "待确认",
                            "计划状态": "待拆任务",
                            "生成日期": today,
                        }
                    )

                task_rows.extend(
                    self._task_rows(
                        fields=fields,
                        theme_id=theme_id,
                        theme=theme,
                        link_index=index,
                        sku_count=sku_count,
                        existing_task_ids=existing_task_ids,
                    )
                )

            risk_rows.extend(
                self._risk_rows(
                    fields=fields,
                    existing_risk_ids=existing_risk_ids,
                    timestamp=today,
                )
            )

        created_themes = self._batch_create(table_ids[THEME_TABLE], theme_rows)
        created_tasks = self._batch_create(table_ids[TASK_TABLE], task_rows)
        created_risks = self._batch_create(table_ids[RISK_TABLE], risk_rows)
        return ProductionGenerationResult(
            product_count=len(products),
            created_themes=created_themes,
            created_tasks=created_tasks,
            created_risks=created_risks,
        )

    def refresh_tasks(self) -> int:
        table_ids = self._table_ids()
        products = {
            as_text(row.get("fields", {}).get("款式编码")): row.get("fields", {})
            for row in self.client.list_records(table_ids[PRODUCT_TABLE], page_size=500)
            if as_text(row.get("fields", {}).get("款式编码"))
        }
        themes = {
            as_text(row.get("fields", {}).get("主题ID")): self._theme_from_fields(row.get("fields", {}))
            for row in self.client.list_records(table_ids[THEME_TABLE], page_size=500)
            if as_text(row.get("fields", {}).get("主题ID"))
        }
        task_updates: list[dict[str, Any]] = []
        for row in self.client.list_records(table_ids[TASK_TABLE], page_size=500):
            fields = row.get("fields", {})
            record_id = as_text(row.get("record_id"))
            product_id = as_text(fields.get("款式编码"))
            theme_id = as_text(fields.get("主题ID"))
            asset_type = as_text(fields.get("素材类型"))
            seq = int(as_number(fields.get("素材序号")) or 1)
            product_fields = products.get(product_id)
            theme = themes.get(theme_id)
            if not record_id or not product_fields or not theme:
                continue
            task_updates.append(
                {
                    "record_id": record_id,
                    "fields": self._task_content_fields(
                        fields=product_fields,
                        theme_id=theme_id,
                        theme=theme,
                        link_index=int(as_number(fields.get("链接序号")) or 1),
                        asset_type=asset_type,
                        seq=seq,
                        size=as_text(fields.get("图片尺寸")),
                        task_id=as_text(fields.get("任务ID")),
                    ),
                }
            )
        updated = 0
        for index in range(0, len(task_updates), 100):
            updated += self.client.update_records_batch(table_ids[TASK_TABLE], task_updates[index : index + 100])
        return updated

    def _table_ids(self) -> dict[str, str]:
        existing = {table_name(item): table_id(item) for item in self.client.list_tables()}
        required = (PRODUCT_TABLE, THEME_TABLE, TASK_TABLE, RISK_TABLE)
        missing = [name for name in required if not existing.get(name)]
        if missing:
            raise RuntimeError(f"Missing production tables: {', '.join(missing)}")
        return {name: existing[name] for name in required}

    def _title(self, fields: dict[str, Any]) -> str:
        product_name = as_text(fields.get("标准产品名称"))
        spec = as_text(fields.get("规格/型号/数量"))
        return f"{product_name} {spec} 日常口腔护理含漱液".strip()

    def _compliance_note(self, fields: dict[str, Any], platform_requirements: str) -> str:
        notes = [
            "按本地平台要求取严审核，避免医疗化、治疗承诺、绝对化和低价误导。",
            "涉及医疗器械/口腔护理边界时，以注册证、说明书、标签和资质图为准。",
            "消费者页面优先使用日常护理、按说明使用、信息真实清楚等稳妥表达。",
        ]
        if "治疗" in as_text(fields.get("可宣传范围")) or "疼痛" in as_text(fields.get("可宣传范围")):
            notes.append("原始适用范围含治疗/疼痛等高风险词，生成文案时需优先改写为说明书适用范围或人工确认表达。")
        if not platform_requirements:
            notes.append("未读取到本地平台要求文件，请先检查 E:\\CD级素材\\平台要求。")
        return "\n".join(notes)

    def _task_rows(
        self,
        fields: dict[str, Any],
        theme_id: str,
        theme: dict[str, str],
        link_index: int,
        sku_count: int,
        existing_task_ids: set[str],
    ) -> list[dict[str, Any]]:
        specs: list[tuple[str, int, str]] = [
            ("方图", 5, "1440x1440"),
            ("长图", 5, "1440x1920"),
            ("详情页", 6, "宽1440，单张长度不超过2880"),
            ("笔记图", 3, "1440x1440"),
            ("产品视频", 1, "15秒左右，建议9:16"),
            ("基础图", 2, "1440x1440，白底图/透明底图"),
            ("场景图", 1, "1440x1440"),
            ("资质图", 1, "真实资质文件排版"),
        ]
        if sku_count:
            specs.append(("SKU图", sku_count, "1440x1440"))

        product_id = as_text(fields.get("款式编码"))
        product_name = as_text(fields.get("标准产品名称"))
        title = as_text(fields.get("商品标题（埋词）")) or self._title(fields)
        platform = as_text(fields.get("平台")) or "全平台"
        output: list[dict[str, Any]] = []

        for asset_type, count, size in specs:
            for seq in range(1, count + 1):
                task_id = f"{theme_id}-{self._task_type_code(asset_type)}{seq:02d}"
                if task_id in existing_task_ids:
                    continue
                output.append(
                    {
                        "任务ID": task_id,
                        "主题ID": theme_id,
                        "款式编码": product_id,
                        "标准产品名称": product_name,
                        "商品标题（埋词）": title,
                        "平台": platform,
                        "链接序号": link_index,
                        "素材类型": asset_type,
                        "素材序号": seq,
                        "素材规格": f"{asset_type}{seq}",
                        "图片尺寸": size,
                        **self._task_content_fields(
                            fields=fields,
                            theme_id=theme_id,
                            theme=theme,
                            link_index=link_index,
                            asset_type=asset_type,
                            seq=seq,
                            size=size,
                            task_id=task_id,
                        ),
                        "关联SKU": as_text(fields.get("SKU明细")) if asset_type == "SKU图" else "",
                        "引用资质": as_text(fields.get("注册证/资质文件夹")) if asset_type in {"资质图", "详情页"} else "",
                        "产品参考图路径": as_text(fields.get("产品实拍文件夹")),
                        "场景参考图路径": "",
                        "匹配参考素材ID": "",
                        "参考素材使用方式": "本次测试暂不使用参考素材池，先按主题方向和产品实拍图生成。",
                        "生图提示词": self._image_prompt(asset_type, theme, fields, size),
                        "ChatGPT对话批次": self._chat_batch(asset_type),
                        "建议单轮生成数量": 1 if asset_type in {"详情页", "SKU图", "资质图", "产品视频"} else 2,
                        "输出文件名": f"{task_id}.png" if asset_type != "产品视频" else f"{task_id}.mp4",
                        "输出文件夹": f"{product_id}\\{theme_id}\\{asset_type}",
                        "下载文件路径": "",
                        "合规初检状态": "待人工确认",
                        "人工审核状态": "待审核",
                        "人工质检结论": "",
                        "制作状态": "待制作",
                        "上架包状态": "未打包",
                        "负责人": as_text(fields.get("负责人")),
                    }
                )
        return output

    def _task_content_fields(
        self,
        fields: dict[str, Any],
        theme_id: str,
        theme: dict[str, str],
        link_index: int,
        asset_type: str,
        seq: int,
        size: str,
        task_id: str,
    ) -> dict[str, Any]:
        return {
            "主文案": self._main_copy(asset_type, seq, theme, fields),
            "辅助文案": self._sub_copy(asset_type, seq, theme, fields),
            "画面描述": self._visual_prompt(asset_type, seq, theme, fields),
            "设计要求": self._design_requirement(asset_type, seq),
            "详情页衔接要求": self._detail_flow(seq) if asset_type == "详情页" else "",
            "品牌背书模块": "恒品关注日常生活与家庭护理场景，商品信息以页面展示、产品标签、说明书及相关资质文件为准，请按说明合理使用。"
            if asset_type == "详情页" and seq == 6
            else "",
            "口播脚本": self._video_script(theme, fields) if asset_type == "产品视频" else "",
            "生图提示词": self._image_prompt(asset_type, seq, theme, fields, size),
        }

    def _risk_rows(self, fields: dict[str, Any], existing_risk_ids: set[str], timestamp: int) -> list[dict[str, Any]]:
        product_id = as_text(fields.get("款式编码"))
        product_name = as_text(fields.get("标准产品名称"))
        platform = as_text(fields.get("平台")) or "全平台"
        source = as_text(fields.get("基础卖点")) + "\n" + as_text(fields.get("可宣传范围"))
        risky_words = ["治疗", "疼痛", "炎症", "溃疡", "手术", "辅助治疗"]
        rows: list[dict[str, Any]] = []
        for word in risky_words:
            if word not in source:
                continue
            risk_id = f"{product_id}-RISK-{word}"
            if risk_id in existing_risk_ids:
                continue
            rows.append(
                {
                    "风险ID": risk_id,
                    "任务ID": "",
                    "款式编码": product_id,
                    "标准产品名称": product_name,
                    "商品标题（埋词）": self._title(fields),
                    "平台": platform,
                    "素材类型": "生成前产品资料",
                    "检查对象": "基础卖点/可宣传范围",
                    "命中内容": word,
                    "风险类型": "医疗化/适用范围高风险表达",
                    "风险等级": "P1人工确认",
                    "风险说明": "原始资料中包含医疗器械适用范围相关词，生成消费者可见文案时必须依据资质和说明书，不得扩写为疗效承诺。",
                    "建议替代表达": "按说明书适用范围、日常口腔护理、物理遮蔽保护层、请按说明合理使用。",
                    "是否阻断生产": "否，需人工确认表达边界",
                    "人工处理意见": "",
                    "复检状态": "待复检",
                    "检查时间": timestamp,
                }
            )
        return rows

    def _batch_create(self, table_id_value: str, rows: list[dict[str, Any]]) -> int:
        created = 0
        for index in range(0, len(rows), 100):
            created += self.client.create_records_batch(table_id_value, rows[index : index + 100])
        return created

    @staticmethod
    def _task_type_code(asset_type: str) -> str:
        return {
            "方图": "SQ",
            "长图": "VT",
            "详情页": "DT",
            "笔记图": "NT",
            "产品视频": "VD",
            "基础图": "BS",
            "场景图": "SC",
            "资质图": "QC",
            "SKU图": "SKU",
        }.get(asset_type, "AS")

    @staticmethod
    def _chat_batch(asset_type: str) -> str:
        return {
            "方图": "A",
            "长图": "B",
            "详情页": "C",
            "SKU图": "D",
            "基础图": "E",
            "场景图": "F",
            "笔记图": "G",
            "资质图": "H",
            "产品视频": "V",
        }.get(asset_type, "A")

    def _theme_from_fields(self, fields: dict[str, Any]) -> dict[str, str]:
        return {
            "name": as_text(fields.get("主题名称")),
            "style": as_text(fields.get("主题风格")),
            "audience": as_text(fields.get("目标人群")),
            "scene": as_text(fields.get("使用场景")),
            "pain": as_text(fields.get("核心痛点")),
            "angle": as_text(fields.get("核心卖点")),
            "trust": as_text(fields.get("信任背书")),
            "promo": as_text(fields.get("价格/促销方向")),
        }

    def _variant(self, asset_type: str, seq: int) -> dict[str, str]:
        variants = ASSET_VARIANTS.get(asset_type, [])
        if variants:
            return variants[min(max(seq - 1, 0), len(variants) - 1)]
        return {
            "purpose": asset_type,
            "main": "{theme_name}",
            "sub": "{angle}",
            "visual": "{asset_type}，围绕{scene}，真实展示产品。",
        }

    def _format_variant(self, template: str, asset_type: str, theme: dict[str, str], fields: dict[str, Any]) -> str:
        return template.format(
            asset_type=asset_type,
            theme_name=theme.get("name", ""),
            audience=theme.get("audience", ""),
            scene=theme.get("scene", ""),
            angle=theme.get("angle", ""),
            product_name=as_text(fields.get("标准产品名称")),
            spec=as_text(fields.get("规格/型号/数量")),
        )

    def _main_copy(self, asset_type: str, seq: int, theme: dict[str, str], fields: dict[str, Any]) -> str:
        if asset_type == "资质图":
            return "商品信息以注册证、说明书、标签及页面展示为准"
        if asset_type == "SKU图":
            return f"SKU {seq}：规格清楚，按需选择"
        if asset_type == "产品视频":
            return f"{theme['name']}口播讲解"
        variant = self._variant(asset_type, seq)
        return self._format_variant(variant["main"], asset_type, theme, fields)

    def _sub_copy(self, asset_type: str, seq: int, theme: dict[str, str], fields: dict[str, Any]) -> str:
        if asset_type == "资质图":
            return "仅使用真实资质文件排版，不生成虚构证照信息。"
        if asset_type == "SKU图":
            return f"展示第 {seq} 个 SKU 或组合，数量、价格和规格必须与上架信息一致。"
        if asset_type == "产品视频":
            return "15秒左右，开头2秒露出产品和主题，不说疗效承诺。"
        variant = self._variant(asset_type, seq)
        return self._format_variant(variant["sub"], asset_type, theme, fields)

    def _visual_prompt(self, asset_type: str, seq: int, theme: dict[str, str], fields: dict[str, Any]) -> str:
        if asset_type == "SKU图":
            return f"SKU图第{seq}张，突出对应组合规格，产品和数量清楚，背景干净，避免价格误导。"
        if asset_type == "产品视频":
            return f"口播视频，{theme['style']}风格，产品始终清楚露出，围绕{theme['scene']}讲解。"
        variant = self._variant(asset_type, seq)
        return self._format_variant(variant["visual"], asset_type, theme, fields)

    def _design_requirement(self, asset_type: str, seq: int) -> str:
        purpose = self._variant(asset_type, seq).get("purpose", asset_type)
        return f"本图目的：{purpose}。画面清晰、产品真实突出、信息层级明确，不使用夸张对比和医疗化承诺。"

    def _image_prompt(self, asset_type: str, seq: int, theme: dict[str, str], fields: dict[str, Any], size: str) -> str:
        variant = self._variant(asset_type, seq)
        purpose = variant.get("purpose", asset_type)
        visual = self._visual_prompt(asset_type, seq, theme, fields)
        main = self._main_copy(asset_type, seq, theme, fields)
        sub = self._sub_copy(asset_type, seq, theme, fields)
        visible_text_rule = (
            "画面可见文字只允许使用主标题；辅助文字仅用于理解画面和构图，不得作为文字写入图片。"
            "画面可以使用短标签、图标角标、信息卡和背书徽章来承载卖点，但每个标签应控制在2-6个字，不要把辅助文案整句写进图片。"
            "优先用场景、产品摆放、图标和层级排版表达购买理由。"
        )
        ecommerce_layout_rule = (
            "请按电商主图思路设计：产品主体必须最大最清晰；主标题负责点击；"
            "画面需补充2-3个短卖点或背书角标，例如含氟配方、200ml规格、资质可查、按说明使用；"
            "同时解释该场景为什么需要这个产品、产品解决什么护理需求、给用户带来什么选择好处。"
            "如使用“二类医疗器械”等背书，只能作为资质信息角标表达，并保持“信息以资质/说明书为准”的稳妥口径。"
        )
        return (
            f"请基于上传的产品参考图生成{asset_type}第{seq}张，图片目的：{purpose}，尺寸要求：{size}。"
            f"产品：{as_text(fields.get('标准产品名称'))}；规格：{as_text(fields.get('规格/型号/数量'))}；"
            f"主题：{theme['name']}；目标人群：{theme['audience']}；使用场景：{theme['scene']}。"
            f"画面方向：{visual}。"
            f"画面文字主标题：{main}。辅助文字参考：{sub}。{visible_text_rule}{ecommerce_layout_rule}"
            "要求画面真实清晰，产品主体完整突出，避免医疗化治疗承诺、绝对化词汇、夸张前后对比、医生专家背书、二维码和外部联系方式。"
            "文案只使用稳妥表达：按说明合理使用、日常口腔护理、信息以说明书和资质文件为准。"
        )

    @staticmethod
    def _detail_flow(seq: int) -> str:
        flows = {
            1: "首屏：痛点场景与产品整体露出，底部自然引出解决方案。",
            2: "产品方案：承接首屏场景，说明日常护理定位。",
            3: "核心信息：展示规格、成分或使用场景，避免疗效承诺。",
            4: "使用方法：步骤清楚，提醒按说明合理使用。",
            5: "信任与资质：展示真实资质/说明书信息，不使用专家背书。",
            6: "品牌背书：收束页面，风格与前面模块保持一致。",
        }
        return flows.get(seq, "与上一张视觉和文案自然衔接。")

    @staticmethod
    def _video_script(theme: dict[str, str], fields: dict[str, Any]) -> str:
        return (
            f"这是一款{as_text(fields.get('标准产品名称'))}。"
            f"今天用{theme['name']}这个场景来介绍，适合{theme['audience']}关注。"
            "页面信息以说明书、标签和资质文件为准，请按说明合理使用。"
            "选择规格时看清瓶数和数量，按自己的使用需求选择。"
        )
