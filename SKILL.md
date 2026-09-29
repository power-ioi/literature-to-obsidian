---
name: literature-to-obsidian
description: Zotero → MinerU → Obsidian 文献精读笔记工作流。当用户要求精读/整理论文、把 Zotero 里的文献做成 Obsidian 笔记、或提到 Zotero、MinerU、文献笔记、精读时使用。不用于普通网页内容整理或非文献类写作。
---

# Literature to Obsidian 文献精读工作流

把 Zotero 里的论文（元数据 + 标注）与 MinerU 解析出的全文、图片，整合成一份带图精读笔记写入 Obsidian vault。

总顺序：**先找本地证据 → 再生成笔记 → 最后确认写入位置**。核心原则：宁可空着也不编造。

## 路径约定（脚本默认基于用户主目录 `~`，可用环境变量 `ZOTERO_HOME` / `ZOTERO_DB` / `MINERU_CACHE` 覆盖）

| 组件 | 路径 |
|------|------|
| Zotero 数据库 | `~/Zotero/zotero.sqlite`（只读，WAL 模式，Zotero 开着也能读） |
| Zotero PDF 存储 | `~/Zotero/storage/<附件key>/xxx.pdf` |
| MinerU 缓存 | `~/Zotero/llm-for-zotero-mineru/<附件ID>/`（来自 Zotero 插件 llm-for-zotero-mineru） |
| Obsidian vault | 由用户在会话中指定（写入前必须现场核实实际结构） |
| 笔记模板目录 | `<vault>/附件/模板/`（用户可自行增删模板，每次使用前现场列目录） |
| Python | `python`（标准库即可，脚本无第三方依赖） |

MinerU 缓存目录内固定有：

- `_llm_source.json` — 映射表：`attachmentKey`（附件 key）、`parentItemKey`（文献条目 key）、`sourceFilename`（原 PDF 文件名）
- `full.md` — MinerU 解析全文
- `manifest.json` — 分节结构，`sections[].figures[]` 含每张图的 `label`、`path`、`caption`、页码
- `images\<hash>.jpg` — 切出的图片

## 第 0 步 环境自检

先跑一次自检，避免把路径搞错（Zotero/MinerU/Obsidian 任一不可用都要先告知用户，不要猜）。

```powershell
python "C:\Users\86186\.trae-cn\skills\literature-to-obsidian\scripts\zotero_lookup.py"
python "C:\Users\86186\.trae-cn\skills\literature-to-obsidian\scripts\mineru_find.py"
```

## 第 1 步 Zotero 取证（只读，绝不写库）

```powershell
python "C:\Users\86186\.trae-cn\skills\literature-to-obsidian\scripts\zotero_lookup.py" --title "标题关键词"
python "C:\Users\86186\.trae-cn\skills\literature-to-obsidian\scripts\zotero_lookup.py" --key NESWKVII
```

- 多个匹配时，列出候选（标题 + 作者 + 年份）让用户确认，不要替用户选。
- 拿到 `key`（文献条目）、附件 key、标注（`annotations`：原文 `text` + 用户批注 `comment`）。
- `attachments[].mineruCache` 非空即表示 MinerU 缓存已存在。

## 第 2 步 MinerU 取证

```powershell
python "C:\Users\86186\.trae-cn\skills\literature-to-obsidian\scripts\mineru_find.py" --parent-key NESWKVII
python "C:\Users\86186\.trae-cn\skills\literature-to-obsidian\scripts\mineru_find.py" --parent-key NESWKVII --figures
```

- 缓存命中：读 `full.md` 全文 + `manifest.json`（--figures 直接给图片清单）。
- 缓存状态 `incomplete` 或 `broken`：告知用户该 PDF 需要在 Zotero 里重新跑 MinerU 解析（llm-for-zotero-mineru 插件），完成后重试。**不要自己安装或运行 MinerU**。
- 无缓存：同样引导用户先解析，不要拿 PDF 硬读。Zotero 标注仍然可用，可先出无图版草稿。

## 第 3 步 读全文、看图、选图

1. 通读 `full.md`，提炼核心逻辑链和关键结论；每条结论都要能在原文找到出处。
2. 从 manifest 的 figures 清单中初筛，然后**用 Read 工具看候选图片的实际内容**再定稿。
   - 坑：一个 Figure 常被 MinerU 拆成多张小图（如 Figure 3a/b/c/d 各一张），caption 只能辅助定位，看图内容才能放对。
   - 选 3–6 张：优先最能支撑核心结论的结果图（性能曲线、修复效率、对比柱状图），其次机制示意图。
3. 记录每张选中图的：`path`、`caption`、一句话"为什么放它"。

## 第 4 步 选模板并生成草稿（只在当前工作区）

- **每次先问用户用哪个模板**：现场列出 vault `附件\模板\` 目录下全部 .md 模板文件名，用 AskUserQuestion 供用户选择。模板会越来越多，永远不要静默替用户挑一个；用户本轮消息已明确指定模板时才可跳过提问。
- 选中的模板决定笔记结构与 frontmatter；模板目录不存在或为空时，回退到 skill 自带 `references/note-template.md` 并告知用户。
- 按选定模板结构，在当前工作区生成草稿 md（文件名 `<年份> - <标题简写>.md`）。
- 基本信息表中的期刊、年份、DOI、作者一律取自 Zotero 元数据。
- **未核验数据规则**：影响因子、JCR 分区、引用数等若没有可靠来源，写 `暂未核验`，绝不编造数字。
- 图片统一放 vault 的 `附件/images/<笔记名>/`，按嵌入顺序把选中图重命名为 `fig1.jpg … figN.jpg`；笔记内用相对链接 `![](../附件/images/<笔记名>/fig1.jpg)`（笔记不在文献子目录时按实际相对位置调整前缀）。
- Zotero 标注摘录放入笔记"标注摘录"一节，保留用户自己的 comment。

## 第 5 步 确认写入位置并复制

vault 在工作区之外，写入前必须停一下：

1. 列出 vault 根目录，看**现在实际的**目录结构。已有文献目录（如 `literature/`、`文献笔记/`）就沿用现成的，不要假设固定子目录——目录可能迁移过。
2. 没有现成目录或结构有歧义时，向用户确认再建（默认建议 `literature/`）。用户消息里已明确指定目标的，核实存在后直接用。
3. 复制：笔记 → `<vault>\literature\`（沿用现有文献目录），选中图 → `<vault>\附件\images\<笔记名>\fig1.jpg …`。MinerU 缓存目录保持只读、原文件不动。
4. 笔记内图片链接保持相对路径，Obsidian 才能直接渲染。

## 第 6 步 复查（必须逐项做）

1. 笔记文件确实存在于 vault。
2. 逐个检查笔记里每个 `![](...)` 链接指向的文件真实存在（`Test-Path` 或脚本核对）。
3. 若 vault 是 git 仓库：`git status` 应能看到新增文件；不是则跳过。
4. 向用户报告：写入路径、文件清单、嵌入图片数、复查结果。

## 硬规则

- Zotero 数据库**只读**，所有查询走 `scripts/zotero_lookup.py`（脚本自动复制临时快照再读，原库零接触；Zotero 开着也能查）。
- 没看过内容的图片不嵌入；没出处的结论不写入。
- 未核验指标一律 `暂未核验`。
- 写 vault 前必须现场核实目录结构；vault 属于工作区外路径，遵循权限确认流程。
- 复制/移动只发生在"workspace 草稿 → vault"这一步，MinerU 与 Zotero 的原始文件永不改动。
