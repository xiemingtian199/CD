from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class DailyRecord:
    record_id: str
    date: date | None
    product_id: str
    product_name: str = ""
    category: str = ""
    platform: str = ""
    channel: str = ""
    impressions: float = 0
    clicks: float = 0
    add_to_cart: float = 0
    orders: float = 0
    revenue: float = 0
    refunds: float = 0
    competitor_impressions: float = 0
    competitor_clicks: float = 0
    competitor_orders: float = 0
    competitor_note: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def click_rate(self) -> float:
        return safe_div(self.clicks, self.impressions)

    @property
    def add_to_cart_rate(self) -> float:
        return safe_div(self.add_to_cart, self.clicks)

    @property
    def conversion_rate(self) -> float:
        return safe_div(self.orders, self.clicks)

    @property
    def add_to_cart_conversion_rate(self) -> float:
        return safe_div(self.orders, self.add_to_cart)

    @property
    def refund_rate(self) -> float:
        return safe_div(self.refunds, self.orders)

    @property
    def average_order_value(self) -> float:
        return safe_div(self.revenue, self.orders)

    @property
    def competitor_conversion_rate(self) -> float:
        return safe_div(self.competitor_orders, self.competitor_clicks)


@dataclass
class RuleConfig:
    platform: str = ""
    category: str = ""
    channel: str = ""
    min_impressions: float = 300
    min_clicks: float = 20
    min_add_to_cart: float = 5
    min_orders: float = 5
    low_click_rate: float = 0.01
    low_conversion_rate: float = 0.01
    low_cart_to_order_rate: float = 0.15
    high_refund_rate: float = 0.25
    competitor_low_conversion_rate: float = 0.005
    scale_click_rate: float = 0.03
    scale_conversion_rate: float = 0.03
    scale_refund_rate_max: float = 0.12
    eliminate_consecutive_hits: int = 3

    def specificity(self) -> int:
        return sum(bool(value) for value in (self.platform, self.category, self.channel))


@dataclass
class Decision:
    node: str
    reason: str
    action: str
    confidence: float
    matched_rules: list[str]
    log: str
    decided_at: datetime
    should_write: bool = True


def safe_div(numerator: float, denominator: float) -> float:
    if denominator in (0, 0.0):
        return 0.0
    return numerator / denominator
