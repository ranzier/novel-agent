# 网文写作 Agent（novel-agent）

把一句话创意，半自动 / 全自动地写成结构完整、前后连贯的长篇网络小说。

这不是"调一次模型写一段"的玩具。它把长篇写作拆成**立项 → 分层大纲 → 单章写作 → 记忆固化 → 一致性校验 → 向量召回 → 批量续写**的流水线，并用一套记忆与校验机制，解决长篇连载最难的问题——**写到几百章后，模型还记得开头发生了什么、谁已经死了、主角现在什么境界**。

---

## 核心设计

长篇写作真正的难点不是文笔，是**连贯性**。模型上下文有限，写到第 50 章时早就看不到第 1 章。本项目用三层记忆 + 双层校验来兜住：

- **短期记忆** —— 最近几章原文，保证相邻章节衔接自然
- **中期记忆** —— 滚动的章节摘要 + 世界状态快照（主角境界 / 位置、谁生谁死、未回收伏笔、进行中线索），让模型不读全文也能掌握全局
- **长期记忆** —— 向量库语义召回历史片段，写到后期还能"想起"早期的相关场景细节
- **一致性校验** —— 写完每章自动比对设定与状态：确定性规则（境界倒退、死人复活、角色名漂移）+ LLM 语义校验（时间线、金手指越界、伏笔逻辑）。发现硬伤自动重写
- **节奏引擎** —— 确定性推算每章节拍（铺垫 / 蓄势 / 爆发 / 高潮 / 余韵），注入写作，避免一路平推

---

## 安装

需要 Python 3.12+。

```bash
.venv/bin/pip install -e .
```

## 配置

复制 `.env.example` 为 `.env`，填入 key：

```ini
# 必填：Claude API key
ANTHROPIC_API_KEY=sk-ant-...

# 可选：走代理 / 兼容网关时填
# ANTHROPIC_BASE_URL=
# NOVEL_MODEL=claude-opus-4-8

# 向量召回需要（通义 text-embedding-v3，走 DashScope）
# 不填则写作时自动跳过向量召回，其余功能不受影响
DASHSCOPE_API_KEY=sk-...

# 可选：embedding 端点 / 模型 / 维度
# EMBED_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
# EMBED_MODEL=text-embedding-v3
# EMBED_DIM=1024
```

> `DASHSCOPE_API_KEY` 缺失时，向量召回会静默降级，不影响立项 / 大纲 / 写作 / 校验等其它功能。

---

## 快速上手

```bash
# 1. 立项：一句话创意 → 设定圣经 + 角色库
novel init -i "废柴少年觉醒吞噬天赋，靠吞噬妖兽和敌人的能力逆袭" -g 玄幻 -t 吞噬万古

# 2. 大纲：先骨架（卷弧光），再逐卷展开章节细纲
novel outline --book 吞噬万古 --volumes 5 --chapters 10

# 3. 写作：单章（走完整闭环：节奏→召回→写→校验→固化→索引）
novel write --book 吞噬万古 -c 1

# 4. 批量续写：无人值守连写多章
novel run --book 吞噬万古 -n 5

# 5. 查看进度 / 导出全文
novel status --book 吞噬万古
novel export --book 吞噬万古
```

---

## Web 界面

除了命令行，还提供一个本地 Web 界面：浏览器里完成立项、生成大纲、触发单章/批量写作（带实时进度）、阅读与在线编辑正文、查看世界状态与校验报告。

**开发模式**（前后端分端口，改前端即时热更新）：

```bash
# 终端 1：起后端 API（:8000）
novel serve

# 终端 2：起前端开发服务器（:5173，自动代理 /api 到后端）
cd web && npm install && npm run dev
# 浏览器打开 http://localhost:5173
```

**交付模式**（前端打包后由后端一并托管，只需一个进程）：

```bash
cd web && npm run build      # 产出 web/dist/
novel serve                  # 浏览器打开 http://127.0.0.1:8000
```

界面结构：项目列表 → 进入某本书的工作台（概览 / 设定圣经 / 角色库 / 大纲 / 章节 / 校验记忆）。写作类操作会弹出进度抽屉，通过 SSE 实时滚动「节拍 → 召回 → 写作 → 校验 → 固化 → 索引」每一步，结束展示用量与校验结果。

> 架构：后端 FastAPI 复用全部 `novel_agent` 业务逻辑，长任务在后台线程跑、进度经 SSE 推送；前端 Vite + React + TypeScript。同一本书同时只允许一个写任务（共享世界状态）。

