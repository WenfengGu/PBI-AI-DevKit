# 技术白皮书：Power BI 与 AI 助手的集成方案对比

> PBI AI DevKit — Power BI AI Development Toolkit for Claude Code | 2026-07 (v1.2)

---

## 1. 摘要

本文档对比了当前 AI 助手（Claude Code、ChatGPT/Copilot）与 Power BI 数据模型交互的技术路径，分析了各方案的架构、能力边界和适用场景，并阐述了我们自建 PBI AI DevKit 的技术决策依据。

**v1.2 新增：** 远程 REST API 连接、BIM 文件驱动的远程查询、双模式连接策略。

---

## 2. Power BI 模型访问的技术路径

### 2.1 PBIX 文件结构

PBIX 文件本质是 ZIP 压缩包，内部结构如下：

```
file.pbix (ZIP)
+-- DataModel          <- SSAS xmSQL 压缩备份 (模型的核心数据)
+-- Report/Layout      <- 可视化布局 (JSON)
+-- TMDLScripts/       <- 增量修改记录 (TMDL 格式, 仅脏数据)
+-- DataMashup         <- Power Query M 代码 (旧版格式, ZIP within ZIP)
+-- Connections        <- 数据源连接信息
+-- Metadata           <- 文件元数据
+-- ...
```

### 2.2 关键约束

- **DataModel** 是 xmSQL 压缩二进制格式（Microsoft Analysis Services 私有格式），无法通过文本解析器直接读取
- **DataMashup** 仅在非增强元数据格式的 PBIX 中存在，增强格式下 M 代码嵌入 DataModel 内部
- 模型的运行时状态由 **msmdsrv.exe**（SSAS Tabular 引擎）管理，监听 `localhost:<随机端口>`

### 2.3 三种访问路径

| 路径 | 协议 | 适用场景 |
|------|------|----------|
| **Power BI REST API** | HTTPS | 云端数据集、报表、工作区管理 |
| **XMLA Endpoint** | HTTP/XMLA | 本地或云端 SSAS 实例的读写 |
| **ADOMD.NET / TOM** | TCP (localhost) | 本地 Power BI Desktop 实例的直连 |

---

## 3. 现有方案分析

### 3.1 官方 Power BI MCP Server (Preview)

Microsoft 于 2026 年发布，提供两个版本：

**本地服务器 (local):**
- 运行时：Node.js 20+，通过 `npx` 启动
- 传输：stdio
- 认证：Microsoft Entra ID (OAuth) 或 Service Principal
- 能力：基于 TMDL 的语义模型读写（表、列、Measure、关系）、DAX 查询验证、批量操作

**远程服务器 (remote):**
- 运行时：Fabric 托管服务
- 传输：Streamable HTTP
- 认证：Microsoft Entra ID (OAuth)
- 能力：Copilot 驱动的 DAX 生成、自然语言查询语义模型

**局限：**
- 强制要求 Entra ID 认证，无法离线使用
- 依赖 Node.js 生态系统，Python 用户需额外安装
- 全文 DAX 搜索和 Power Query 审计不在能力范围内
- 无 DAX 最佳实践分析、无依赖追踪

### 3.2 社区方案

社区存在多个 Power BI MCP 实现，均基于以下技术栈之一：

- Power BI REST API（需 Azure AD 认证）
- pythonnet + ADOMD.NET（本地 SSAS 连接）
- msmdsrv 端口发现 + DMV 查询

**共同局限：** 所有社区方案仅支持模型元数据读取，不支持 Measure 修改（TOM）。

### 3.3 ChatGPT/Copilot 集成

ChatGPT 和 GitHub Copilot 通过 Microsoft 官方插件直接调用 Power BI REST API 和 XMLA 端点。该能力绑定在各自生态中，不适用于 Claude Code 用户。

---

## 4. PBI AI DevKit 架构

### 4.1 技术栈

