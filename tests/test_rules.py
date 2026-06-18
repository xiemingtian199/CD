import unittest

from cd_racing_monitor.pipeline import evaluate_items


RULES = [{"fields": {"最小曝光": 300, "最小点击": 20, "最小加购": 5, "最小成交": 5}}]


def decision_for(fields):
    result = evaluate_items([{"record_id": "rec", "fields": {"产品ID": "P001", **fields}}], RULES)
    return result[0][1]


class RuleEngineTest(unittest.TestCase):
    def test_low_click_rate_suggests_visual_change(self):
        decision = decision_for({"曝光": 1000, "点击": 5})
        self.assertEqual(decision.reason, "视觉/首屏吸引力问题")
        self.assertEqual(decision.action, "改视觉")

    def test_clicks_without_orders_suggests_landing_change(self):
        decision = decision_for({"曝光": 1000, "点击": 80, "成交": 0})
        self.assertEqual(decision.reason, "方向与承接问题")
        self.assertEqual(decision.action, "改承接")

    def test_add_to_cart_without_order_suggests_price_trust_change(self):
        decision = decision_for({"曝光": 1000, "点击": 100, "加购": 20, "成交": 1})
        self.assertEqual(decision.reason, "价格与信任问题")
        self.assertEqual(decision.action, "调价格/信任")

    def test_high_refund_suggests_product_promise_change(self):
        decision = decision_for({"曝光": 1000, "点击": 120, "加购": 30, "成交": 10, "退款": 4})
        self.assertEqual(decision.reason, "产品与承诺问题")
        self.assertEqual(decision.action, "修产品/承诺")

    def test_competitor_weak_demand_suggests_retest(self):
        decision = decision_for({"曝光": 1000, "点击": 100, "成交": 0, "竞品点击": 100, "竞品成交": 0})
        self.assertEqual(decision.reason, "需求不足")
        self.assertEqual(decision.action, "复测")

    def test_sample_insufficient_observes(self):
        decision = decision_for({"曝光": 20, "点击": 1})
        self.assertEqual(decision.reason, "数据量不足")
        self.assertEqual(decision.action, "继续观察")

    def test_positive_metrics_suggest_scale(self):
        decision = decision_for({"曝光": 1000, "点击": 80, "加购": 20, "成交": 8, "退款": 0})
        self.assertEqual(decision.reason, "表现达标")
        self.assertEqual(decision.action, "放量")


if __name__ == "__main__":
    unittest.main()
