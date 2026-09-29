# literature-to-obsidian

一个把 **Zotero 文献库 → MinerU 解析产物 → Obsidian 精读笔记** 串成一条流水线的 AI Agent Skill（为 Trae 等 Code Agent 设计，也可移植到其他支持 Skill 机制的 Agent）。

你只需要说一句"帮我精读《论文标题》"，Agent 就会自动完成：查 Zotero 条目与你的标注 → 定位 MinerU 缓存的全文和图片 → 看图选图 → 按你的模板生成精读笔记 → 询问后写入 Obsidian vault。

## 工作流

```
Zotero (元数据 + 你的标注)          Obsidian vault
        │                               ▲
        ▼                               │ ⑤ 询问后写入笔记 + 图片
llm-for-zotero-mineru 插件              │
        │                               │
        ▼                               │
MinerU 缓存 (full.md + manifest + 切图) │
        │                               │
        └── ②③④ 读全文 / 看图 / 选图 ──┘
```

总顺序：**先找本地证据 → 再生成笔记 → 最后确认写入位置**。

| 步骤 | 内容 |
|------|------|
| 0 环境自检 | 检查 Zotero 库、MinerU 缓存、vault 是否可用 |
| 1 Zotero 取证 | 只读查询条目元数据、附件 key、你的标注（绝不写库） |
| 2 MinerU 取证 | 按 item key 定位缓存，读 `full.md` + 图片清单 |
| 3 读全文、看图、选图 | 每张图先看内容再决定嵌入，3–6 张支撑核心结论 |
| 4 选模板、生成草稿 | 列出 vault 里的模板让用户选，在工作区生成草稿 |
| 5 确认写入位置 | 现场核实 vault 结构，沿用现有文献目录 |
| 6 复查 | 逐个校验图片链接真实存在，向用户报告 |

## 前置条件

| 依赖 | 说明 |
|------|------|
| [Zotero](https://www.zotero.org/) | 本地库，默认在 `~/Zotero/`；脚本**只读**访问 `zotero.sqlite` |
| llm-for-zotero-mineru | Zotero 插件，把 PDF 用 MinerU 解析为 Markdown + 图片切图，缓存到 `~/Zotero/llm-for-zotero-mineru/<附件ID>/`（在 Zotero 社区插件市场搜索安装） |
| Obsidian | 目标笔记仓库（vault），路径在会话中指定 |
| Python 3.8+ | 仅标准库，无第三方依赖 |

## 安装（Trae）

把整个文件夹复制到 Trae 的全局 skill 目录：

```
~/.trae-cn/skills/literature-to-obsidian/
├── SKILL.md                 # 工作流主指令（Agent 读取）
├── README.md
├── references/
│   └── note-template.md     # 内置兜底笔记模板
└── scripts/
    ├── zotero_lookup.py     # Zotero 只读查询（自动快照，WAL 运行中也可读）
    └── mineru_find.py       # MinerU 缓存定位 + 图片清单
```

新开会话即可触发。也可以在其他支持 SKILL.md 规范的 Agent 中使用。

## 用法

对 Agent 说：

- `帮我精读 Biodegradable Nanospray for Sunlight-Activated Photodynamic Antibacterial Therapy and Wound Healing`
- `把 Zotero 里的那篇 Co(III) 纳米颗粒论文做成 Obsidian 笔记`
- `用 <某个模板名> 精读 <标题>`

如果 vault 的 `附件/模板/` 目录里有多个模板，Agent 每次都会先列出来让你选。

## 路径配置

脚本默认基于用户主目录，无需改动即可用于标准 Zotero 安装；Zotero 数据目录不在默认位置时，用环境变量覆盖：

| 环境变量 | 默认值 |
|----------|--------|
| `ZOTERO_HOME` | `~/Zotero` |
| `ZOTERO_DB` | `$ZOTERO_HOME/zotero.sqlite` |
| `MINERU_CACHE` | `$ZOTERO_HOME/llm-for-zotero-mineru` |

## 设计原则（硬规则）

- Zotero 数据库**只读**：查询走快照，原库零接触，Zotero 开着也能查
- **没看过内容的图片不嵌入，没出处的结论不写入**
- 影响因子、分区等未核验指标一律写 `暂未核验`，绝不编造数字
- 一个 Figure 常被 MinerU 拆成多张小图，caption 只能辅助定位，**看图内容才能放对**
- 写 vault 前必须现场核实目录结构（目录可能迁移过）
- MinerU 与 Zotero 的原始文件永不改动，复制只发生在"草稿 → vault"一步

## 免责声明

本工具只读取本地文件，不上传任何数据；作者不对解析质量与生成内容作担保，笔记中的结论请以原文为准。
