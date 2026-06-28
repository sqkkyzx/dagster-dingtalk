# 发版版本号规则

发布新版本前，先确定当前 Dagster 官方版本与库版本的对应关系。

1. 打开 <https://docs.dagster.io/about/changelog>，查看页面中 `ul.table-of-contents.table-of-contents__left-border` 的第一个 `li` 内 `a` 标签文本。

   例如：`1.13.8 (core) / 0.29.8 (libraries)`。

2. 更新 [pyproject.toml](pyproject.toml) 时：

   - `dagster` 依赖版本使用 `core` 版本，例如 `1.13.8`。
   - 项目自身 `version` 使用 `libraries` 版本作为前三段，并追加项目内小版本号，即 `0.29.8.x`。
   - `.x` 用于本项目自己的小版本修复和功能新增。

3. 更新 [version.py](src/dagster_dingtalk/version.py) 时：

   - `__version__` 使用 `libraries` 版本的三段号，例如 `0.29.8`。

# 钉钉开放平台API文档本地存档

本地存档依据 `docs/docinfolist_{date}.json` 进行抓取，date 是 docinfolist 的生成日期。有三类生成产物：

1. 目录列表 `docs/dingtalk_static_html_catalog.yaml`：
    - 已完成树结构
    - 更新日期从HTML中的 meta name="gmtModify" 解析，是真实的线上文档更新日志，可以信任。

2. 已抓取的静态文档 `docs/dingtalk_static_html` :
    - 按树结构逐级目录存储
