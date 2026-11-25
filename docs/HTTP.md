# 接口

- `GET /`：工作台。
- `GET /api/catalog`：阶段、字段和样例。
- `POST /api/stages/{stage}`：按阶段返回处理结果。
- `POST /api/runs`：执行完整批次并保存草稿。
- `GET /api/runs/{id}`：读取批次。
- `POST /api/runs/{id}/review`：签发或暂缓，提交 `decision`、`comment`、`expected_revision`。
- `GET /api/runs/{id}/evidence`：下载已签发证据。
- `GET /api/examples/{profile}`：下载样例。
- `POST /api/resale/quotes`：采信进货报价区间并试算/签发续卖凭据，同一报价幂等。
- `GET /api/resale/eligibility/{sku}`：查询商品能否续卖及凭据状态。
- `POST /api/resale/actual-prices`：登记实价；超出已采信区间时立即失效旧凭据。
- `POST /api/resale/shipments` / `GET /api/resale/shipments`：记录和查询冻结的已出货毛利。
- `POST /api/resale/products/{sku}/rerun`：用已采信报价重算资格，不新增凭据、不恢复已失效资格、不改出货快照。
- `GET /healthz`：健康检查。
