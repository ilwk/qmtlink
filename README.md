# QmtLink

QmtLink 是一个非官方的 miniQMT/xtquant 跨平台中转项目，提供：

- Windows Bridge 一键启动命令
- 面向 AI 和自动化脚本的 JSON CLI
- 面向 Python 量化项目的 SDK
- HTTP API（实时 WebSocket 将在后续版本加入）

> 当前版本是开发预览版。Mock Bridge、HTTP API、CLI 和 SDK 可用；真实 miniQMT
> 交易尚未实现，请勿用于实盘。

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

```bash
qmt bridge run
```

## 安全原则

- 真实交易默认关闭。
- 交易请求必须携带唯一 `client_order_id`。
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

## 开发

```bash
uv sync --extra server
uv run pytest
uv run ruff check .
uv build --no-sources
```

开发路线见 [ROADMAP.md](ROADMAP.md)。

## License

MIT。QmtLink 与 miniQMT、QMT、xtquant 及其权利方不存在官方隶属或背书关系。
