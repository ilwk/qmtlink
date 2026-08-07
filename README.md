# QmtLink

QmtLink 是一个面向 A 股 miniQMT/xtquant 的非官方中转工具，让 Windows 交易机、AI
命令行工具和 Python 量化项目使用同一套交易接口。

主要功能：

- 一条命令启动 Windows miniQMT 中转服务
- 提供默认输出 JSON 的 `qmt` 命令，方便 AI 和自动化脚本调用
- 提供 Python SDK，方便量化项目接入实盘
- 提供 HTTP 接口，隔离策略代码与 Windows miniQMT 环境
- 支持行情、资产、持仓、委托、成交、下单、查单和撤单
- 使用 SQLite 持久化下单幂等记录，降低重复下单风险

> 当前仍是开发预览版。模拟模式、HTTP 接口、命令行和 SDK 已可用；真实交易适配尚未在
> 你的券商 miniQMT 环境验证，请先使用模拟模式，切勿直接用于实盘。

## 安装

全局安装 `qmt` 命令：

```bash
uv tool install qmtlink
```

安装到自己的 Python 量化项目：

```bash
uv add qmtlink
```

不需要填写 `[server]`，也不需要手动追加 xtquant。Windows 会自动安装 xtquant，
Linux 和 macOS 只安装跨平台组件。

## 快速体验

启动不连接真实 miniQMT 的模拟中转服务：

```bash
qmt bridge run --mock
```

在另一个终端执行：

```bash
qmt health
qmt capabilities
qmt market quote --symbol 000001.SZ --symbol 600519.SH
qmt account asset
qmt account positions
qmt order preview --symbol 000001.SZ --side buy --quantity 100 --price 10.50
```

所有命令默认输出 JSON。`qmtlink` 也可以作为 `qmt` 的备用命令。

## 连接 Windows miniQMT

先在 PowerShell 中配置运行参数：

```powershell
$env:QMTLINK_API_KEY = "请替换为随机密钥"
$env:QMTLINK_QMT_PATH = "C:\miniQMT安装目录\userdata_mini"
$env:QMTLINK_ACCOUNT_ID = "请替换为资金账号"
```

检查环境：

```powershell
qmt bridge doctor
```

启动中转服务：

```powershell
qmt bridge run
```

QmtLink 会启动唯一的 XtQuantTrader 运行实例，连接 miniQMT 并订阅账户。真实中转服务建议
使用 Python 3.11～3.13，并先在模拟盘或券商测试环境中验证。

## Python SDK

```python
from qmtlink import QMTClient

with QMTClient(
    "http://127.0.0.1:8000",
    api_key="请替换为与中转服务相同的密钥",
) as client:
    print(client.health())
    print(client.get_quotes(["000001.SZ"]))
    print(client.get_positions())
```

## 交易安全

- 真实下单和撤单默认关闭。
- 服务端必须设置 `QMTLINK_ALLOW_LIVE_ORDERS=true` 才允许提交。
- 命令行还必须显式提供 `--live`。
- 每笔订单必须携带唯一的 `client_order_id`。
- `client_order_id` 会写入 SQLite，重启后仍会阻止重复提交。
- 下单超时后必须先查询订单状态，不能直接重试。
- API 密钥只应通过环境变量或本地配置提供，不要写入命令参数或 Git 仓库。

## 配置项

| 变量 | 默认值 | 用途 |
|---|---|---|
| `QMTLINK_URL` | `http://127.0.0.1:8000` | 命令行和 SDK 访问地址 |
| `QMTLINK_API_KEY` | 空 | 接口访问密钥 |
| `QMTLINK_HOST` | `127.0.0.1` | 中转服务监听地址 |
| `QMTLINK_PORT` | `8000` | 中转服务监听端口 |
| `QMTLINK_MODE` | `real` | `real` 或 `mock` |
| `QMTLINK_ALLOW_LIVE_ORDERS` | `false` | 是否允许真实下单和撤单 |
| `QMTLINK_QMT_PATH` | 空 | Windows `userdata_mini` 完整路径 |
| `QMTLINK_ACCOUNT_ID` | 空 | miniQMT 资金账号 |
| `QMTLINK_ACCOUNT_TYPE` | `STOCK` | xtquant 账号类型 |
| `QMTLINK_SESSION_ID` | 自动生成 | XtQuantTrader 会话编号 |
| `QMTLINK_STRATEGY_NAME` | `qmtlink` | 委托策略名称 |
| `QMTLINK_IDEMPOTENCY_DB` | 用户数据目录 | 下单幂等数据库位置 |

配置示例见 [qmtlink.env.example](qmtlink.env.example)。不要把真实密钥或资金账号提交到
Git 仓库。

## 参与开发

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv build --no-sources
```

后续计划见 [ROADMAP.md](ROADMAP.md)，发版说明见
[docs/RELEASING.md](docs/RELEASING.md)。

## 许可证

本项目使用 MIT 许可证。QmtLink 与 miniQMT、QMT、xtquant 及其权利方不存在官方隶属或
背书关系。
