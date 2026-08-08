# QmtLink

QmtLink 是一个面向 A 股 miniQMT/xtquant 的非官方中转工具，让 Windows 交易机、AI
命令行工具和 Python 量化项目使用同一套交易接口。

主要功能：

- 一条命令启动 Windows miniQMT 中转服务
- 提供默认输出 JSON 的 `qmt` 命令，方便 AI 和自动化脚本调用
- 提供 Python SDK，方便量化项目接入实盘
- 提供 HTTP 接口，隔离策略代码与 Windows miniQMT 环境
- 支持行情、资产、持仓、委托、成交、下单、查单和撤单
- 支持带单调游标的行情、委托、成交和账户事件续读
- 使用 SQLite 持久化下单幂等记录，降低重复下单风险

QmtLink 对外使用 `buy`、`sell`、`limit` 等可读字段，在 bridge 内部统一转换为 xtquant
常量。查询结果同时保留 `broker_*` 原始值和标准化字段，方便排查券商差异，但不把 xtquant
数字常量扩散到 CLI 和量化策略中。

> 当前仍是开发预览版。模拟模式、HTTP 接口、命令行和 SDK 已可用；真实交易适配尚未在
> 你的券商 miniQMT 环境验证，请先使用模拟模式，切勿直接用于实盘。

## 安装

在普通电脑上安装 `qmt` 命令，只包含 Client：

```bash
uv tool install qmtlink
```

安装后可使用下面的命令更新到 PyPI 上的最新版本：

```bash
qmt update
```

在 Windows miniQMT 交易机上安装 Bridge：

```powershell
uv tool install "qmtlink[server]" --python 3.13
```

安装到自己的 Python 量化项目：

```bash
uv add qmtlink
```

## 快速体验

安装 Bridge 后直接启动。未配置 miniQMT 账号时会自动使用 Mock 模式：

```bash
qmt bridge run
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

第一次运行时会自动生成配置文件和随机 API 密钥。也可以使用
`qmt bridge run --mock` 强制进入 Mock 模式。所有命令默认输出 JSON，`qmtlink` 也可以
作为 `qmt` 的备用命令。

## 连接 Windows miniQMT

直接运行：

```powershell
qmt bridge run
```

QmtLink 第一次运行会自动生成配置文件，以 Mock 模式启动，并在输出中显示文件位置。按
`Ctrl+C` 停止服务，打开配置文件，只需填写：

```toml
qmt_path = 'C:\miniQMT安装目录\userdata_mini'
account_id = "你的资金账号"
```

保存后再次运行：

```powershell
qmt bridge run
```

不需要自己生成 API 密钥，也不需要设置环境变量。可使用 `qmt bridge doctor` 检查当前配置和
运行环境。

QmtLink 会启动唯一的 XtQuantTrader 运行实例，连接 miniQMT 并订阅账户。真实中转服务建议
使用 Python 3.13，并先在模拟盘或券商测试环境中验证。Client 不受 xtquant 的 Python 版本
上限影响。

## Python SDK

```python
from qmtlink import QMTClient

with QMTClient() as client:
    print(client.health())
    subscription = client.subscribe_quotes(["000001.SZ"])
    events = client.poll_events(after_sequence=subscription.cursor, timeout=20)
    print(events.events)
    print(client.get_positions())
```

事件接口使用单调递增序号；客户端只有在成功处理一批事件后才保存
`next_sequence`。短暂断线后从该序号继续轮询，不需要猜测断线期间是否漏掉成交。事件还
包含 `order_error` 和 `cancel_error`，调用方必须显式处理失败回报。若游标早于服务端保留
窗口，接口返回 `EVENT_CURSOR_EXPIRED`；若 QmtLink 服务进程重启导致旧游标超前，则返回
`EVENT_CURSOR_INVALID`。两种情况都必须重新查询账户、持仓、当日委托和成交后再恢复事件
消费。事件日志位于内存，不承诺跨服务进程重启续读。

量化项目与 bridge 在同一台机器时，SDK 会自动读取同一份配置。分开部署时，在量化项目机器
的配置文件中设置 `url`，并使用与 bridge 相同的 `api_key`。

## 交易安全

- 当前只开放限价单；不同交易所的市价类型规则不同，在完成真实环境验证前不做模糊映射。
- 真实下单和撤单默认关闭。
- 配置文件必须增加 `allow_trading = true` 才允许提交。
- 命令行还必须显式提供 `--live`。
- 每笔订单必须携带唯一的 `client_order_id`。
- `client_order_id` 会写入 SQLite，重启后仍会阻止重复提交。
- 下单超时后必须先查询订单状态，不能直接重试。
- API 密钥由 QmtLink 自动生成并保存在本地配置中，不要提交到 Git 仓库。

## 配置项

默认配置文件位置：

- Windows/Linux/macOS：`~/.config/qmtlink/config.toml`

配置文件使用扁平的 TOML 格式，不需要添加 `[bridge]` 或 `[client]`。首次执行
`qmt bridge run` 时，QmtLink 会生成以下最小配置：

```toml
api_key = "自动生成的随机密钥"
qmt_path = ""
account_id = ""
```

普通股票账户只需填写 `qmt_path` 和 `account_id`。两项都为空时自动使用 Mock 模式，两项
都填写后自动使用真实模式；只填写一项会报告配置错误。自动生成的 `api_key` 应保留原值。

### 完整示例

下面包含所有支持的配置项。`session_id` 和 `idempotency_db` 通常无需设置，因此保持注释即可。

```toml
# CLI、SDK 和 bridge 共用的访问密钥，请勿泄露。
api_key = "自动生成的随机密钥"