```
+-------------------------------------------------+
|  Claude Code (MCP Client)                        |
|    |  MCP JSON-RPC 2.0 (stdio)                   |
|    v                                             |
|  server.py (Python 3.11)                         |
|    +-- MCP Protocol (hand-written)               |
|    +-- 26 tools defined                          |
|    +-- Tool Handler Dispatcher                   |
|         |                                        |
|    +----+--------------------------+             |
|    |    |                          |             |
|    v    v                          v             |
|  ssas_client.py   bpa.py    dependency_          |
|  (ADOMD+TOM+       (18 rules) tracker.py         |
|   REST API+BIM)                    |             |
|    |                               |             |
|    v                               v             |
|  power_query_ssas.py      bim_reader.py          |
|  (DMV Partition)          (BIM JSON)             |
|    |                                             |
|    v                                             |
|  pythonnet (CLR Bridge)                          |
|    |                                             |
|    v                                             |
|  Power BI Desktop DLLs                           |
|    +-- Microsoft.PowerBI.AdomdClient.dll         |
|    +-- Microsoft.AnalysisServices.Server.        |
|    |   Tabular.dll                               |
|    +-- Microsoft.PowerBI.Tabular.dll             |
|         |                                        |
|         v                                        |
|  msmdsrv.exe (TCP localhost:<port>)              |
|    +-- SSAS Tabular Instance                     |
|                                                  |
|  -- OR (remote) --                               |
|                                                  |
|  REST API Client                                 |
|    +-- Power BI Cloud (executeQueries)           |
+-------------------------------------------------+
```

### 4.2 核心设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| MCP 协议 | 手写实现 | 避免依赖 mcp/fastmcp 包，减少网络依赖 |
| 传输格式 | 二进制安全 stdio | 避免 Windows 文本模式 `\r\n` 转换导致 Content-Length 失配 |
| .NET 桥接 | pythonnet 3.1 | 直接调用 Power BI Desktop 自带的 ADOMD.NET DLL，无需额外安装 |
| 实例发现 | netstat + tasklist | 零配置自动发现 msmdsrv 端口 |
| 模型读取 | DMV 查询 | $SYSTEM.TMSCHEMA_* 系列，全覆盖 |
| 模型修改 | TOM (Tabular Object Model) | 直接操作 model.SaveChanges()，非 XMLA |
| Power Query 读取 | TMSCHEMA_PARTITIONS.QueryDefinition | 所有表的 M 代码全部可读 |
| DAX 分析 | 正则 + 括号深度追踪 | 纯 Python 静态分析，无需 SSAS 连接 |
| 依赖追踪 | 图论 (BFS/DFS) | 正向/反向/传递/环形检测，支持拓扑排序 |
| 远程 DAX | REST API executeQueries | 直接查询 Power BI 云端数据集 |
| 远程元数据 | BIM 文件 | DMV 不可用时的 JSON schema 缓存 |
| 连接策略 | 本地优先，远程兜底 | 打开 PBIX 时全能力，关闭时远程降级 |
| 认证 | 无 (本地) / MSAL (远程) | localhost 无需认证；云端用用户名密码 |

### 4.3 工具清单

