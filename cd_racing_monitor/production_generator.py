from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

from .config import AppConfig
from .feishu import FeishuClient
from .normalizer import as_number, as_text
from .platform_requirements import read_platform_requirements
from .production_100_links import ANALYSIS_TABLE, PRODUCT_TABLE, RISK_TABLE, TASK_TABLE, THEME_TABLE
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
        "visual_style": "天猫清爽医护风",
        "palette": "白色、浅薄荷绿、浅蓝点缀",
        "composition": "中心产品大图+右侧卖点信息卡+底部规格条",
        "texture": "干净留白、轻医疗感、高清棚拍",
    },
    {
        "name": "正畸人群护理",
        "style": "干净理性",
        "audience": "牙齿矫正、佩戴牙套或保持器的人群",
        "scene": "正畸期间的居家口腔护理",
        "pain": "正畸期间口腔清洁步骤更多，需要清晰、方便的护理用品",
        "angle": "强调正畸护理场景和便捷护理动作，不使用治疗承诺",
        "trust": "规格、成分、适用范围清晰展示",
        "promo": "组合装价格测试",
        "visual_style": "正畸护理专业风",
        "palette": "白色、牙釉质浅米色、金属银灰点缀",
        "composition": "产品前景+牙套/保持器场景道具+步骤型信息卡",
        "texture": "理性克制、线条清晰、轻科普感",
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
        "visual_style": "家庭生活温和风",
        "palette": "暖白、浅木色、柔和橙色点缀",
        "composition": "洗漱台家庭场景+多瓶组合陈列+家庭备用标签",
        "texture": "温暖真实、居家收纳感、自然光",
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
        "visual_style": "办公室轻快风",
        "palette": "白色、浅灰、清爽柑橘橙点缀",
        "composition": "办公桌/午休洗手台场景+产品特写+痛点问句",
        "texture": "轻快明亮、年轻化、内容流友好",
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
        "visual_style": "出行便携场景风",
        "palette": "雾白、浅卡其、旅行蓝点缀",
        "composition": "洗漱包/行李箱局部+产品斜向摆放+便携场景图标",
        "texture": "旅行收纳感、轻户外、干净不杂乱",
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
        "visual_style": "成分透明科普风",
        "palette": "白色、浅青绿、实验室透明感点缀",
        "composition": "产品+成分信息模块+简洁分子/水滴图标",
        "texture": "清透、专业、信息可读性强",
    },
    {
        "name": "使用步骤清晰",
        "style": "教程说明",
        "audience": "第一次购买或不熟悉该类口腔护理产品的人群",
        "scene": "使用教程图、详情页步骤说明、短视频口播",
        "pain": "用户不知道什么时候用、怎么用、注意什么",
        "angle": "用步骤图降低理解成本，强调按说明书合理使用",
        "trust": "步骤清楚、注意事项清楚、资质真实",
        "promo": "教程型链接测试",
        "visual_style": "教程步骤插画风",
        "palette": "白色、浅蓝、柔和绿色",
        "composition": "三步流程横向或环形排列+产品固定在画面一侧",
        "texture": "说明书友好、图标化、步骤清楚",
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
        "visual_style": "电商SKU转化风",
        "palette": "白色、浅灰、价格标签红少量点缀",
        "composition": "不同SKU组合阶梯陈列+SKU卡片+购买选择对比",
        "texture": "转化导向、信息密度中等、货架感清楚",
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
        "visual_style": "资质背书稳重风",
        "palette": "白色、深蓝、银灰点缀",
        "composition": "产品+资质文件局部+背书徽章矩阵",
        "texture": "稳重可信、证照展示感、商务清晰",
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
        "visual_style": "香橙清新体验风",
        "palette": "白色、浅橙、清透水感蓝",
        "composition": "产品+橙色清新元素+水感背景+体验短标签",
        "texture": "清新水润、轻生活方式、柔和不医疗化",
    },
]

THEME_BY_NAME = {theme["name"]: theme for theme in THEME_LIBRARY}

DEFAULT_VISUAL_SYSTEMS = [
    {
        "visual_style": "天猫清爽医护风",
        "palette": "白色、浅薄荷绿、浅蓝点缀",
        "composition": "中心产品大图+右侧卖点信息卡+底部规格条",
        "texture": "干净留白、轻医疗感、高清棚拍",
    },
    {
        "visual_style": "专业原理科普风",
        "palette": "白色、浅蓝、银灰点缀",
        "composition": "产品前景+原理信息卡+局部放大示意",
        "texture": "理性克制、线条清晰、轻科普感",
    },
    {
        "visual_style": "家庭生活温和风",
        "palette": "暖白、浅木色、柔和橙色点缀",
        "composition": "居家洗漱台场景+产品陈列+人群提醒卡",
        "texture": "温暖真实、居家收纳感、自然光",
    },
    {
        "visual_style": "症状关注稳妥风",
        "palette": "白色、浅灰、低饱和红色点缀",
        "composition": "产品大图+困扰提示卡+说明书口径角标",
        "texture": "专业可信、不过度刺激、不制造焦虑",
    },
    {
        "visual_style": "成分透明科普风",
        "palette": "白色、浅青绿、实验室透明感点缀",
        "composition": "产品+成分信息模块+简洁分子/水滴图标",
        "texture": "清透、专业、信息可读性强",
    },
    {
        "visual_style": "教程步骤插画风",
        "palette": "白色、浅蓝、柔和绿色",
        "composition": "三步流程横向或环形排列+产品固定在画面一侧",
        "texture": "说明书友好、图标化、步骤清楚",
    },
    {
        "visual_style": "电商SKU转化风",
        "palette": "白色、浅灰、价格标签红少量点缀",
        "composition": "不同SKU组合阶梯陈列+SKU卡片+购买选择对比",
        "texture": "转化导向、信息密度中等、货架感清楚",
    },
    {
        "visual_style": "资质背书稳重风",
        "palette": "白色、深蓝、银灰点缀",
        "composition": "产品+资质文件局部+背书徽章矩阵",
        "texture": "稳重可信、证照展示感、商务清晰",
    },
    {
        "visual_style": "薄荷清新体验风",
        "palette": "白色、薄荷绿、清透水感蓝",
        "composition": "产品+清新口感元素+体验短标签",
        "texture": "清新水润、轻生活方式、柔和不医疗化",
    },
    {
        "visual_style": "复购囤货清楚风",
        "palette": "白色、浅灰、温和黄色点缀",
        "composition": "多SKU陈列+购买理由卡+家庭备用场景",
        "texture": "货架清楚、选择成本低、信息不过载",
    },
]