---

## 命令清单

| 命令 | 作用 | 常用参数 |
|------|------|----------|
| `init` | 立项：创意 → 设定圣经 + 初始角色库 | `-i` 创意（必填）、`-g` 题材、`-t` 书名 |
| `outline` | 分层大纲：骨架 + 逐卷章节细纲 | `-v` 卷数、`-c` 每卷章数、`--skeleton-only` 只出骨架 |
| `write` | 写单章（完整闭环） | `-c` 章号（0=下一章）、`-w` 字数、`--overwrite`、`--max-rewrites`、`--no-review`、`--no-vector`、`--no-consolidate` |
| `run` | 无人值守批量续写 | `-n` 章数（0=写到结尾）、`-s` 起点、`-w` 字数、`--stop-on-error`、`--no-vector` |
| `reindex` | 为已写章节补建向量索引 | `--rebuild` 清空重建 |
| `status` | 查看设定、进度、世界状态 | `-b` 项目 slug |
| `list` | 列出所有项目 | — |
| `export` | 合并已写章节为单个 markdown | `-o` 输出路径 |
| `serve` | 启动本地 Web 界面 | `--host`、`-p` 端口 |
| `ping` | 测试 Claude 连通性与用量 | `-p` 测试提示词 |
| `version` | 显示版本 | — |

---

## 单章写作的完整闭环

`write` 和 `run` 的每一章都会走这条流水线：

```
节奏推算 → 向量召回 → 写正文 → 抽取摘要+更新世界状态 → 一致性校验
                                                          │
                              ┌─ 有硬伤且有重写额度 ─→ 带反馈重写（回到写正文）
                              │
                              └─ 通过 / 额度用尽 ─→ 落盘 → 索引进向量库
```

**关键保护**：如果重写后仍有硬伤，正文会保留，但**不会**把（很可能错误的）世界状态写进记忆——记忆维持上一章的干净状态，等人工修正后用 `--overwrite` 重写。校验报告写入 `reviews.json`。

---

## 项目目录结构

每本书是一个自包含目录：

```
books/<书名>/
├── bible.json              # 设定圣经（世界观、力量体系、势力、规则）
├── characters.json         # 角色库
├── outline.json            # 分层大纲（卷 → 章节细纲）
├── state.json              # 世界状态快照（中期记忆）
├── summaries/chapters.json # 滚动章节摘要（中期记忆）
├── reviews.json            # 各章一致性校验报告
├── vectors.npy             # 向量库矩阵（长期记忆）
├── vectors_meta.json       # 向量库元数据
├── chapters/ch0001.md …    # 各章正文
└── 全文.md                 # export 导出的合并稿
```

---

## 代码结构

```
novel_agent/
├── cli.py              # 命令行入口与编排
├── config.py           # 配置加载（.env）
├── project.py          # 项目读写、路径管理
├── storage.py          # JSON/YAML 序列化
├── engine.py           # 单章写作完整闭环（CLI 与 Web 共用）
├── reporting.py        # 进度上报抽象（Console / Queue）
├── llm/                # Claude 网关 + JSON 抽取
├── bible/              # 设定圣经 / 角色模型
├── generate/           # 立项、大纲、单章写作、节奏引擎
├── memory/             # 短期 / 中期 / 长期记忆 + 抽取
├── editor/             # 一致性校验（规则 + LLM）
└── server/             # FastAPI Web API + 长任务/SSE

web/                    # 前端（Vite + React + TypeScript）
├── src/api.ts          # 后端 API 封装
├── src/useTaskStream.ts# SSE 进度订阅
├── src/pages/          # 项目列表 + 工作台 + 各标签页
└── src/components/     # 进度抽屉等
```

---

## 模型用量

- **写作**用 Opus（质量优先），**抽取 / 校验**用 Sonnet（便宜），**向量**用通义 text-embedding-v3
- 每条命令结束会打印本次 token 用量与估算成本
- 写一章正文（约 2500 字）大致在 ¥0.x ~ $0.1 量级；带重写和校验会翻倍

---

## 已知限制

- 向量召回与批量续写目前**只做过离线验证**，尚未用真实 DashScope key 端到端跑通
- 大纲是一次性生成固定卷数 / 章数；写到后期想加卷需手动调整 `outline.json`
- 一致性校验基于"世界状态快照 + 规则 + LLM"，没有独立的实体关系知识图谱
- 暂无自动化测试套件，质量靠人工审阅