| # | 工具 | 底层技术 | 读写 |
|---|------|----------|:---:|
| 1 | `discover` | netstat + tasklist | 读 |
| 2 | `get_model_info` | DMV / BIM + REST API | 读 |
| 3 | `get_tables` | DMV / BIM 文件 | 读 |
| 4 | `get_measures` | DMV / BIM 文件 | 读 |
| 5 | `get_columns` | DMV / BIM 文件 | 读 |
| 6 | `search_dax` | DMV / BIM 文件 + Python 过滤 | 读 |
| 7 | `run_dax` | ADOMD.NET / REST API | 读 |
| 8 | `replace_in_measure` | TOM: Measure.Expression | 写 |
| 9 | `get_power_query` | DMV: TMSCHEMA_PARTITIONS.QueryDefinition | 读 |
| 10 | `audit_power_query` | 同上 + 模式分析 | 读 |
| 11 | `get_relationships` | DMV / BIM 文件 | 读 |
| 12 | `validate_dax` | DEFINE MEASURE ... EVALUATE | 读 |
| 13 | `export_model_snapshot` | DMV 全量 + JSON 序列化 | 读 |
| 14 | `create_measure` | TOM: MeasureCollection.Add() | 写 |
| 15 | `delete_measure` | TOM: MeasureCollection.Remove() | 写 |
| 16 | `get_roles` | TOM: Model.Roles | 读 |
| 17 | `create_relationship` | TOM: SingleColumnRelationship | 写 |
| 18 | `create_table` | TOM: TableCollection.Add() + Partition | 写 |
| 19 | `create_column` | TOM: DataColumn + DataType enum | 写 |
| 20 | `batch_operations` | TOM: 批量操作 + 单次 SaveChanges | 写 |
| 21 | `get_model_graph` | DMV: 表+列+关系 拓扑图 | 读 |
| 22 | `bpa_analyze` | Python 正则静态分析 (18 条规则) | 读 |
| 23 | `dependency_analyze` | Python 图论 (BFS/DFS + 拓扑排序) | 读 |
| 24 | `get_report_structure` | PBIX zip 解析: 页面、视觉对象、字段绑定 | 读 |
| 25 | `get_report_measures` | 报表 Measure 使用情况 + BIM 交叉对比 | 读 |
| 26 | `get_report_field_usage` | 影响分析: measure/column -> 页面/视觉对象 | 读 |

---

## 5. DAX 最佳实践分析器 (BPA)

### 5.1 架构

```
bpa.py
+-- Severity: error / warning / info
+-- Category: performance / maintainability / correctness / naming
+-- 18 rules (extensible)
|   +-- Performance (6 rules)
|   |   +-- EARLIER_INSTEAD_OF_VAR
|   |   +-- CALCULATE_NO_FILTER
|   |   +-- FILTER_VALUES_PATTERN
|   |   +-- MULTIPLE_FILTER
|   |   +-- ITERATOR_NO_FILTER
|   |   +-- SELECTCOLUMNS_ADDCOLUMNS
|   +-- Maintainability (4 rules)
|   |   +-- LONG_EXPRESSION
|   |   +-- NO_COMMENTS
|   |   +-- HARDCODED_VALUES
|   |   +-- NESTED_IF_DEPTH
|   +-- Correctness (8 rules)
|   |   +-- DIVIDE_NO_ALTERNATIVE
|   |   +-- SWITCH_NO_ELSE
|   |   +-- ISFILTERED_IN_MEASURE
|   |   +-- ALL_VS_ALLSELECTED
|   |   +-- BLANK_COMPARISON
|   |   +-- USERELATIONSHIP_NO_CALCULATE
|   |   +-- SELECTEDVALUE_NO_ALTERNATIVE
|   |   +-- VAR_NO_RETURN
|   +-- Naming (2 rules)
|       +-- NO_FORMAT_STRING
|       +-- NO_DISPLAY_FOLDER
+-- DaxAnalyzer class
    +-- analyze_expression(expr) -> list[dict]
    +-- analyze_measure(measure_dict) -> list[dict]
    +-- analyze_all(measures) -> dict (stats + issues)
    +-- format_report(stats) -> str (readable report)
```

### 5.2 实现细节

- **纯 Python 实现** -- 无需 SSAS 连接，可离线分析 BIM 文件
- **正则 + 括号深度追踪** -- 处理嵌套函数调用，避免误报
- **严重程度分层** -- error (语法错误) / warning (潜在问题) / info (风格建议)
- **可扩展** -- 新增规则只需实现 `_check_xxx(expr) -> Optional[dict]` 并注册到 `EXPRESSION_RULES` 列表

### 5.3 实测数据

针对生产环境模型（约 1,680 个 Measure，117 张表）测试：

