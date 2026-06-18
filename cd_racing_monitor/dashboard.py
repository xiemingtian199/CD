from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import html
import json
from pathlib import Path
from typing import Any

from .config import AppConfig
from .feishu import FeishuClient
from .normalizer import as_number, as_text


@dataclass
class DashboardResult:
    output_path: Path
    product_count: int
    row_count: int
    latest_date: str


class DashboardBuilder:
    def __init__(self, config: AppConfig, output_path: str | Path, logger) -> None:
        self.config = config
        self.output_path = Path(output_path)
        self.logger = logger
        self.client = FeishuClient(config.feishu)

    def build(self) -> DashboardResult:
        rows = [normalize_row(item.get("fields", {})) for item in self.client.list_records(self.config.feishu.daily_table_id, page_size=100)]
        rows = [row for row in rows if row["product_id"] and row["date"]]
        rankings = build_rankings(rows)
        trends = build_trends(rows, rankings)
        payload = {
            "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "latestDate": max((row["date"] for row in rows), default=""),
            "rowCount": len(rows),
            "productCount": len(rankings),
            "rankings": rankings,
            "trends": trends,
        }
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(render_html(payload), encoding="utf-8")
        return DashboardResult(
            output_path=self.output_path,
            product_count=len(rankings),
            row_count=len(rows),
            latest_date=payload["latestDate"],
        )


def normalize_row(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": normalize_date(fields.get("日期")),
        "product_id": as_text(fields.get("产品ID")),
        "product_name": as_text(fields.get("产品名")),
        "platform": as_text(fields.get("平台")) or "未知平台",
        "visitors": number(fields.get("点击")),
        "sales": number(fields.get("成交金额")),
        "orders": number(fields.get("成交")),
        "source": as_text(fields.get("数据来源")),
    }


def normalize_date(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    text = as_text(value)
    try:
        return datetime.fromisoformat(text).strftime("%Y-%m-%d")
    except Exception:
        return text[:10]


def number(value: Any) -> float:
    try:
        return float(as_number(value))
    except Exception:
        return 0.0


def build_rankings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    platform_totals: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: {"visitors": 0.0, "sales": 0.0}))
    for row in rows:
        product_id = row["product_id"]
        item = grouped.setdefault(
            product_id,
            {
                "productId": product_id,
                "productName": row["product_name"] or product_id,
                "visitors": 0.0,
                "sales": 0.0,
                "orders": 0.0,
                "platforms": set(),
            },
        )
        item["visitors"] += row["visitors"]
        item["sales"] += row["sales"]
        item["orders"] += row["orders"]
        item["platforms"].add(row["platform"])
        platform_totals[product_id][row["platform"]]["visitors"] += row["visitors"]
        platform_totals[product_id][row["platform"]]["sales"] += row["sales"]

    rankings = sorted(grouped.values(), key=lambda item: (item["sales"], item["visitors"]), reverse=True)
    for index, item in enumerate(rankings, start=1):
        item["rank"] = index
        item["platforms"] = sorted(item["platforms"])
        item["platformSummary"] = [
            {
                "platform": platform,
                "visitors": round(values["visitors"], 2),
                "sales": round(values["sales"], 2),
            }
            for platform, values in sorted(platform_totals[item["productId"]].items())
        ]
        item["visitors"] = round(item["visitors"], 2)
        item["sales"] = round(item["sales"], 2)
        item["orders"] = round(item["orders"], 2)
    return rankings


