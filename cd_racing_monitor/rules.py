from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from .models import DailyRecord, Decision, RuleConfig


class RuleEngine:
    def __init__(self) -> None:
        self.history: dict[tuple[str, str, str, str], int] = defaultdict(int)

    def evaluate(self, record: DailyRecord, config: RuleConfig) -> Decision:
        matched: list[tuple[int, str, str, str, float, str]] = []

        if record.impressions < config.min_impressions:
            return self._decision(
                record,
                "样本不足",
                "数据量不足",
                "继续观察",
                0.35,
                ["sample_insufficient"],
                f"曝光 {record.impressions:.0f} < 最小曝光 {config.min_impressions:.0f}，暂不做强判断。",
            )

        if self._competitor_demand_is_weak(record, config):
            matched.append(
                (
                    50,
                    "需求判断",
                    "需求不足",
                    "复测",
                    0.78,
                    (
                        "竞品也卖不动：自家成交转化率 "
                        f"{pct(record.conversion_rate)}，竞品成交转化率 {pct(record.competitor_conversion_rate)}。"
                    ),
                )
            )

        if record.impressions > 0 and record.click_rate < config.low_click_rate:
            matched.append(
                (
                    10,
                    "点击判断",
                    "视觉/首屏吸引力问题",
                    "改视觉",
                    0.82,
                    f"没人点：点击率 {pct(record.click_rate)} < 低点击率阈值 {pct(config.low_click_rate)}。",
                )
            )

        if record.clicks >= config.min_clicks and record.conversion_rate < config.low_conversion_rate:
            matched.append(
                (
                    20,
                    "成交判断",
                    "方向与承接问题",
                    "改承接",
                    0.76,
                    (
                        "有人点不买：点击 "
                        f"{record.clicks:.0f} >= {config.min_clicks:.0f}，成交转化率 "
                        f"{pct(record.conversion_rate)} < {pct(config.low_conversion_rate)}。"
                    ),
                )
            )

        if (
            record.add_to_cart >= config.min_add_to_cart
            and record.add_to_cart_conversion_rate < config.low_cart_to_order_rate
        ):
            matched.append(
                (
                    30,
                    "加购判断",
                    "价格与信任问题",
                    "调价格/信任",
                    0.8,
                    (
                        "有人加购不买：加购 "
                        f"{record.add_to_cart:.0f} >= {config.min_add_to_cart:.0f}，加购成交率 "
                        f"{pct(record.add_to_cart_conversion_rate)} < {pct(config.low_cart_to_order_rate)}。"
                    ),
                )
            )

        if record.orders >= config.min_orders and record.refund_rate > config.high_refund_rate:
            matched.append(
                (
                    40,
                    "退款判断",
                    "产品与承诺问题",
                    "修产品/承诺",
                    0.86,
                    (
                        "买了又退：成交 "
                        f"{record.orders:.0f} >= {config.min_orders:.0f}，退款率 "
                        f"{pct(record.refund_rate)} > {pct(config.high_refund_rate)}。"
                    ),
                )
            )

        if self._can_scale(record, config):
            matched.append(
                (
                    60,
                    "放量判断",
                    "表现达标",
                    "放量",
                    0.84,
                    (
                        "正向达标：点击率 "
                        f"{pct(record.click_rate)} >= {pct(config.scale_click_rate)}，成交转化率 "
                        f"{pct(record.conversion_rate)} >= {pct(config.scale_conversion_rate)}，退款率 "
                        f"{pct(record.refund_rate)} <= {pct(config.scale_refund_rate_max)}。"
                    ),
                )
            )

        if not matched:
            return self._decision(
                record,
                "持续观察",
                "暂未命中强规则",
                "继续观察",
                0.5,
                ["no_strong_signal"],
                "已达到曝光样本门槛，但未命中视觉、承接、价格信任、产品承诺、需求或放量规则。",
            )

        selected = sorted(matched, key=lambda item: item[0], reverse=True)[0]
        _, node, reason, action, confidence, primary_log = selected
        key = (record.product_id, record.platform, record.channel, reason)
        self.history[key] += 1
        consecutive_hits = self.history[key]

        if action != "放量" and consecutive_hits >= config.eliminate_consecutive_hits:
            action = "淘汰"
            confidence = min(confidence + 0.08, 0.95)
            primary_log += (
                f" 同类问题连续命中 {consecutive_hits} 轮，达到淘汰连续命中轮次 "
                f"{config.eliminate_consecutive_hits}。"
            )

        rule_codes = [rule_code(item[1], item[2]) for item in sorted(matched, key=lambda item: item[0], reverse=True)]
        all_logs = [item[5] for item in sorted(matched, key=lambda item: item[0], reverse=True)]
        return self._decision(
            record,
            node,
            reason,
            action,
            confidence,
            rule_codes,
            "；".join([primary_log, *[log for log in all_logs if log != primary_log]]),
        )

    def _competitor_demand_is_weak(self, record: DailyRecord, config: RuleConfig) -> bool:
        return (
            record.clicks >= config.min_clicks
            and record.competitor_clicks >= config.min_clicks
            and record.conversion_rate < config.low_conversion_rate
            and record.competitor_conversion_rate < config.competitor_low_conversion_rate
        )

    def _can_scale(self, record: DailyRecord, config: RuleConfig) -> bool:
        return (
            record.clicks >= config.min_clicks
            and record.orders >= config.min_orders
            and record.click_rate >= config.scale_click_rate
            and record.conversion_rate >= config.scale_conversion_rate
            and record.refund_rate <= config.scale_refund_rate_max
        )

    def _decision(
        self,
        record: DailyRecord,
        node: str,
        reason: str,
        action: str,
        confidence: float,
        matched_rules: list[str],
        log: str,
    ) -> Decision:
        identity = f"{record.product_id}/{record.platform or '-'} / {record.channel or '-'}"
        return Decision(
            node=node,
            reason=reason,
            action=action,
            confidence=round(confidence, 2),
            matched_rules=matched_rules,
            log=f"{identity}: {log}",
            decided_at=datetime.now(),
        )


def pct(value: float) -> str:
    return f"{value:.2%}"


def rule_code(node: str, reason: str) -> str:
    mapping = {
        ("点击判断", "视觉/首屏吸引力问题"): "low_click_rate_visual",
        ("成交判断", "方向与承接问题"): "low_conversion_positioning_landing",
        ("加购判断", "价格与信任问题"): "low_cart_to_order_price_trust",
        ("退款判断", "产品与承诺问题"): "high_refund_product_promise",
        ("需求判断", "需求不足"): "competitor_weak_demand",
        ("放量判断", "表现达标"): "ready_to_scale",
    }
    return mapping.get((node, reason), "unknown")