| 指标 | 数值 |
|------|------|
| 总问题数 | ~6,000 |
| 错误 | 0 |
| 警告 | ~1,000 |
| 建议 | ~5,000 |
| 有问题的 Measure | 92% |
| Top 问题 | NO_COMMENTS, CALCULATE_NO_FILTER, NO_DISPLAY_FOLDER |

---

## 6. Measure 依赖追踪器

### 6.1 架构

```
dependency_tracker.py
+-- parse_dax_references(expr) -> dict
|   +-- measures: [Name] references
|   +-- columns: 'Table'[Column] references
|   +-- tables: 'Table' references
|   +-- functions: FUNC() calls
|
+-- DependencyTracker class
|   +-- build_graph(measures, tables)
|   |   +-- Build bidirectional adjacency list
|   +-- get_dependencies(name, table) -> dict
|   |   +-- BFS: forward + transitive deps
|   +-- get_impact(name, table) -> dict
|   |   +-- BFS: reverse + transitive impact
|   +-- detect_circular_dependencies() -> list[cycle]
|   |   +-- DFS (3-color marking)
|   +-- get_topological_order() -> list[str]
|   |   +-- Kahn's algorithm (BFS + in-degree)
|   +-- get_most_used(n) -> list[(key, count)]
|   +-- get_orphan_measures() -> list[str]
|   +-- format_summary() / format_dependencies() -> str
```

### 6.2 实现细节

- **图论算法** -- BFS 传递闭包、DFS 环形检测、Kahn 拓扑排序
- **Measure 名称消歧** -- 当多个表有同名 Measure 时，优先匹配当前表
- **纯 Python 实现** -- 无需 SSAS 连接，可离线分析 BIM 文件
- **O(N+E) 复杂度** -- 数千个 Measure 秒级分析完成

### 6.3 实测数据

针对生产环境模型（约 1,680 个 Measure）测试：

| 指标 | 数值 |
|------|------|
| 有依赖关系的 Measure | 94% |
| 被其他 Measure 引用的 | 69% |
| 环形依赖 | 0 |
| 孤儿引用 | 0 |
| 最被引用的 Measure | 440 dependents |
| 典型 Measure 影响 | 17 个直接依赖, 27 直接 + 281 传递 = 308 个受影响 |

---

## 7. 远程连接 (REST API)

### 7.1 架构

```
ssas_client.py
+-- RemotePowerBI (REST API 客户端)
|   +-- acquire_token() -> MSAL username/password
|   +-- Token 缓存 -> .pbi_token_cache.json (59min 过期)
|   +-- list_workspaces() -> GET /groups
|   +-- list_datasets() -> GET /groups/{id}/datasets
|   +-- execute_dax() -> POST /datasets/{id}/executeQueries
|
+-- RemotePowerBIWithSchema (BIM 增强)
    +-- load_schema(bim_path) -> 解析 BIM JSON
    +-- get_tables() / get_columns() / get_measures() -> BIM 元数据
    +-- search_dax() -> BIM 全文搜索
    +-- get_column_values() / get_table_row_count() -> 远程实时查询
```

### 7.2 认证流程

```
[PBI_USERNAME] + [PBI_PASSWORD] (环境变量)
  v
acquire_token_by_username_password()
  v
JWT Token (aud = Power BI API scope)
  v
REST API: Authorization: Bearer {token}
  v
GET /groups -> 200 OK (工作区列表)
POST /executeQueries -> 200 OK (DAX 查询结果)
```

### 7.3 能力边界

| 能力 | REST API | 限制 |
|------|:---:|------|
| EVALUATE 查询 | 支持 | 标准 DAX 语法 |
| DMV 查询 ($SYSTEM.*) | 不支持 | 被 API 剥离 |
| INFO 函数 | 不支持 | "Failed to execute DAX query" |
| 元数据读取 | 不支持 | 仅 Push API 数据集 |
| 写入操作 | 不支持 | REST API 只读 |

---

## 8. BIM 文件驱动的远程查询

### 8.1 设计动机

