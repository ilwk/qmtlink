# QmtLink

QmtLink 是一个非官方的 miniQMT/xtquant 跨平台中转项目，提供：

- Windows Bridge 一键启动命令
- 面向 AI 和自动化脚本的 JSON CLI
- 面向 Python 量化项目的 SDK
- HTTP API（实时 WebSocket 将在后续版本加入）

> 当前版本是开发预览版。Mock Bridge、HTTP API、CLI 和 SDK 可用；XtQuantTrader
> 适配代码尚未在你的 Windows 券商环境完成验证，请勿直接用于实盘。

## 安装

客户端和 CLI：

```bash
uv add qmtlink
```

Windows Bridge：

```bash
uv add "qmtlink[server]"
```

## 快速体验

启动 Mock Bridge：

```bash
qmt bridge run --mock
```

另一个终端执行：

```bash
qmt health
qmt capabilities
qmt market quote --symbol 000001.SZ --symbol 600519.SH
qmt account asset
qmt account positions
qmt order preview --symbol 000001.SZ --side buy --quantity 100 --price 10.50
```

所有 CLI 命令默认输出 JSON。`qmtlink` 是 `qmt` 的等价备用命令。

## Python SDK

```python
from qmtlink import QMTClient

with QMTClient("http://127.0.0.1:8000") as client:
    print(client.health())
    print(client.get_quotes(["000001.SZ"]))
```

## Bridge 诊断

```bash
qmt bridge doctor
```

真实模式会延迟导入 xtquant，基础客户端包在 Linux/macOS 上不会导入它：

```powershell
$env:QMTLINK_API_KEY = "replace-with-a-random-secret"
$env:QMTLINK_QMT_PATH = "C:\path\to\miniQMT\userdata_mini"
$env:QMTLINK_ACCOUNT_ID = "your-account-id"

qmt bridge doctor
qmt bridge run
```

Bridge 会启动唯一 XtQuantTrader Runtime，连接 miniQMT 并订阅账户。当前提供资产、持仓、
当日委托、当日成交、下单、订单查询和撤单接口。xtquant 当前要求 Windows x64，真实 Bridge
建议使用 Python 3.11–3.13。

## 安全原则

- 真实交易默认关闭。
- 交易请求必须携带唯一 `client_order_id`。
- `client_order_id` 使用 SQLite 持久化，Bridge 重启后仍会阻止重复提交。
- 下单请求不得在网络超时后盲目重试。
- API Key 通过 `QMTLINK_API_KEY` 提供，不建议放入命令参数。

## 环境变量

| 变量 | 默认值 | 用途 |
|---|---|---|
| `QMTLINK_URL` | `http://127.0.0.1:8000` | CLI/SDK 服务地址 |
| `QMTLINK_API_KEY` | 空 | API Key |
| `QMTLINK_HOST` | `127.0.0.1` | Bridge 监听地址 |
| `QMTLINK_PORT` | `8000` | Bridge 监听端口 |
| `QMTLINK_MODE` | `real` | `real` 或 `mock` |
| `QMTLINK_ALLOW_LIVE_ORDERS` | `false` | 允许提交订单 |
| `QMTLINK_QMT_PATH` | 空 | Windows `userdata_mini` 完整路径 |
| `QMTLINK_ACCOUNT_ID` | 空 | miniQMT 资金账号 |
| `QMTLINK_ACCOUNT_TYPE` | `STOCK` | xtquant 账号类型 |
| `QMTLINK_SESSION_ID` | 自动生成 | XtQuantTrader 会话 ID |
| `QMTLINK_STRATEGY_NAME` | `qmtlink` | 委托策略名 |
| `QMTLINK_IDEMPOTENCY_DB` | 用户数据目录 | 幂等 SQLite 文件位置 |

完整模板见 [qmtlink.env.example](qmtlink.env.example)。不要把真实 API Key 或资金账号提交到
Git 仓库。

## 开发

```bash
uv sync --extra server
uv run pytest
uv run ruff check .
uv build --no-sources
```

开发路线见 [ROADMAP.md](ROADMAP.md)。

发版使用 GitHub Actions 和 PyPI Trusted Publishing，不需要长期保存 PyPI Token。配置和
操作方法见 [docs/RELEASING.md](docs/RELEASING.md)。

## License

MIT。QmtLink 与 miniQMT、QMT、xtquant 及其权利方不存在官方隶属或背书关系。
