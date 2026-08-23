# QmtLink

QmtLink 是一个运行在 Windows miniQMT 交易机上的非官方 HTTP bridge。它只做两件事：

1. 通过 xtquant 与本机 miniQMT 通讯；
2. 向局域网内的调用方提供稳定、版本化的 HTTP API。

调用方直接使用 HTTP API，不需要安装 QmtLink Python SDK，也不需要使用 QmtLink 客户端命令。
策略、回测和业务数据转换应留在调用方项目中。

QmtLink 对外使用 `buy`、`sell`、`limit` 等可读字段，在 bridge 内部统一转换为 xtquant
常量。查询结果同时保留 `broker_*` 原始值和标准化字段，避免把券商数字常量扩散到调用方。

> **开发阶段声明：** QmtLink 当前仍处于开发预览阶段，HTTP 接口和数据字段可能继续调整。
> 不建议直接用于生产环境或无人值守实盘。真实交易前请先在模拟盘或券商测试环境中验证。

## 职责范围

QmtLink 包含：

- FastAPI HTTP server；
- miniQMT/xtquant 行情、账户与交易适配；
- 请求校验、统一错误响应和 OpenAPI 文档；
- 行情与交易事件续读；
- SQLite 下单幂等保护；
- 真实交易开关。

QmtLink 不包含客户端 SDK、客户端 CLI、策略、回测、因子、GUI、数据仓库或任意 xtquant
对象代理。

## 安装与启动

在 Windows miniQMT 交易机上使用 Python 3.13 安装：

```powershell
uv tool install qmtlink --python 3.13
```

第一次运行：

```powershell
qmtlink
```

QmtLink 会生成 `~/.config/qmtlink/config.toml`，然后提示配置 miniQMT 路径和资金账号。
打开配置文件，至少填写：

```toml
api_key = "自动生成的密钥，请保留"

[server]
qmt_path = 'C:\miniQMT安装目录\userdata_mini'
account_id = "你的资金账号"
```

保存后再次启动：

```powershell
qmtlink
```

bridge 默认监听 `0.0.0.0:8000`，使用单个 XtQuantTrader 实例连接并订阅 miniQMT 账户。
不要把端口直接暴露到公网。

升级使用：

```powershell
uv tool upgrade qmtlink
```

也可以使用 `python -m qmtlink` 启动。生产运行时应由 Windows 服务管理器或你自己的进程
管理工具负责自动启动和重启。

## 直接调用 HTTP API

所有 API 请求都必须携带配置文件中的 API key：

```text
X-API-Key: <api_key>
```

健康检查：

```bash
curl \
  -H 'X-API-Key: <api_key>' \
  http://192.168.1.150:8000/api/v1/health
```

查询持仓：

```bash
curl \
  -H 'X-API-Key: <api_key>' \
  http://192.168.1.150:8000/api/v1/account/positions
```

读取历史日线：

```bash
curl \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: <api_key>' \
  -d '{"symbols":["000001.SZ"],"period":"1d","start_time":"20200101","end_time":"20241231","dividend_type":"front_ratio"}' \
  http://192.168.1.150:8000/api/v1/market/history
```

启动后可在 `http://<bridge-host>:8000/docs` 查看 OpenAPI 交互文档，在
`/openapi.json` 获取机器可读的接口定义。

### 响应格式

成功响应：

```json
{
  "ok": true,
  "request_id": "req_...",
  "data": {},
  "meta": {"elapsed_ms": 1.234}
}
```

失败响应：

```json
{
  "ok": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "error detail",
    "retryable": false
  }
}
```

调用方应按 `error.code` 和 `retryable` 处理错误，不要依赖自然语言错误文本。

### 接口概览