REST API 不支持元数据查询 (DMV/INFO)，但 BIM 文件与远程模型共享相同的表结构。通过 BIM 文件提供元数据、REST API 提供数据，实现完整的远程查询能力。

### 8.2 数据流

```
+---------------+     +---------------+      +-------------------+
|  BIM File     |     |  MCP Server   |      |  Power BI Cloud   |
|  (local JSON) |     |               |      |  (REST API)       |
+---------------+     +---------------+      +-------------------+
| N tables      |---->| Schema cache  |      |                   |
| N columns     |     |               |      |                   |
| N measures    |     | get_columns() |      |                   |
|               |     | get_measures()|      |                   |
|               |     | search_dax()  |      |                   |
|               |     |               |      |                   |
|               |     | execute_dax() |----->| VALUES(Table[...])|
|               |     | COUNTROWS()   |<-----| N rows            |
+---------------+     +---------------+      +-------------------+
```

---

## 9. 双模式连接策略

### 9.1 路由逻辑

```
_get_connection(mode="auto")
  |
  +-- mode="write" -> Force local (fail if no PBIX)
  +-- mode="remote" -> Force remote (fail if not configured)
  |
  +-- mode="auto" (default)
      +-- 1. Local PBIX found? -> Local mode (ADOMD.NET)
      |     +-- All 26 tools available
      +-- 2. No local, remote configured? -> Remote mode
      |     +-- BIM configured? -> RemotePowerBIWithSchema
      |     +-- No BIM? -> RemotePowerBI (DAX only)
      +-- 3. Neither -> Error with guidance
```

### 9.2 模式能力矩阵

| 能力 | 本地 | 远程 | 远程+BIM |
|------|:---:|:---:|:---:|
| 读取元数据 | DMV | 不支持 | BIM 文件 |
| DAX 查询 | ADOMD.NET | REST API | REST API |
| 创建/修改 Measure | TOM | 不支持 | 不支持 |
| 全文搜索 DAX | DMV | 不支持 | BIM 文件 |
| BPA 分析 | 实时 | 不支持 | BIM 文件 |
| 依赖追踪 | 实时 | 不支持 | BIM 文件 |
| Power Query 审计 | DMV | 不支持 | 不支持 |

---

## 10. 方案对比

### 10.1 能力矩阵

| 能力 | 官方 MCP | 社区方案 | 本方案 |
|------|:---:|:---:|:---:|
| 读取模型元数据 | DMV / REST | DMV / REST | DMV / BIM |
| 修改 Measure | TMDL | 不支持 | **TOM** |
| 创建/删除 Measure | 支持 | 不支持 | **支持** |
| 创建表/列 | 支持 | 不支持 | **支持** |
| 执行 DAX 查询 | XMLA | ADOMD.NET | ADOMD.NET / REST |
| 全文搜索 DAX | 未提及 | 部分支持 | **全文** |
| 审计 Power Query | 未提及 | 不支持 | **支持** |
| 关系管理 | 支持 | 不支持 | **支持** |
| 安全角色 | 支持 | 不支持 | **支持** |
| 事务批处理 | 支持 | 不支持 | **支持** |
| 模型拓扑图 | 支持 | 不支持 | **支持** |
| DAX 最佳实践分析 | 未提及 | 不支持 | **支持 (18 条规则)** |
| Measure 依赖追踪 | 未提及 | 不支持 | **支持 (正向/反向/环形)** |
| 远程 DAX 查询 | 支持 | 不支持 | **支持 (REST API)** |
| BIM 驱动的远程查询 | 未提及 | 不支持 | **支持** |
| 本地/远程双模式 | 支持 | 不支持 | **支持 (本地优先)** |
| 自动发现实例 | 支持 | 需配置 | **零配置** |
| 认证要求 | 视场景而定 | Azure AD | **本地无需 / 远程 MSAL** |
| 运行环境 | Node.js 20+ | Python | Python |
| 离线可用 | 视场景而定 | 混合 | **本地是 / 远程否** |

