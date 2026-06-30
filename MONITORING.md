# Competitor Monitor Notes

这个脚本用于监控美妆竞品独立站的新品/商品发布信号，并把周报推送到 Lark。

## 数据可信度

- `high`: 品牌独立站公开接口，例如 Shopify Atom feed 和 `products.json` 的 `published_at` / `created_at`。
- `medium`: Google News RSS 搜索结果，只能当趋势线索，必须人工点开原文复核。
- 默认不使用 `products.json.updated_at` 判断新品，因为很多 Shopify 店铺会批量更新旧商品，容易误报。

## 常用环境变量

- `LARK_WEBHOOK_URL`: Lark 自定义机器人 webhook。
- `DEEPSEEK_API_KEY`: DeepSeek API key。缺失时会发送规则化兜底报告，不会编造内容。
- `LOOKBACK_DAYS`: 回看天数，默认 `7`。
- `MAX_PRODUCTS_PER_BRAND`: 每个品牌最多进入报告的商品数，默认 `6`。
- `MAX_TRENDS_PER_QUERY`: 每个趋势搜索词最多保留的新闻线索数，默认 `3`。
- `DISABLE_AI=1`: 跳过 DeepSeek，只生成规则化报告，适合调试。
- `INCLUDE_PRODUCT_UPDATES=1`: 允许把 `products.json.updated_at` 纳入商品更新信号；默认关闭。
- `EXCLUDE_PRODUCT_PATTERN`: 过滤赠品、样品、物流保护等噪声商品的正则表达式。

## 输出

每次运行会生成：

- `snapshots/latest_competitor_snapshot.json`
- `snapshots/competitor_snapshot_YYYYMMDD_HHMMSSZ.json`

GitHub Actions 会把这些文件上传为 artifact，方便追溯 Lark 周报里的原始证据。

## 本地调试

```powershell
$env:DISABLE_AI='1'
$env:LOOKBACK_DAYS='7'
python competitor_monitor.py
```

如果只想在 Lark 里收到更短的报告，可以降低 `MAX_PRODUCTS_PER_BRAND` 或 `MAX_TRENDS_PER_QUERY`。