def build_trends(rows: list[dict[str, Any]], rankings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank_ids = [item["productId"] for item in rankings]
    grouped: dict[tuple[str, str, str], dict[str, float]] = defaultdict(lambda: {"visitors": 0.0, "sales": 0.0})
    product_name = {row["product_id"]: row["product_name"] or row["product_id"] for row in rows}
    for row in rows:
        key = (row["product_id"], row["date"], row["platform"])
        grouped[key]["visitors"] += row["visitors"]
        grouped[key]["sales"] += row["sales"]

    output = []
    for product_id in rank_ids:
        points = [
            {
                "date": date,
                "platform": platform,
                "visitors": round(values["visitors"], 2),
                "sales": round(values["sales"], 2),
            }
            for (pid, date, platform), values in grouped.items()
            if pid == product_id
        ]
        output.append(
            {
                "productId": product_id,
                "productName": product_name.get(product_id, product_id),
                "points": sorted(points, key=lambda item: (item["date"], item["platform"])),
            }
        )
    return output


def render_html(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    title = "CD级产品赛马仪表盘"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --text: #18202a;
      --muted: #677385;
      --line: #d9dee7;
      --blue: #2563eb;
      --green: #0f9f6e;
      --orange: #d97706;
      --red: #dc2626;
      --purple: #7c3aed;
      --cyan: #0891b2;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
      line-height: 1.45;
    }}
    header {{
      padding: 24px 28px 14px;
      border-bottom: 1px solid var(--line);
      background: #fff;
      position: sticky;
      top: 0;
      z-index: 5;
    }}
    h1 {{ margin: 0 0 8px; font-size: 24px; letter-spacing: 0; }}
    .meta {{ color: var(--muted); font-size: 13px; }}
    main {{ max-width: 1480px; margin: 0 auto; padding: 20px 24px 40px; }}
    .kpis {{ display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: 12px; margin-bottom: 18px; }}
    .kpi, .section, .chart-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
    }}
    .kpi {{ padding: 14px 16px; }}
    .kpi-label {{ color: var(--muted); font-size: 12px; margin-bottom: 4px; }}
    .kpi-value {{ font-size: 24px; font-weight: 700; }}
    .section {{ margin-bottom: 18px; overflow: hidden; }}
    .section h2 {{ font-size: 18px; margin: 0; padding: 16px 18px 10px; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 9px 10px; border-top: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ background: #f0f3f7; color: #334155; font-weight: 700; white-space: nowrap; }}
    td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .product-cell {{ min-width: 220px; }}
    .platform-list {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}
    .charts {{ display: grid; grid-template-columns: 1fr; gap: 14px; }}
    .chart-card {{ padding: 14px 16px 12px; }}
    .chart-head {{ display: flex; justify-content: space-between; gap: 12px; align-items: baseline; margin-bottom: 8px; }}
    .chart-title {{ font-weight: 700; font-size: 15px; }}
    .chart-subtitle {{ color: var(--muted); font-size: 12px; }}
    .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
    .chart-box {{ min-height: 260px; }}
    .axis-label {{ fill: #64748b; font-size: 11px; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 8px 14px; margin-top: 6px; color: var(--muted); font-size: 12px; }}
    .legend span {{ display: inline-flex; align-items: center; gap: 5px; }}
    .swatch {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
    .empty {{ color: var(--muted); padding: 28px; text-align: center; }}
    .source {{ color: var(--muted); font-size: 12px; padding: 12px 18px 16px; border-top: 1px solid var(--line); }}
    @media (max-width: 920px) {{
      header {{ padding: 18px 16px 12px; }}
      main {{ padding: 14px 12px 28px; }}
      .kpis {{ grid-template-columns: repeat(2, minmax(140px, 1fr)); }}
      .chart-grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 560px) {{
      .kpis {{ grid-template-columns: 1fr; }}
      .kpi-value {{ font-size: 21px; }}
      h1 {{ font-size: 20px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(title)}</h1>
    <div class="meta" id="meta"></div>
  </header>
  <main>
    <section class="kpis" id="kpis"></section>
    <section class="section">
      <h2>总体产品排行</h2>
      <div class="table-wrap" id="ranking"></div>
      <div class="source">排序规则：销售额降序，销售额相同时按访客数降序。访客数使用每日数据表的“点击”字段，销售额使用“成交金额”字段。</div>
    </section>
    <section class="charts" id="charts"></section>
  </main>
  <script id="dashboard-data" type="application/json">{data}</script>
  <script>
    const data = JSON.parse(document.getElementById('dashboard-data').textContent);
    const colors = ['#2563eb', '#0f9f6e', '#d97706', '#dc2626', '#7c3aed', '#0891b2', '#64748b'];
    const fmt = new Intl.NumberFormat('zh-CN', {{ maximumFractionDigits: 0 }});
    const money = new Intl.NumberFormat('zh-CN', {{ style: 'currency', currency: 'CNY', maximumFractionDigits: 0 }});

    document.getElementById('meta').textContent = `数据来源：飞书每日数据表 · 最新日期：${{data.latestDate || '无'}} · 生成时间：${{data.generatedAt}}`;

    const totals = data.rankings.reduce((acc, row) => {{
      acc.visitors += row.visitors;
      acc.sales += row.sales;
      acc.orders += row.orders;
      return acc;
    }}, {{ visitors: 0, sales: 0, orders: 0 }});
    const kpis = [
      ['产品数', fmt.format(data.productCount)],
      ['数据行数', fmt.format(data.rowCount)],
      ['访客数合计', fmt.format(totals.visitors)],
      ['销售额合计', money.format(totals.sales)]
    ];
    document.getElementById('kpis').innerHTML = kpis.map(([label, value]) => `
      <div class="kpi"><div class="kpi-label">${{escapeHtml(label)}}</div><div class="kpi-value">${{escapeHtml(value)}}</div></div>
    `).join('');

    renderRanking();
    renderCharts();

    function renderRanking() {{
      if (!data.rankings.length) {{
        document.getElementById('ranking').innerHTML = '<div class="empty">暂无可展示数据</div>';
        return;
      }}
      const rows = data.rankings.map(row => `
        <tr>
          <td class="num">${{row.rank}}</td>
          <td class="product-cell">
            <strong>${{escapeHtml(row.productName)}}</strong>
            <div class="platform-list">${{escapeHtml(row.productId)}} · ${{escapeHtml(row.platforms.join(' / '))}}</div>
          </td>
          <td class="num">${{fmt.format(row.visitors)}}</td>
          <td class="num">${{money.format(row.sales)}}</td>
          <td class="num">${{fmt.format(row.orders)}}</td>
          <td>${{row.platformSummary.map(p => `${{escapeHtml(p.platform)}}：${{fmt.format(p.visitors)}}访客 / ${{money.format(p.sales)}}`).join('<br>')}}</td>
        </tr>
      `).join('');
      document.getElementById('ranking').innerHTML = `
        <table>
          <thead>
            <tr>
              <th class="num">排名</th>
              <th>产品</th>
              <th class="num">访客数</th>
              <th class="num">销售额</th>
              <th class="num">成交</th>
              <th>平台汇总</th>
            </tr>
          </thead>
          <tbody>${{rows}}</tbody>
        </table>
      `;
    }}

    function renderCharts() {{
      const target = document.getElementById('charts');
      target.innerHTML = data.trends.map((product, index) => {{
        const ranking = data.rankings[index];
        return `
          <article class="chart-card">
            <div class="chart-head">
              <div>
                <div class="chart-title">#${{index + 1}} ${{escapeHtml(product.productName)}}</div>
                <div class="chart-subtitle">${{escapeHtml(product.productId)}} · 访客 ${{fmt.format(ranking.visitors)}} · 销售额 ${{money.format(ranking.sales)}}</div>
              </div>
            </div>
            <div class="chart-grid">
              <div class="chart-box">${{lineChart(product.points, 'visitors', '访客数')}}</div>
              <div class="chart-box">${{lineChart(product.points, 'sales', '销售额')}}</div>
            </div>
          </article>
        `;
      }}).join('');
    }}

    function lineChart(points, metric, label) {{
      const width = 620, height = 250, pad = {{ left: 44, right: 16, top: 22, bottom: 36 }};
      const dates = [...new Set(points.map(p => p.date))].sort();
      const platforms = [...new Set(points.map(p => p.platform))].sort();
      const valuesByPlatform = new Map();
      platforms.forEach(platform => {{
        const byDate = new Map(points.filter(p => p.platform === platform).map(p => [p.date, Number(p[metric] || 0)]));
        valuesByPlatform.set(platform, dates.map(date => ({{ date, value: byDate.get(date) || 0 }})));
      }});
      const maxValue = Math.max(1, ...points.map(p => Number(p[metric] || 0)));
      const plotW = width - pad.left - pad.right;
      const plotH = height - pad.top - pad.bottom;
      const x = date => pad.left + (dates.length <= 1 ? plotW / 2 : dates.indexOf(date) * plotW / (dates.length - 1));
      const y = value => pad.top + plotH - (value / maxValue) * plotH;
      const yTicks = [0, maxValue / 2, maxValue];
      const grid = yTicks.map(tick => `
        <line x1="${{pad.left}}" x2="${{width - pad.right}}" y1="${{y(tick)}}" y2="${{y(tick)}}" stroke="#e5e7eb" />
        <text class="axis-label" x="${{pad.left - 8}}" y="${{y(tick) + 4}}" text-anchor="end">${{metric === 'sales' ? shortMoney(tick) : shortNum(tick)}}</text>
      `).join('');
      const xLabels = dates.map(date => `
        <text class="axis-label" x="${{x(date)}}" y="${{height - 12}}" text-anchor="middle">${{date.slice(5)}}</text>
      `).join('');
      const lines = platforms.map((platform, idx) => {{
        const values = valuesByPlatform.get(platform);
        const d = values.map((point, i) => `${{i === 0 ? 'M' : 'L'}} ${{x(point.date).toFixed(1)}} ${{y(point.value).toFixed(1)}}`).join(' ');
        const circles = values.map(point => `<circle cx="${{x(point.date)}}" cy="${{y(point.value)}}" r="3" fill="${{colors[idx % colors.length]}}"><title>${{platform}} ${{point.date}}: ${{metric === 'sales' ? money.format(point.value) : fmt.format(point.value)}}</title></circle>`).join('');
        return `<path d="${{d}}" fill="none" stroke="${{colors[idx % colors.length]}}" stroke-width="2.4" />${{circles}}`;
      }}).join('');
      const legend = platforms.map((platform, idx) => `<span><i class="swatch" style="background:${{colors[idx % colors.length]}}"></i>${{escapeHtml(platform)}}</span>`).join('');
      return `
        <svg viewBox="0 0 ${{width}} ${{height}}" width="100%" height="250" role="img" aria-label="${{escapeHtml(label)}}趋势">
          <text x="${{pad.left}}" y="15" font-size="13" font-weight="700" fill="#18202a">${{escapeHtml(label)}}</text>
          ${{grid}}
          <line x1="${{pad.left}}" y1="${{height - pad.bottom}}" x2="${{width - pad.right}}" y2="${{height - pad.bottom}}" stroke="#cbd5e1" />
          ${{xLabels}}
          ${{lines}}
        </svg>
        <div class="legend">${{legend}}</div>
      `;
    }}

    function shortNum(value) {{
      if (value >= 10000) return `${{(value / 10000).toFixed(1)}}万`;
      return fmt.format(value);
    }}
    function shortMoney(value) {{
      if (value >= 10000) return `¥${{(value / 10000).toFixed(1)}}万`;
      return `¥${{fmt.format(value)}}`;
    }}
    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
    }}
  </script>
</body>
</html>"""