### 10.2 适用场景

| 场景 | 推荐方案 |
|------|----------|
| 企业级 Fabric 部署，已有 Entra ID | 官方 MCP (local) |
| 云端数据集查询分析 | 官方 MCP (remote) |
| 本地 PBIX 开发，零配置快速上手 | **本方案** |
| 批量修改 Measure | **本方案** |
| DAX 全文搜索 | **本方案** |
| DAX 代码质量审查 | **本方案** |
| Measure 影响评估 | **本方案** |
| Power Query 代码审计 | **本方案** |
| 离线环境 | **本方案** |
| Python 环境偏好 | **本方案** |

---

## 11. Power Query 研究的发现

### 11.1 M 代码的存储位置

经过多种路径研究（DataMashup ZIP 提取、Microsoft.Mashup API、xmSQL 解析），最终确认 M 代码存储在：

```
$SYSTEM.TMSCHEMA_PARTITIONS.QueryDefinition
```

这是 SSAS DMV 中 partitions 表的 `QueryDefinition` 列，包含每张表的完整 Power Query M 表达式。

### 11.2 修改限制

- `MPartitionSource.Expression` 属性**可读写**（TOM API）
- 但 Power BI Desktop 会在刷新时**验证并回滚**结构性的 M 代码变更
- 仅注释级别的修改可以持久化（已验证）
- 结论：**M 代码可读不可改**（结构性修改），这是 Power BI Desktop 的设计保护机制

---

## 12. 参考文献

- Microsoft Learn: [Power BI MCP servers overview (Preview)](https://learn.microsoft.com/en-us/power-bi/developer/mcp/mcp-servers-overview)
- Anthropic: [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- Microsoft Docs: [Tabular Object Model (TOM)](https://learn.microsoft.com/en-us/analysis-services/tom/introduction-to-the-tabular-object-model-tom-in-analysis-services-amo)
- DMV Reference: `$SYSTEM.TMSCHEMA_MEASURES`, `$SYSTEM.TMSCHEMA_PARTITIONS`, `$SYSTEM.TMSCHEMA_TABLES`, `$SYSTEM.TMSCHEMA_COLUMNS`

---

## 13. 附录：成本核算

### 项目规模

| 指标 | 数量 |
|------|------|
| 总文件数 | 90+ |
| 代码量 | ~550 KB |
| 工具数 | 26 |
| 核心模块 | 6 (ssas_client, bpa, dependency_tracker, bim_reader, power_query_ssas, RemotePowerBI) |
| BPA 规则 | 18 (可扩展) |
| Skill 工作流 | 12 |
| 测试套件 | 31 |
| 文档 | 5 份 |

### 时间投入

| 阶段 | 工时 |
|------|------|
| 基础架构 (MCP + Skill + SSAS + 8 核心工具) | 8h |
| Power Query (研究 + 读取 + 审计) | 4h |
| 扩展工具 (关系/校验/快照/角色/创建/删除/批处理) | 8h |
| DAX 优化 (模型拓扑图/上下文预检/渠道分析) | 4h |
| BPA + Dependency Tracker (模块开发 + 集成 + 测试) | 4h |
| 远程连接 (REST API + BIM + 双模式 + MSAL 认证) | 4h |
| **合计** | **~32h** |

### 等效成本

| 成本项 | 估算 |
|------|------|
| 开发者时间 | 32h x 内部时薪 |
| Claude Code Token | 5 天密集对话 |
| 等价外包开发 | 23 工具 + 5 文档 + 31 测试 ~ 80-120h x $100-150/h = **$8,000-$18,000** |
| 等价官方方案 | 免 Entra ID 配置、免 Node.js 环境 |

### 核心价值

- **零边际成本分发** -- 同事一句话部署，无需额外开发
- **填补生态空白** -- 社区唯一支持 TOM 写入 + BPA + 依赖追踪的 Python MCP
- **可复用** -- 适用于所有 Power BI Desktop 项目