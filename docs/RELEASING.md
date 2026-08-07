# Releasing QmtLink

QmtLink 使用 GitHub Actions 和 PyPI Trusted Publishing 发版，不在 GitHub 或本地长期保存
PyPI API Token。

## 一次性配置

在 PyPI 项目 `qmtlink` 的 **Manage → Publishing** 页面添加 GitHub Publisher：

| 字段 | 值 |
|---|---|
| Owner | `ilwk` |
| Repository name | `qmtlink` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

GitHub 仓库中需要存在名为 `pypi` 的 Environment。发布任务只申请 `id-token: write` 和
`contents: read` 权限。

## 发布步骤

1. 更新 `pyproject.toml` 中的版本并刷新 `uv.lock`。
2. 运行代码检查、测试、构建和本地安装验证。
3. 提交版本变更。
4. 创建与包版本一致的标签，例如 `v0.1.0a2`。
5. 推送提交和标签；GitHub Actions 自动构建并发布到 PyPI。

推荐使用 uv 更新版本：

```bash
uv version 0.1.0a2
uv lock
```

发布工作流会拒绝与 `pyproject.toml` 版本不一致的标签。PyPI 上的版本文件不可覆盖；失败后
如果构建内容发生变化，应提升版本再重新发布。