# miniQMT 配置。
qmt_path = 'C:\miniQMT安装目录\userdata_mini'
account_id = "你的资金账号"
account_type = "STOCK"
strategy_name = "qmtlink"

# bridge 服务配置。
host = "127.0.0.1"
port = 8000
allow_trading = false

# CLI 和 Python SDK 的 HTTP 客户端配置。
url = "http://127.0.0.1:8000"
timeout = 30.0

# 高级配置：不填写时由 QmtLink 自动处理。
# session_id = 123456
# idempotency_db = 'C:\Users\你的用户名\AppData\Local\QmtLink\orders.sqlite3'
```

### 字段说明

| 配置项 | 环境变量覆盖 | 默认值 | 说明 |
|---|---|---|---|
| `api_key` | `QMTLINK_API_KEY` | 首次运行时自动生成 | 访问账户和交易接口的密钥，CLI、SDK 和 bridge 必须保持一致 |
| `qmt_path` | `QMTLINK_QMT_PATH` | 空 | miniQMT 的 `userdata_mini` 完整路径，真实模式必填 |
| `account_id` | `QMTLINK_ACCOUNT_ID` | 空 | miniQMT 资金账号，真实模式必填 |
| `account_type` | `QMTLINK_ACCOUNT_TYPE` | `STOCK` | 账户类型；普通股票为 `STOCK`，融资融券通常为 `CREDIT` |
| `strategy_name` | `QMTLINK_STRATEGY_NAME` | `qmtlink` | 写入委托记录的策略名称 |
| `host` | `QMTLINK_HOST` | `127.0.0.1` | bridge 监听地址；仅本机使用时不要改为公网地址 |
| `port` | `QMTLINK_PORT` | `8000` | bridge 监听端口，也可通过 `qmt bridge run --port` 临时覆盖 |
| `allow_trading` | `QMTLINK_ALLOW_TRADING` | `false` | 是否允许真实下单和撤单；Mock 模式不受影响，开启后 CLI 仍需显式传入 `--live` |
| `url` | `QMTLINK_URL` | 根据 `host` 和 `port` 生成 | CLI 和 Python SDK 访问 bridge 的地址，分开部署时需要设置 |
| `timeout` | `QMTLINK_TIMEOUT` | `30.0` | CLI 和 Python SDK 的 HTTP 请求超时秒数 |
| `session_id` | `QMTLINK_SESSION_ID` | 自动生成 | XtQuantTrader 会话编号；手动设置时应避免与其他实例重复 |
| `idempotency_db` | `QMTLINK_IDEMPOTENCY_DB` | 用户数据目录 | 保存下单幂等记录的 SQLite 文件路径 |

Windows 默认幂等数据库位于 `%LOCALAPPDATA%\QmtLink\orders.sqlite3`；Linux/macOS 默认位于
`~/.local/share/qmtlink/orders.sqlite3`。

### 覆盖规则

配置优先级从高到低为：

1. `qmt bridge run` 的 `--mock`、`--host`、`--port` 参数
2. 对应的 `QMTLINK_*` 环境变量
3. `config.toml`
4. 程序内置默认值

最小配置示例见 [qmtlink.toml.example](qmtlink.toml.example)。如需把配置放到其他位置，可设置
`QMTLINK_CONFIG` 指向目标文件。

## 参与开发

```bash
uv sync --all-extras --dev
uv run pytest
uv run ruff check .
uv build --no-sources
```

后续计划见 [ROADMAP.md](ROADMAP.md)，发版说明见
[docs/RELEASING.md](docs/RELEASING.md)。

## 许可证

本项目使用 MIT 许可证。QmtLink 与 miniQMT、QMT、xtquant 及其权利方不存在官方隶属或
背书关系。
