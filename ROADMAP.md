# Roadmap

## 0.1.x：基础链路

- [x] 可发布 Python 包和 uv 管理
- [x] `qmt` / `qmtlink` CLI
- [x] Mock Bridge
- [x] 健康检查、能力发现和行情快照
- [x] Python SDK
- [x] 安全订单预览
- [ ] 真实 xtdata 历史行情验证
- [x] 历史行情（tick/K 线、时间范围/条数、复权、原始字段）
- [ ] WebSocket 行情订阅

## 0.2.x：账户与模拟交易

- [x] XtQuantTrader 生命周期
- [x] 资产、持仓、委托和成交查询
- [ ] 交易回报 WebSocket
- [x] SQLite 下单幂等记录
- [x] Mock/模拟盘下单和撤单测试
- [x] 标准化交易字段并保留券商原始状态值
- [ ] 按交易所明确支持并验证市价委托类型

## 0.3.x：受控实盘

- [ ] 实盘多层开关
- [ ] 单笔及每日金额限制
- [ ] 超时后的订单状态核对
- [ ] 审计日志
- [ ] 干净 Windows 环境兼容性测试

## 非目标

QmtLink 不提供策略、回测、因子、GUI、数据仓库或任意 xtquant 对象代理。
