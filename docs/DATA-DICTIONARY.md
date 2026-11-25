# 字段定义

| 字段 | 类型 | 说明 |
|---|---|---|
| `sku` | text | 主键 |
| `line_qty` | int_positive | 业务字段 |
| `list_price_cents` | int | 业务字段 |
| `sell_price_cents` | int | 业务字段 |
| `supplier_fund_cents` | int | 业务字段 |
| `coupon_cents` | int | 业务字段 |
| `unit_cost_cents` | int | 业务字段 |

空字符串、`-`、`NA`、`null` 和 `未提供` 按空值处理。金额字段在整理层转为整数分或整数最小单位；日期按 ISO 日期解析；带时间的字段按本地时间解析。标识字段保持为文本，前导零不会被去除。

## 续卖报价字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `sku` | text | 商品主键 |
| `sell_price_cents` | int | 促销售价（分） |
| `quote_low_cents` / `quote_high_cents` | int | 已采信进货报价区间上下限（分） |
| `margin_floor_cents` | int | 可选的单位毛利底线（分） |
| `margin_floor_rate` | decimal | 可选的毛利率底线；省略金额底线时沿用 0.20 |
| `actual_cost_cents` | int | 实际进货价/成本（分） |
| `can_resell` | bool | 工作台续卖资格结论 |
| `credential_count` | int | 该商品的凭据总数，用于校验重跑不新增 |