ASSET_VARIANTS: dict[str, list[dict[str, str]]] = {
    "方图": [
        {
            "purpose": "首屏产品识别",
            "main": "{hero}",
            "sub": "用当前产品的核心卖点做首屏点击点，补充“二类医疗器械/资质可查/{spec}”等背书角标，真实产品与包装正面展示。",
            "visual": "电商主图构图，产品居中偏大，浅色干净背景；右侧放主标题，旁边点缀2-3个小图标卖点：核心信息、规格信息、资质信息可查。底部可放简洁规格条。",
        },
        {
            "purpose": "场景痛点引入",
            "main": "{buy_point}",
            "sub": "用消费者真实买点引导点击，解释为什么在当前场景选择这个产品，不出现疗效承诺。",
            "visual": "洗漱台、居家护理或办公室洗手区场景，产品放在前景；画面用小图标表达使用场景，配少量信息卡说明“口腔护理多一步”。",
        },
        {
            "purpose": "规格与SKU说明",
            "main": "{sku_detail}可选",
            "sub": "把购买选择说清楚，突出家庭备用、周期使用、组合更清楚等购买理由，减少SKU疑虑，避免低价误导。",
            "visual": "产品与SKU组合阶梯式陈列；旁边用对比信息块说明“尝鲜装/家庭备用/多人共享”等场景，不出现虚假优惠和最低价承诺。",
        },
        {
            "purpose": "使用步骤说明",
            "main": "使用步骤更清楚",
            "sub": "把买点落在使用便利性上，说明步骤清楚、适合当前产品场景，用步骤图表达护理流程，强调阅读说明书和合理使用。",
            "visual": "三步流程信息图：取用、按说明使用、收纳；每一步用图标和短标签表达，产品主体在左侧，右侧是流程卡片，整体像专业电商卖点图。",
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
            "main": "{hero}",
            "sub": "{product_name}大图+核心场景，一屏看懂购买理由。",
            "visual": "竖版海报，上半部分场景，下半部分产品和卖点，留白充足。",
        },
        {
            "purpose": "人群场景",
            "main": "{buy_point}",
            "sub": "用真实生活场景表达适用场景，不制造焦虑。",
            "visual": "竖版生活方式图，人物只作场景辅助，产品保持清晰露出。",
        },
        {
            "purpose": "卖点拆解",
            "main": "{proof_points}",
            "sub": "信息模块化展示当前产品核心卖点，避免堆字。",
            "visual": "竖版信息卡布局，3个卖点模块，配产品图和浅色背景。",
        },
        {
            "purpose": "步骤教程",
            "main": "按说明合理使用",
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
            "purpose": "详情页首屏承接",
            "main": "{theme_name}场景",
            "sub": "第一屏必须承接链接定位，让用户一眼知道这条链接主打的人群和场景。",
            "visual": "详情页第1屏，首屏大场景+产品完整露出+主题定位标题，建立整套详情页的视觉基调。",
        },
        {
            "purpose": "场景痛点解释",
            "main": "为什么需要日常护理？",
            "sub": "围绕本链接场景解释用户为什么会需要这个产品，只做日常护理表达。",
            "visual": "详情页第2屏，场景细节+用户困扰信息卡+产品作为解决方案引出，避免恐吓式画面。",
        },
        {
            "purpose": "核心卖点拆解",
            "main": "核心卖点清楚看",
            "sub": "把链接定位转成2-3个可视化卖点或背书角标，不写完整长句。",
            "visual": "详情页第3屏，产品大图+2-3个卖点模块+图标化说明，重点解释产品带来的选择理由。",
        },
        {
            "purpose": "使用方法",
            "main": "按说明合理使用",
            "sub": "步骤化表达，降低理解成本，并和本链接场景结合。",
            "visual": "详情页第4屏，三步使用流程或时间线，突出取用、用量/频次以说明书为准、使用后收纳等动作。",
        },
        {
            "purpose": "规格资质信任",
            "main": "商品信息以资质与说明书为准",
            "sub": "展示真实资质、规格和SKU信息，不做机构或专家背书。",
            "visual": "详情页第5屏，注册证/说明书局部+产品包装+规格/SKU信息矩阵，形成购买前信任确认。",
        },
        {
            "purpose": "品牌背书",
            "main": "恒品日常护理用品",
            "sub": "收束详情页，补充品牌简介和购买提醒，提醒按说明使用。",
            "visual": "详情页第6屏，品牌简介+产品陈列+服务/售后信息角标，作为详情页末尾收口模块。",
        },
    ],
    "笔记图": [
        {
            "purpose": "种草封面",
            "main": "{hero}",
            "sub": "真实分享感，避免功效承诺。",
            "visual": "小红书笔记封面风格，产品+洗漱台+手写感标签。",
        },
        {
            "purpose": "场景分享",
            "main": "{buy_point}",
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


@dataclass(frozen=True)
class ProductAnalysisResult:
    product_count: int
    created: int
    updated: int


class ProductionGenerator:
    def __init__(self, config: AppConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.client = FeishuClient(config.feishu)

    def analyze_products(self, limit: int = 20) -> ProductAnalysisResult:
        table_ids = self._table_ids()
        timestamp = int(datetime.now().timestamp() * 1000)
        product_records = self.client.list_records(table_ids[PRODUCT_TABLE], page_size=500)
        products = [row for row in product_records if as_text(row.get("fields", {}).get("款式编码"))][:limit]
        product_ids = {as_text(row.get("fields", {}).get("款式编码")) for row in products}
        for row in self.client.list_records(table_ids[ANALYSIS_TABLE], page_size=500):
            fields = row.get("fields", {})
            if as_text(fields.get("款式编码")) in product_ids:
                self.client.delete_record(table_ids[ANALYSIS_TABLE], as_text(row.get("record_id")))
        create_rows: list[dict[str, Any]] = []
        for product in products:
            fields = product.get("fields", {})
            create_rows.extend(self._product_analysis_rows(fields, timestamp))
        created = self._batch_create(table_ids[ANALYSIS_TABLE], create_rows)
        return ProductAnalysisResult(product_count=len(products), created=created, updated=0)

    def generate(self, limit: int = 5) -> ProductionGenerationResult:
        table_ids = self._table_ids()
        confirmed_product_ids = self._confirmed_product_ids(table_ids)
        product_records = self.client.list_records(table_ids[PRODUCT_TABLE], page_size=100)
        products = [
            row
            for row in product_records
            if as_text(row.get("fields", {}).get("款式编码")) in confirmed_product_ids
        ]
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
            product_themes = self._product_themes(fields, target_count)

            for index, theme in enumerate(product_themes, start=1):
                theme_id = f"{product_id}-T{index:02d}"
                if theme_id not in existing_theme_ids:
                    theme_rows.append(
                        self._theme_row_fields(
                            fields=fields,
                            theme_id=theme_id,
                            theme=theme,
                            index=index,
                            sku_count=sku_count,
                            platform_requirements=platform_requirements,
                            timestamp=today,
                        )
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

    def refresh_themes(self) -> int:
        table_ids = self._table_ids()
        platform_requirements = read_platform_requirements()
        confirmed_product_ids = self._confirmed_product_ids(table_ids)
        products = {
            as_text(row.get("fields", {}).get("款式编码")): row.get("fields", {})
            for row in self.client.list_records(table_ids[PRODUCT_TABLE], page_size=500)
            if as_text(row.get("fields", {}).get("款式编码")) in confirmed_product_ids
        }
        updates: list[dict[str, Any]] = []
        timestamp = int(datetime.now().timestamp() * 1000)
        for row in self.client.list_records(table_ids[THEME_TABLE], page_size=500):
            fields = row.get("fields", {})
            product_id = as_text(fields.get("款式编码"))
            product_fields = products.get(product_id)
            if not product_fields:
                continue
            theme_id = as_text(fields.get("主题ID"))
            index = int(as_number(fields.get("链接序号")) or self._theme_index(theme_id) or 1)
            target_count = int(as_number(product_fields.get("每日目标链接数")) or 10)
            product_themes = self._product_themes(product_fields, target_count)
            if not (1 <= index <= len(product_themes)):
                continue
            updates.append(
                {
                    "record_id": as_text(row.get("record_id")),
                    "fields": self._theme_row_fields(
                        fields=product_fields,
                        theme_id=theme_id,
                        theme=product_themes[index - 1],
                        index=index,
                        sku_count=int(as_number(product_fields.get("SKU数量")) or 0),
                        platform_requirements=platform_requirements,
                        timestamp=timestamp,
                    ),
                }
            )
        updated = 0
        for index in range(0, len(updates), 100):
            updated += self.client.update_records_batch(table_ids[THEME_TABLE], updates[index : index + 100])
        return updated

    def refresh_tasks(self) -> int:
        table_ids = self._table_ids()
        confirmed_product_ids = self._confirmed_product_ids(table_ids)
        products = {
            as_text(row.get("fields", {}).get("款式编码")): row.get("fields", {})
            for row in self.client.list_records(table_ids[PRODUCT_TABLE], page_size=500)
            if as_text(row.get("fields", {}).get("款式编码")) in confirmed_product_ids
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
            link_index = int(as_number(fields.get("链接序号")) or self._theme_index(theme_id) or 1)
            theme = self._theme_for_product_index(product_fields, link_index, theme)
            task_updates.append(
                {
                    "record_id": record_id,
                    "fields": {
                        **self._task_content_fields(
                            fields=product_fields,
                            theme_id=theme_id,
                            theme=theme,
                            link_index=link_index,
                            asset_type=asset_type,
                            seq=seq,
                            size=as_text(fields.get("图片尺寸")),
                            task_id=as_text(fields.get("任务ID")),
                        ),
                        "产品参考图路径": self._product_reference_path(product_fields),
                        "参考素材使用方式": "本次生图参考图优先使用产品白底图，保证主体真实一致；暂不使用参考素材池。",
                    },
                }
            )
        updated = 0
        for index in range(0, len(task_updates), 100):
            updated += self.client.update_records_batch(table_ids[TASK_TABLE], task_updates[index : index + 100])
        return updated

    def _theme_for_product_index(
        self, product_fields: dict[str, Any], link_index: int, fallback: dict[str, str]
    ) -> dict[str, str]:
        target_count = int(as_number(product_fields.get("每日目标链接数")) or 10)
        themes = self._product_themes(product_fields, target_count)
        if 1 <= link_index <= len(themes):
            return themes[link_index - 1]
        return fallback

    def _table_ids(self) -> dict[str, str]:
        existing = {table_name(item): table_id(item) for item in self.client.list_tables()}
        required = (PRODUCT_TABLE, ANALYSIS_TABLE, THEME_TABLE, TASK_TABLE, RISK_TABLE)
        missing = [name for name in required if not existing.get(name)]
        if missing:
            raise RuntimeError(f"Missing production tables: {', '.join(missing)}")
        return {name: existing[name] for name in required}

    def _confirmed_product_ids(self, table_ids: dict[str, str]) -> set[str]:
        statuses_by_product: dict[str, list[str]] = {}
        for row in self.client.list_records(table_ids[ANALYSIS_TABLE], page_size=500):
            fields = row.get("fields", {})
            product_id = as_text(fields.get("款式编码"))
            if not product_id:
                continue
            statuses_by_product.setdefault(product_id, []).append(as_text(fields.get("人工确认状态")))
        return {
            product_id
            for product_id, statuses in statuses_by_product.items()
            if statuses and all(status == "已确认" for status in statuses)
        }

    def _title(self, fields: dict[str, Any]) -> str:
        product_name = as_text(fields.get("标准产品名称"))
        spec = as_text(fields.get("规格/型号/数量"))
        title_terms = self._product_title_terms(fields)
        return " ".join(part for part in [product_name, spec, title_terms] if part).strip()

    def _product_analysis_rows(self, fields: dict[str, Any], timestamp: int) -> list[dict[str, Any]]:
        product_id = as_text(fields.get("款式编码"))
        product_name = as_text(fields.get("标准产品名称"))
        target_count = int(as_number(fields.get("每日目标链接数")) or 10)
        themes = self._product_themes(fields, target_count)
        rows: list[dict[str, Any]] = []
        for index, theme in enumerate(themes, start=1):
            rows.append(
                {
                    "分析ID": f"{product_id}-P{index:02d}",
                    "款式编码": product_id,
                    "标准产品名称": product_name,
                    "人群": self._consumer_persona(theme, fields, index),
                    "场景": theme["scene"],
                    "卖点": self._consumer_selling_point(theme),
                    "消费者选择的原因": self._consumer_choice_reason(theme),
                    "产品解决了什么问题": self._consumer_problem(theme),
                    "为什么是这个产品来解决这个问题": self._why_this_product_reason(theme, fields),
                    "分析时间": timestamp,
                    "人工确认状态": "待确认",
                    "人工确认意见": "",
                    "确认人": "",
                    "确认时间": None,
                }
            )
        return rows

    def _consumer_persona(self, theme: dict[str, str], fields: dict[str, Any], index: int) -> str:
        product_text = self._positioning_text(fields)
        name = theme["name"]
        if self._is_desensitizing_toothpaste(fields):
            mapping = {
                "牙齿敏感护理": "25-45岁｜男女不限｜资深中产/都市型男｜冷热酸甜入口容易敏感，愿意为针对性护理买单",
                "牙本质小管原理": "25-40岁｜男女不限｜精致女性/悦己青年｜买前会看成分、原理和资质，偏理性决策",
                "牙龈出血关注": "30-55岁｜男女不限｜资深中产/品质银发｜刷牙时关注牙龈状态，需要稳妥护理选择",
                "牙菌斑管理": "25-45岁｜男女不限｜悦己青年/资深中产｜重视日常清洁管理，想把口腔护理做细",
                "配方成分透明": "25-45岁｜女性为主｜精致女性/悦己青年｜关注配方表、成分透明和使用体验",
                "居家日用步骤": "20-40岁｜男女不限｜平价青年/实惠大众｜第一次购买，希望使用方法简单清楚",
                "规格组合选择": "25-50岁｜男女不限｜实惠大众/小镇中坚｜按家庭用量和预算选择组合规格",
                "资质安心说明": "30-55岁｜男女不限｜资深中产/品质银发｜医疗器械类产品购买前先看资质",
                "薄荷口感体验": "20-35岁｜女性为主｜精致女性/悦己青年｜在意口感清新和日常坚持体验",
                "家庭备用复购": "30-55岁｜男女不限｜小镇中坚/实惠大众｜家庭多人或周期使用，需要备用更方便",
            }
            return mapping.get(name, theme["audience"])
        if "含漱" in product_text:
            mapping = {
                "日常口腔护理": "20-40岁｜男女不限｜悦己青年/平价青年｜饭后、刷牙后想多一步口腔护理",
                "正畸人群护理": "18-35岁｜男女不限｜精致女性/悦己青年｜正畸期间清洁步骤更多，需要便捷护理",
                "家庭备用护理": "30-55岁｜男女不限｜小镇中坚/实惠大众｜家里常备口腔护理用品，方便多人使用",
                "饭后清爽护理": "20-40岁｜男女不限｜都市型男/悦己青年｜午餐后、约会前、通勤时在意口腔状态",
                "出行便携护理": "20-40岁｜男女不限｜都市型男/悦己青年｜出差旅行或外出时需要随手护理",
                "成分信息透明": "25-45岁｜女性为主｜精致女性/资深中产｜购买前想看清成分、规格和资质",
                "使用步骤清晰": "20-45岁｜男女不限｜平价青年/实惠大众｜第一次购买，需要用法简单明了",
                "规格组合清楚": "25-50岁｜男女不限｜实惠大众/小镇中坚｜按家庭人数和使用频率选择瓶数组合",
                "资质安心说明": "30-55岁｜男女不限｜资深中产/品质银发｜医疗器械类口腔产品先看资质再买",
                "温和口感体验": "20-40岁｜女性为主｜精致女性/悦己青年｜在意入口感受和日常使用舒适度",
            }
            return mapping.get(name, theme["audience"])
        fallback_labels = ["精致女性", "悦己青年", "小镇新贵", "小镇中坚", "资深中产", "都市型男", "实惠大众", "品质银发", "平价青年", "简朴银发"]
        return f"20-50岁｜男女不限｜{fallback_labels[(index - 1) % len(fallback_labels)]}｜{theme['audience']}"

    def _consumer_selling_point(self, theme: dict[str, str]) -> str:
        if theme.get("hero"):
            return self._short_text(theme["hero"], 32)
        mapping = {
            "日常口腔护理": "日常护理多一步",
            "正畸人群护理": "正畸清洁更方便",
            "家庭备用护理": "家庭常备更省心",
            "饭后清爽护理": "饭后口腔更清爽",
            "出行便携护理": "出门也能随手护理",
            "成分信息透明": "成分规格看得清",
            "使用步骤清晰": "使用步骤更简单",
            "规格组合清楚": "瓶数组合好选择",
            "资质安心说明": "资质信息清楚可查",
            "温和口感体验": "口感温和更好坚持",
        }
        return mapping.get(theme["name"], self._short_text(theme["name"], 32))

    def _consumer_choice_reason(self, theme: dict[str, str]) -> str:
        if theme.get("buy_point"):
            return self._short_text(theme["buy_point"], 48)
        mapping = {
            "日常口腔护理": "想在刷牙后、饭后补充口腔护理",
            "正畸人群护理": "正畸期间清洁麻烦，需要更方便的护理补充",
            "家庭备用护理": "家里多人可用，日常备用不慌",
            "饭后清爽护理": "饭后、社交前想保持口腔状态",
            "出行便携护理": "外出时也想保持护理习惯",
            "成分信息透明": "买前想知道成分、规格和资质",
            "使用步骤清晰": "不想研究复杂用法，照着步骤用更安心",
            "规格组合清楚": "想按预算和使用频率选合适组合",
            "资质安心说明": "医疗器械类产品，先看资质再下单",
            "温和口感体验": "入口体验舒服，日常更容易坚持",
        }
        return mapping.get(theme["name"], self._short_text(theme["pain"], 48))

    def _consumer_problem(self, theme: dict[str, str]) -> str:
        mapping = {
            "牙齿敏感护理": "冷热酸甜刺激时牙齿敏感",
            "牙本质小管原理": "不知道脱敏产品为什么有用",
            "牙龈出血关注": "刷牙时牙龈状态不稳定",
            "牙菌斑管理": "日常清洁后仍担心牙菌斑",
            "配方成分透明": "担心成分不清楚、信息不透明",
            "居家日用步骤": "不知道怎么用、什么时候用",
            "规格组合选择": "不知道买几支更合适",
            "资质安心说明": "担心医疗器械资质不清楚",
            "薄荷口感体验": "担心口感不好、难坚持",
            "家庭备用复购": "家庭多人使用容易断货",
        }
        return mapping.get(theme["name"], self._short_text(theme["pain"], 48))

    def _why_this_product_reason(self, theme: dict[str, str], fields: dict[str, Any]) -> str:
        product_text = self._positioning_text(fields)
        spec = as_text(fields.get("规格/型号/数量"))
        if self._is_desensitizing_toothpaste(fields):
            mapping = {
                "牙齿敏感护理": "脱敏膏定位明确，120g/支，适合牙敏感护理测试",
                "牙本质小管原理": "有生物活性玻璃、氯化锶、氟化钠等成分信息可讲清原理",
                "牙龈出血关注": "可宣传范围覆盖牙龈出血相关护理，需按说明书口径表达",
                "牙菌斑管理": "可宣传范围包含牙菌斑管理，和普通牙膏形成区分",
                "配方成分透明": "成分表完整，适合做成分透明和理性购买方向",
                "居家日用步骤": "膏体形态接近日常刷牙习惯，使用门槛低",
                "规格组合选择": "1支到5支组合覆盖尝试、复购和家庭备用",
                "资质安心说明": "医疗器械属性和资质图可作为信任背书",
                "薄荷口感体验": "薄荷油、薄荷脑、留兰香油支撑清新口感表达",
                "家庭备用复购": "价格带和多支组合适合做家庭备用/周期复购",
            }
            return mapping.get(theme["name"], self._short_text(theme["trust"], 64))
        if "含漱" in product_text:
            mapping = {
                "日常口腔护理": f"{spec}规格清楚，适合日常刷牙后补充护理",
                "正畸人群护理": "含漱液形态使用方便，适合正畸清洁后的补充护理",
                "家庭备用护理": "瓶装规格适合家庭洗漱台常备",
                "饭后清爽护理": "使用动作简单，适合饭后快速护理",
                "出行便携护理": "产品形态清楚，适合外出护理场景测试",
                "成分信息透明": "有成分、规格和资质信息可做信任解释",
                "使用步骤清晰": "使用步骤可视化，降低首次购买理解成本",
                "规格组合清楚": "SKU组合清楚，便于按家庭用量选择",
                "资质安心说明": "医疗器械属性和资质图可提高信任",
                "温和口感体验": "口感体验可作为日常坚持理由",
            }
            return mapping.get(theme["name"], self._short_text(theme["trust"], 64))
        return self._short_text(theme["trust"], 64)

    @staticmethod
    def _short_text(text: str, max_len: int = 80) -> str:
        cleaned = as_text(text).replace("\n", " ").strip()
        if len(cleaned) <= max_len:
            return cleaned
        return cleaned[: max_len - 1].rstrip("，；。 ") + "…"

    def _product_analysis_fields(self, fields: dict[str, Any], timestamp: int) -> dict[str, Any]:
        product_id = as_text(fields.get("款式编码"))
        product_name = as_text(fields.get("标准产品名称"))
        category = as_text(fields.get("产品类目"))
        platform = as_text(fields.get("平台"))
        owner = as_text(fields.get("负责人"))
        material = as_text(fields.get("材质/成分"))
        scope = as_text(fields.get("可宣传范围")) or as_text(fields.get("基础卖点"))
        people = as_text(fields.get("适用人群"))
        scenes = as_text(fields.get("适用场景"))
        spec = as_text(fields.get("规格/型号/数量"))
        sku_detail = as_text(fields.get("SKU明细"))
        themes = self._product_themes(fields, int(as_number(fields.get("每日目标链接数")) or 10))
        return {
            "分析ID": product_id,
            "款式编码": product_id,
            "标准产品名称": product_name,
            "产品类目": category,
            "平台": platform,
            "负责人": owner,
            "材质成分摘要": self._material_summary(fields),
            "预期用途摘要": scope,
            "适用人群拆解": self._audience_summary(people, themes),
            "适用场景拆解": self._scene_summary(scenes, themes),
            "资质背书依据": self._trust_basis(fields),
            "可宣传边界": self._promotion_boundary(fields),
            "高风险表达提醒": self._risk_expression_note(scope),
            "目标人群场景分析": self._target_scene_analysis(themes),
            "产品卖点梳理": self._selling_points_analysis(fields, themes),
            "消费者买点梳理": self._buying_points_analysis(themes),
            "问题-解决路径": self._problem_solution_analysis(themes),
            "为什么选择这个产品": self._why_choose_analysis(fields, themes),
            "建议主题方向": "\n".join(f"{index}. {theme['name']}：{theme['audience']}" for index, theme in enumerate(themes, 1)),
            "建议主文案方向": "\n".join(
                f"{index}. {theme.get('hero', theme['name'])} / {theme.get('buy_point', theme['pain'])}"
                for index, theme in enumerate(themes, 1)
            ),
            "合规提醒": self._analysis_compliance_note(fields),
            "分析结论": (
                f"{product_name}的后续链接不应先套通用模板，应围绕产品成分、预期用途、适用人群和资质边界展开。"
                f"规格/SKU信息为{spec}；SKU组合为{sku_detail}。人工确认后再进入主题规划与素材生产。"
            ),
            "分析时间": timestamp,
        }

    def _material_summary(self, fields: dict[str, Any]) -> str:
        material = as_text(fields.get("材质/成分"))
        text = self._product_text(fields)
        if "脱敏" in text or "牙本质小管" in text:
            return (
                "核心成分与信息点：生物活性玻璃、氯化锶、氟化钠可作为脱敏护理和牙本质小管相关原理的说明抓手；"
                "二氧化硅、羧甲基纤维素钠、聚乙二醇400等体现膏体基质；"
                "β-葡聚糖、薄荷油、薄荷脑、留兰香油等可用于口感体验和成分透明方向。"
                f"\n原始成分：{material}"
            )
        return f"原始成分：{material}"

    @staticmethod
    def _audience_summary(people: str, themes: list[dict[str, str]]) -> str:
        lines = [f"原始适用人群：{people}"] if people else []
        lines.extend(f"{index}. {theme['name']}：{theme['audience']}" for index, theme in enumerate(themes, 1))
        return "\n".join(lines)

    @staticmethod
    def _scene_summary(scenes: str, themes: list[dict[str, str]]) -> str:
        lines = [f"原始适用场景：{scenes}"] if scenes else []
        lines.extend(f"{index}. {theme['name']}：{theme['scene']}" for index, theme in enumerate(themes, 1))
        return "\n".join(lines)

    def _trust_basis(self, fields: dict[str, Any]) -> str:
        cert_path = as_text(fields.get("注册证/资质文件夹"))
        scope = as_text(fields.get("可宣传范围")) or as_text(fields.get("基础卖点"))
        return (
            "资质背书优先使用：注册证、说明书、标签信息、页面真实展示和产品包装。"
            f"\n资质文件夹：{cert_path}"
            f"\n可宣传范围原文：{scope}"
        )

    def _promotion_boundary(self, fields: dict[str, Any]) -> str:
        scope = as_text(fields.get("可宣传范围")) or as_text(fields.get("基础卖点"))
        return (
            "允许方向：围绕产品注册证/说明书/标签可证明的信息表达，包括成分、规格、适用范围、使用方法、资质可查。"
            "\n谨慎方向：治疗、炎症、出血、抑制、减少等词如确属资质范围，可在人工确认后按说明书口径使用。"
            "\n禁止方向：保证效果、立刻见效、根治、医生/机构背书、病例反馈、夸张对比、病灶刺激画面。"
            f"\n原始范围：{scope}"
        )

    @staticmethod
    def _risk_expression_note(scope: str) -> str:
        risk_terms = [term for term in ("治疗", "炎症", "出血", "抑制", "减少", "牙菌斑", "过敏") if term in scope]
        if not risk_terms:
            return "未在可宣传范围中识别到明显高风险词，但仍需按平台规范审核。"
        return (
            f"识别到高风险/需确认表达：{', '.join(risk_terms)}。"
            "这些词不能随意放大为功效承诺，应优先改写为“说明书适用范围、护理关注、按说明使用、信息以资质为准”。"
        )

    @staticmethod
    def _target_scene_analysis(themes: list[dict[str, str]]) -> str:
        return "\n".join(
            f"{index}. {theme['name']}：面向{theme['audience']}，在{theme['scene']}中切入。核心问题是{theme['pain']}。"
            for index, theme in enumerate(themes, 1)
        )

    @staticmethod
    def _selling_points_analysis(fields: dict[str, Any], themes: list[dict[str, str]]) -> str:
        product_name = as_text(fields.get("标准产品名称"))
        return "\n".join(
            f"{index}. {theme['name']}：卖点为{theme['angle']}；证明点为{theme.get('proof_points', theme['trust'])}。"
            for index, theme in enumerate(themes, 1)
        ) or f"{product_name}暂无可拆解卖点，请补充成分、用途和资质信息。"

    @staticmethod
    def _buying_points_analysis(themes: list[dict[str, str]]) -> str:
        return "\n".join(
            f"{index}. {theme['name']}：消费者买点是“{theme.get('buy_point', theme['pain'])}”，对应主张“{theme.get('hero', theme['name'])}”。"
            for index, theme in enumerate(themes, 1)
        )

    @staticmethod
    def _problem_solution_analysis(themes: list[dict[str, str]]) -> str:
        return "\n".join(
            f"{index}. {theme['name']}：用户问题={theme['pain']}；解决方式={theme['angle']}；选择理由={theme['trust']}。"
            for index, theme in enumerate(themes, 1)
        )

    def _why_choose_analysis(self, fields: dict[str, Any], themes: list[dict[str, str]]) -> str:
        spec = as_text(fields.get("规格/型号/数量"))
        sku_detail = as_text(fields.get("SKU明细"))
        reasons = [
            "产品信息有明确成分、规格、适用范围和资质文件路径，可支撑素材生成前的事实核验。",
            "卖点可以拆成原理、场景、成分、资质、规格、体验多条测试方向，适合做多链接赛马。",
            f"规格为{spec}，SKU为{sku_detail}，可做单支测试和组合装转化测试。",
        ]
        proof_points = [theme.get("proof_points", "") for theme in themes if theme.get("proof_points")]
        if proof_points:
            reasons.append(f"可反复使用的证明点：{'；'.join(proof_points[:5])}。")
        return "\n".join(f"{index}. {reason}" for index, reason in enumerate(reasons, 1))

    def _analysis_compliance_note(self, fields: dict[str, Any]) -> str:
        return (
            self._promotion_boundary(fields)
            + "\n人工确认要求：确认目标人群是否真实适用、卖点是否在资质范围内、主文案是否可上架、是否需要删除或降级争议表达。"
        )

    def _product_title_terms(self, fields: dict[str, Any]) -> str:
        text = self._positioning_text(fields)
        if self._is_desensitizing_toothpaste(fields):
            return "牙齿敏感护理 牙龈护理"
        if "含漱" in text:
            return "日常口腔护理"
        return "口腔护理"

    @staticmethod
    def _product_text(fields: dict[str, Any]) -> str:
        keys = ("标准产品名称", "产品类目", "基础卖点", "材质/成分", "可宣传范围", "适用人群", "适用场景")
        return "\n".join(as_text(fields.get(key)) for key in keys)

    @staticmethod
    def _positioning_text(fields: dict[str, Any]) -> str:
        keys = ("标准产品名称", "基础卖点", "材质/成分", "可宣传范围", "适用人群", "适用场景")
        return "\n".join(as_text(fields.get(key)) for key in keys)

    def _is_desensitizing_toothpaste(self, fields: dict[str, Any]) -> bool:
        text = self._positioning_text(fields)
        product_name = as_text(fields.get("标准产品名称"))
        if "含漱液" in product_name or "含漱" in product_name:
            return False
        strong_signals = ("医用口腔护理脱敏膏", "脱敏膏", "牙本质小管", "氯化锶", "生物活性玻璃")
        return any(signal in text for signal in strong_signals)

    def _product_themes(self, fields: dict[str, Any], target_count: int) -> list[dict[str, str]]:
        if self._is_desensitizing_toothpaste(fields):
            themes = self._desensitizing_toothpaste_themes(fields)
        else:
            themes = [dict(theme) for theme in THEME_LIBRARY]
        return [self._apply_visual_system(theme, index) for index, theme in enumerate(themes[:target_count])]

    def _desensitizing_toothpaste_themes(self, fields: dict[str, Any]) -> list[dict[str, str]]:
        product_name = as_text(fields.get("标准产品名称")) or "口腔护理产品"
        spec = as_text(fields.get("规格/型号/数量"))
        sku_detail = as_text(fields.get("SKU明细")) or spec
        return [
            {
                "name": "牙齿敏感护理",
                "style": "清爽专业",
                "audience": "牙齿遇冷、遇热、酸甜刺激时容易敏感的人群",
                "scene": "居家刷牙后的日常牙齿敏感护理",
                "pain": "冷热酸甜入口时牙齿容易敏感，日常护理需要更有针对性的产品",
                "angle": "基于注册证/说明书口径，突出封闭牙本质小管这一脱敏护理原理",
                "trust": "商品信息以注册证、说明书、标签和资质图为准",
                "promo": "单支低门槛测试",
                "hero": "冷热酸甜敏感护理",
                "buy_point": "冷热酸甜前后都要认真护理",
                "proof_points": "牙本质小管封闭、脱敏护理、120g/支",
            },
            {
                "name": "牙本质小管原理",
                "style": "原理科普",
                "audience": "关注脱敏原理、购买前会看成分和说明的人群",
                "scene": "详情页原理说明、主图卖点拆解",
                "pain": "不知道脱敏膏为什么适合牙齿敏感护理，需要看懂作用路径",
                "angle": "从牙本质小管封闭逻辑解释产品定位，避免夸张疗效承诺",
                "trust": "用说明书、资质信息和成分表支持，不使用实验结论夸大",
                "promo": "原理信任测试",
                "hero": "看懂脱敏护理原理",
                "buy_point": "脱敏护理看得懂",
                "proof_points": "生物活性玻璃、氯化锶、氟化钠",
            },
            {
                "name": "牙龈出血关注",
                "style": "稳妥关怀",
                "audience": "关注牙龈出血、刷牙时牙龈状态的人群",
                "scene": "早晚刷牙时的牙龈护理关注场景",
                "pain": "刷牙时发现牙龈出血，想找一款信息清楚的口腔护理产品",
                "angle": "按注册证/说明书范围表达缓解和减少牙龈出血相关护理，不做保证",
                "trust": "涉及出血、炎症等高风险词时使用说明书口径并标注人工确认",
                "promo": "痛点方向谨慎测试",
                "hero": "牙龈出血护理关注",
                "buy_point": "刷牙时的牙龈状态别忽略",
                "proof_points": "菌斑性牙龈炎症适用范围、牙龈出血护理、说明书为准",
            },
            {
                "name": "牙菌斑管理",
                "style": "清洁管理",
                "audience": "重视牙菌斑管理和日常口腔清洁的人群",
                "scene": "早晚刷牙、饭后清洁后的口腔护理补充",
                "pain": "日常清洁后仍想加强牙菌斑管理和口腔护理",
                "angle": "围绕抑制和减少牙菌斑的注册证/说明书范围做稳妥表达",
                "trust": "避免杀菌、消炎等高风险词，强调说明书和资质可查",
                "promo": "清洁管理方向测试",
                "hero": "牙菌斑管理多一步",
                "buy_point": "日常清洁后再补一步",
                "proof_points": "抑制和减少牙菌斑、口腔清洁管理、资质可查",
            },
            {
                "name": "配方成分透明",
                "style": "成分科普",
                "audience": "购买前会看配方成分、规格和资质的人群",
                "scene": "成分说明、详情页卖点拆解、信任背书模块",
                "pain": "医疗器械类口腔产品选择时，需要看清成分与信息来源",
                "angle": "展示生物活性玻璃、氯化锶、氟化钠、β-葡聚糖等成分信息，不夸大含量和效果",
                "trust": "成分来自产品资料，具体信息以标签、说明书和资质文件为准",
                "promo": "成分信任测试",
                "hero": "成分信息清楚看",
                "buy_point": "买前看清配方与规格",
                "proof_points": "生物活性玻璃、氯化锶、氟化钠、β-葡聚糖",
            },
            {
                "name": "居家日用步骤",
                "style": "教程说明",
                "audience": "第一次购买脱敏膏或不清楚使用方式的人群",
                "scene": "居家刷牙台、早晚护理、详情页步骤说明",
                "pain": "不知道什么时候用、怎么用、需要注意什么",
                "angle": "用步骤图降低理解成本，提醒按说明书合理使用",
                "trust": "使用方法以说明书为准，特殊情况先阅读说明或咨询专业人士",
                "promo": "教程型链接测试",
                "hero": "使用步骤更清楚",
                "buy_point": "居家护理照着用",
                "proof_points": "取用、刷牙/护理、收纳、说明书为准",
            },
            {
                "name": "规格组合选择",
                "style": "SKU转化",
                "audience": "想先试用或按周期囤货的家庭用户",
                "scene": "单支尝试、多人家庭备用、周期复购选择",
                "pain": "不知道选1支、2支、3支还是5支，担心买错规格",
                "angle": f"清楚展示{sku_detail}组合，减少规格理解成本",
                "trust": "SKU、数量、价格带与上架信息保持一致，不做低价误导",
                "promo": "SKU组合转化测试",
                "hero": f"{sku_detail}可选",
                "buy_point": "按使用频率选规格",
                "proof_points": f"{sku_detail}、120g/支、组合清楚",
            },
            {
                "name": "资质安心说明",
                "style": "资质背书",
                "audience": "重视医疗器械资质和商品信息真实性的人群",
                "scene": "详情页资质模块、主图信任角标、购买前确认",
                "pain": "医疗器械类产品购买前，需要确认资质、说明书和标签信息",
                "angle": "展示注册证、说明书、标签等可核验信息，避免医生/机构背书",
                "trust": "产品信息以资质文件、说明书和页面展示为准",
                "promo": "信任转化测试",
                "hero": "资质信息清楚可查",
                "buy_point": "买前先看资质",
                "proof_points": "注册证、说明书、标签信息",
            },
            {
                "name": "薄荷口感体验",
                "style": "体验清新",
                "audience": "在意口感、气味和日常使用体验的人群",
                "scene": "早晚刷牙后的清新口腔护理体验",
                "pain": "担心口腔护理产品不好入口、体验不舒服",
                "angle": "基于食用香精中薄荷油、薄荷脑、留兰香油等信息表达清新体验，不做效果保证",
                "trust": "口感体验与功效表达分开，具体使用感因人而异",
                "promo": "体验感方向测试",
                "hero": "薄荷清新口感",
                "buy_point": "日常使用更容易坚持",
                "proof_points": "薄荷油、薄荷脑、留兰香油",
            },
            {
                "name": "家庭备用复购",
                "style": "家庭备用",
                "audience": "家庭多人口腔护理、周期使用和复购人群",
                "scene": "浴室柜、家庭洗漱台、囤货备用场景",
                "pain": "家里多人使用或周期护理时，需要规格清楚、备用方便",
                "angle": "用家庭备用和组合规格表达购买理由，不做低价或疗效承诺",
                "trust": "规格、数量、SKU和售后信息清楚展示",
                "promo": "多支组合测试",
                "hero": "家庭备用更省心",
                "buy_point": "多支组合按需选",
                "proof_points": f"{sku_detail}、120g/支、家庭备用",
            },
        ]

    @staticmethod
    def _apply_visual_system(theme: dict[str, str], index: int) -> dict[str, str]:
        visual = DEFAULT_VISUAL_SYSTEMS[index % len(DEFAULT_VISUAL_SYSTEMS)]
        output = dict(theme)
        output.setdefault("visual_style", visual["visual_style"])
        output.setdefault("palette", visual["palette"])
        output.setdefault("composition", visual["composition"])
        output.setdefault("texture", visual["texture"])
        return output

    @staticmethod
    def _product_reference_path(fields: dict[str, Any]) -> str:
        return (
            as_text(fields.get("白底图文件夹"))
            or as_text(fields.get("产品实拍文件夹"))
            or as_text(fields.get("透明底图文件夹"))
        )

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

    def _theme_row_fields(
        self,
        fields: dict[str, Any],
        theme_id: str,
        theme: dict[str, str],
        index: int,
        sku_count: int,
        platform_requirements: str,
        timestamp: int,
    ) -> dict[str, Any]:
        product_id = as_text(fields.get("款式编码"))
        product_name = as_text(fields.get("标准产品名称"))
        title = as_text(fields.get("商品标题（埋词）")) or self._title(fields)
        platform = as_text(fields.get("平台")) or "全平台"
        return {
            "主题ID": theme_id or f"{product_id}-T{index:02d}",
            "款式编码": product_id,
            "标准产品名称": product_name,
            "商品标题（埋词）": title,
            "平台": platform,
            "链接序号": index,
            "主题名称": theme["name"],
            "主题风格": theme["style"],
            "视觉风格": theme["visual_style"],
            "色调搭配": theme["palette"],
            "推荐构图": theme["composition"],
            "画面质感": theme["texture"],
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
            "生成日期": timestamp,
        }

    @staticmethod
    def _theme_index(theme_id: str) -> int:
        try:
            return int(as_text(theme_id).rsplit("T", 1)[1])
        except (IndexError, TypeError, ValueError):
            return 0

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
                        "产品参考图路径": self._product_reference_path(fields),
                        "场景参考图路径": "",
                        "匹配参考素材ID": "",
                        "参考素材使用方式": "本次生图参考图优先使用产品白底图，保证主体真实一致；暂不使用参考素材池。",
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
            "设计要求": self._design_requirement(asset_type, seq, theme),
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
        name = as_text(fields.get("主题名称"))
        defaults = THEME_BY_NAME.get(name, {})
        theme = {
            "name": name,
            "style": as_text(fields.get("主题风格")) or defaults.get("style", ""),
            "audience": as_text(fields.get("目标人群")) or defaults.get("audience", ""),
            "scene": as_text(fields.get("使用场景")) or defaults.get("scene", ""),
            "pain": as_text(fields.get("核心痛点")) or defaults.get("pain", ""),
            "angle": as_text(fields.get("核心卖点")) or defaults.get("angle", ""),
            "trust": as_text(fields.get("信任背书")) or defaults.get("trust", ""),
            "promo": as_text(fields.get("价格/促销方向")) or defaults.get("promo", ""),
            "visual_style": as_text(fields.get("视觉风格")) or defaults.get("visual_style", ""),
            "palette": as_text(fields.get("色调搭配")) or defaults.get("palette", ""),
            "composition": as_text(fields.get("推荐构图")) or defaults.get("composition", ""),
            "texture": as_text(fields.get("画面质感")) or defaults.get("texture", ""),
        }
        return {key: self._clean_legacy_product_terms(value) for key, value in theme.items()}

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
        return self._clean_legacy_product_terms(
            template.format(
                asset_type=asset_type,
                theme_name=theme.get("name", ""),
                audience=theme.get("audience", ""),
                scene=theme.get("scene", ""),
                angle=theme.get("angle", ""),
                hero=theme.get("hero", theme.get("name", "")),
                buy_point=theme.get("buy_point", theme.get("pain", "")),
                proof_points=theme.get("proof_points", theme.get("angle", "")),
                product_name=as_text(fields.get("标准产品名称")),
                spec=as_text(fields.get("规格/型号/数量")),
                sku_detail=as_text(fields.get("SKU明细")) or as_text(fields.get("规格/型号/数量")),
            )
        )

    @staticmethod
    def _clean_legacy_product_terms(text: str) -> str:
        replacements = {
            "含漱类产品": "该类口腔护理产品",
            "便捷含漱": "便捷护理动作",
            "含漱护理": "口腔护理",
            "含漱": "按说明使用",
            "含氟": "核心属性",
            "200ml/瓶": "规格信息",
            "口腔含漱液": "口腔护理产品",
        }
        cleaned = as_text(text)
        for source, target in replacements.items():
            cleaned = cleaned.replace(source, target)
        return cleaned

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

    def _design_requirement(self, asset_type: str, seq: int, theme: dict[str, str]) -> str:
        purpose = self._variant(asset_type, seq).get("purpose", asset_type)
        return (
            f"本图目的：{purpose}。视觉风格：{theme.get('visual_style', '')}；"
            f"色调搭配：{theme.get('palette', '')}。"
            "画面清晰、产品真实突出、信息层级明确，不使用夸张对比和医疗化承诺。"
        )

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
            "画面需补充2-3个短卖点或背书角标，例如核心成分/核心属性、规格信息、资质可查、按说明使用；"
            "同时解释该场景为什么需要这个产品、产品解决什么护理需求、给用户带来什么选择好处。"
            "如使用“二类医疗器械”等背书，只能作为资质信息角标表达，并保持“信息以资质/说明书为准”的稳妥口径。"
        )
        differentiation_rule = (
            f"本链接的专属视觉风格：{theme.get('visual_style', '')}；"
            f"专属色调：{theme.get('palette', '')}；"
            f"推荐构图：{theme.get('composition', '')}；"
            f"画面质感：{theme.get('texture', '')}。"
            "请让本链接与其他主题链接在色调、构图、道具、信息卡样式和整体气质上明显区分，"
            "但产品瓶身、包装、规格和资质信息必须保持真实一致。"
        )
        detail_page_rule = self._detail_page_prompt_rule(seq, theme) if asset_type == "详情页" else ""
        product_positioning = self._product_positioning_prompt(fields, theme)
        return (
            f"请基于上传的产品参考图生成{asset_type}第{seq}张，图片目的：{purpose}，尺寸要求：{size}。"
            f"产品：{as_text(fields.get('标准产品名称'))}；规格：{as_text(fields.get('规格/型号/数量'))}；"
            f"主题：{theme['name']}；目标人群：{theme['audience']}；使用场景：{theme['scene']}。"
            f"{product_positioning}"
            f"画面方向：{visual}。"
            f"画面文字主标题：{main}。辅助文字参考：{sub}。{visible_text_rule}{ecommerce_layout_rule}{differentiation_rule}{detail_page_rule}"
            "要求画面真实清晰，产品主体完整突出，避免医疗化治疗承诺、绝对化词汇、夸张前后对比、医生专家背书、二维码和外部联系方式。"
            "文案只使用稳妥表达：按说明合理使用、日常口腔护理、信息以说明书和资质文件为准。"
        )

    def _product_positioning_prompt(self, fields: dict[str, Any], theme: dict[str, str]) -> str:
        material = as_text(fields.get("材质/成分"))
        promo_scope = as_text(fields.get("可宣传范围")) or as_text(fields.get("基础卖点"))
        return (
            f"产品经理定位：本图必须围绕“{theme.get('hero', theme.get('name', ''))}”展开；"
            f"用户买点：{theme.get('buy_point', '')}；"
            f"证明点/成分或资质依据：{theme.get('proof_points', '')}。"
            f"产品资料中的成分信息：{material[:180]}。"
            f"可宣传范围以此为边界：{promo_scope[:160]}。"
            "如果原始资料含治疗、炎症、出血等高风险词，画面文案优先改成说明书口径、适用范围、护理关注、信息以资质为准。"
        )

    @staticmethod
    def _detail_page_prompt_rule(seq: int, theme: dict[str, str]) -> str:
        rules = {
            1: (
                "详情页第1屏专属要求：作为整套详情页开头，只做主题承接和产品第一印象。"
                "必须出现产品完整瓶身、链接主题场景、人群定位；不要展开步骤、资质证照或SKU对比。"
                "底部预留自然过渡到第2屏的场景问题。"
            ),
            2: (
                "详情页第2屏专属要求：承接第1屏，重点解释本场景下用户为什么需要护理。"
                "必须出现生活化场景细节、痛点信息卡、产品作为护理选择的引出；不要做资质背书页或品牌介绍页。"
                "结尾过渡到第3屏的产品卖点拆解。"
            ),
            3: (
                "详情页第3屏专属要求：围绕本链接定位拆解核心卖点。"
                f"卖点必须紧扣“{theme.get('angle', '')}”，用2-3个图标化模块表达；不要重复第2屏的痛点场景，也不要写长段说明。"
                "底部过渡到第4屏的使用方法。"
            ),
            4: (
                "详情页第4屏专属要求：做使用方法页。"
                "必须用步骤、时间线或流程图表达使用动作，并提醒按说明合理使用；使用动作必须匹配当前产品剂型，不要套用其他产品的使用方式。"
                "不要把它画成卖点海报、资质页或品牌页。"
                "上下边缘要延续前后页色调，让第3屏到第5屏衔接自然。"
            ),
            5: (
                "详情页第5屏专属要求：做规格、SKU和资质信任页。"
                "必须出现注册证/说明书/标签信息的真实展示位置、产品包装、规格或SKU信息矩阵；不要使用医生、医院、专家、机构推荐。"
                "结尾过渡到第6屏品牌收口。"
            ),
            6: (
                "详情页第6屏专属要求：作为整套详情页末尾收口。"
                "必须出现恒品品牌简介、产品陈列、按说明使用提醒和服务/售后信息角标；不要再重复痛点、步骤或SKU对比。"
                "整体要像详情页最后一屏，而不是新的主图海报。"
            ),
        }
        return rules.get(seq, "详情页专属要求：当前页面必须和前后页面形成连续叙事，避免与其他详情页重复构图和内容。")

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