- `GET /api/v1/health`：bridge 与 miniQMT 连接状态；
- `GET /api/v1/capabilities`：bridge 能力；
- `POST /api/v1/market/quotes`：行情快照；
- `POST /api/v1/market/history`：历史 tick/K 线；
- `POST /api/v1/market/instruments`：合约信息；
- `POST /api/v1/market/financial`：财务数据；
- `POST /api/v1/market/dividends`：除权除息数据；
- `POST /api/v1/market/historical-st`：历史 ST 区间；
- `POST /api/v1/market/sectors`：板块成分股；
- `POST /api/v1/market/subscriptions`：订阅实时行情；
- `GET /api/v1/events`：续读行情、委托、成交和账户事件；
- `GET /api/v1/account/asset`：账户资产；
- `GET /api/v1/account/positions`：持仓；
- `GET /api/v1/account/orders`：当日委托；
- `GET /api/v1/account/trades`：当日成交；
- `POST /api/v1/orders/preview`：校验订单并预估金额；
- `POST /api/v1/orders`：下单；
- `GET /api/v1/orders/{order_id}`：查询订单；
- `POST /api/v1/orders/{order_id}/cancel`：撤单。

## 历史数据约定

`POST /api/v1/market/history` 默认返回 xtdata 原始字段，数据按 `bars[symbol]` 分组。常用字段
包括 `time`、`open`、`high`、`low`、`close`、`volume`、`amount`、`preClose` 和
`suspendFlag`。日线额外提供 `date`（`YYYYMMDD` 整数）。

请求默认先读取 xtdata 本地缓存；没有缓存时才补充历史数据并重新读取。`fill_data` 默认关闭，
复权方式默认 `none`。接口接受 QMT 常用的 `.SH`，也接受 AKQuant/StockDB 使用的 `.SS`，返回
时保留请求中的代码形式。

财务回测应使用 `report_type = "announce_time"`。历史涨跌停价使用历史行情的
`stoppricedata` 周期。部分数据取决于 miniQMT 本地缓存和账号权限。

## 事件续读

事件接口使用单调递增序号。调用方只有在成功处理一批事件后才保存 `next_sequence`，短暂断线
后从该序号继续请求。

如果游标早于服务端保留窗口，接口返回 `EVENT_CURSOR_EXPIRED`；如果 bridge 重启导致旧游标
超前，返回 `EVENT_CURSOR_INVALID`。两种情况都需要重新查询账户、持仓、当日委托和成交，
再恢复事件消费。事件日志位于内存，不承诺跨进程重启续读。

## 交易安全

- 当前只开放限价单；
- 真实下单和撤单默认关闭；
- 配置文件必须设置 `allow_trading = true`；
- 下单和撤单请求还必须携带 `live = true`；
- 每笔订单必须携带唯一的 `client_order_id`；
- `client_order_id` 写入 SQLite，bridge 重启后仍会阻止重复提交；
- 下单超时后必须先查询订单状态，不能直接重试。

## 配置

默认配置文件为 `~/.config/qmtlink/config.toml`，幂等数据库位于同一目录的
`orders.sqlite3`。完整模板见 [src/qmtlink/config.template.toml](src/qmtlink/config.template.toml)。

| 配置项 | 环境变量覆盖 | 默认值 | 说明 |
|---|---|---|---|
| `api_key` | `QMTLINK_API_KEY` | 首次运行自动生成 | HTTP API 密钥 |
| `server.qmt_path` | `QMTLINK_QMT_PATH` | 空 | miniQMT `userdata_mini` 完整路径 |
| `server.account_id` | `QMTLINK_ACCOUNT_ID` | 空 | 资金账号 |
| `server.account_type` | `QMTLINK_ACCOUNT_TYPE` | `STOCK` | 账户类型 |
| `server.strategy_name` | `QMTLINK_STRATEGY_NAME` | `qmtlink` | 写入委托记录的策略名 |
| `server.host` | `QMTLINK_HOST` | `0.0.0.0` | HTTP 监听地址 |
| `server.port` | `QMTLINK_PORT` | `8000` | HTTP 监听端口 |
| `server.allow_trading` | `QMTLINK_ALLOW_TRADING` | `false` | 是否允许真实下单和撤单 |

配置优先级为：环境变量、`config.toml`、程序默认值。可用 `QMTLINK_CONFIG` 指定其他配置文件。

## 开发

```bash
uv sync --locked --dev
uv run pytest
uv run ruff check .
uv build --no-sources
```

后续计划见 [ROADMAP.md](ROADMAP.md)，发版说明见 [docs/RELEASING.md](docs/RELEASING.md)。

## 许可证

QmtLink 使用 MIT 许可证，与 miniQMT、QMT、xtquant 及其权利方不存在官方隶属或背书关系。
