# 通俗版：为什么我们要自己做这个 MCP？

---

## 先打个比方

把 Power BI 文件（PBIX）想象成一个**保险箱**：

```
你的报表.pbix (保险箱)
+-- Report/         <- 贴在保险箱外面的标签 (可视化布局, JSON格式)
+-- TMDLScripts/    <- 保险箱上的便签 (最近的修改记录)
+-- DataModel       <- 保险箱里的东西 (二进制文件, 大小取决于模型复杂度)
```

- **ChatGPT 有官方钥匙** -- 微软给了它一把官方钥匙（现在也开放了 Power BI MCP server Preview），能打开保险箱拿出里面的东西
- **Claude 没有这把钥匙** -- 它只能看到保险箱外面的标签和便签，打开保险箱看到的是一堆乱码

我们要做的就是**给 Claude 配一把钥匙**。

---

## 三种 AI 是怎么跟 Power BI 打交道的？

### ChatGPT：有官方钥匙

```
我说: "帮我看看这个报表里有哪些 measure"

ChatGPT -> 官方 Power BI 连接器 -> 打开保险箱 -> 读出所有 measure -> 回复我
         (微软提供, 开箱即用。2026年起也开放了 Power BI MCP server Preview)
```

ChatGPT 能这么做，是因为微软和 OpenAI 合作，**内置了 Power BI 的读写能力**。用户不需要安装任何额外的东西。

### Claude（之前）：没有钥匙

```
我说: "帮我看看这个报表里有哪些 measure"

Claude -> 解压 PBIX 文件 -> 看到 DataModel -> 试了一下 -> 乱码 -> 回复: "我读不了"
         (只能看到外面)       (二进制, 微软私有格式)
```

Claude 能解压 PBIX（因为 PBIX 本质是个 ZIP 文件），但核心数据存在 `DataModel` 文件里，这是一个**只有 Power BI 自己才能打开的私有格式**，就像一份加了密的文件，没有密码看到的就是乱码。

### Claude（现在）：我们自己配了一把钥匙

```
我说: "帮我看看这个报表里有哪些 measure"

Claude -> 本 MCP Server -> 找到 Power BI 自带钥匙 -> 打开保险箱 -> 读出所有 measure -> 回复我
         (我们做的)     (借用 PBI Desktop 的 DLL)    (跟 ChatGPT 一样了)
```

关键在于：**我们没有自己造钥匙，而是借用了 Power BI Desktop 安装目录里自带的钥匙**。

每台装了 Power BI Desktop 的电脑上，都有这个目录：
```
D:\Program Files\Microsoft Power BI Desktop\bin\
    +-- Microsoft.PowerBI.AdomdClient.dll    <- 这把钥匙能"读"
    +-- Microsoft.AnalysisServices.*.dll      <- 这把钥匙能"改"
```

这些 DLL 是微软官方的，DAX Studio 和 Tabular Editor 用的也是它们。我们的 MCP 只是通过 Python 桥接了这些 DLL，让 Claude 也能用上。

---

## 对比表

| 核心问题 | 官方 MCP | Claude 之前 | Claude 现在 |
|----------|:---:|:---:|:---:|
| 能打开 PBIX 吗？ | 能 | 能解压 ZIP，但看不懂数据 | 能，跟官方 MCP 一样 |
| 能列出所有 measure 吗？ | 能 | 不能 | 能 |
| 能搜索 DAX 公式吗？ | 部分支持 | 不能 | **全文搜索** |
| 能修改 measure 吗？ | 能 (TMDL) | 不能 | **能 (TOM)** |
| 能审计 Power Query 吗？ | 不能 | 不能 | **能** |
| 需要联网吗？ | 视场景 | 不需要 | 不需要 |
| 需要 Azure 账号吗？ | 视场景 | 不需要 | 不需要 |
| 怎么做到的？ | 微软官方 | 无解 | 借用 Power BI 自带的 DLL |

---

## 为什么不能直接用 ChatGPT 的方案？

用一句话说：**ChatGPT 和官方 MCP 的钥匙是微软定制的，只认 ChatGPT/Entra ID 这个锁，Claude 的锁孔形状不一样，插不进去。**

具体来说：
1. 官方 MCP 在 Desktop 场景下可以自动发现本地实例，无需 Entra ID
2. 但需要 Node.js 运行环境（npx 启动），Python 用户不友好
3. 我们的方案：Python 环境、零配置、一句话部署

---

## 我们做了什么？

```
步骤 1: 发现 Power BI Desktop 自带的 DLL 钥匙
步骤 2: 用 pythonnet 把 Python 调用"翻译"成 .NET 调用
步骤 3: 通过 ADOMD.NET 连接本地 Power BI 引擎
步骤 4: 用 DMV 查询读取模型元数据（表、Measure、DAX）
步骤 5: 用 TOM 接口实现修改 Measure 的能力
步骤 6: 发现 TMSCHEMA_PARTITIONS 中的 Power Query M 代码，实现审计
步骤 7: 封装成 MCP Server + Skill，让 Claude Code 能直接调用
```

**结果：** Claude 现在具备了和官方 MCP 一样的 Power BI 读写能力，而且是**纯本地、零认证、零配置、不需要联网**。和官方 MCP 相比，我们额外提供了全文 DAX 搜索和 Power Query 审计功能。