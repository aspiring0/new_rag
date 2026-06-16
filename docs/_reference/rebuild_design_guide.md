# 重建设计与实现指南（Rebuild Design & Implementation Guide）

> 定位：本文是 `project_gap_analysis.md`（诊断书）的姊妹篇。诊断书告诉你"上次哪里坏了"，本文告诉你"怎么从零建对"。
> 目标读者：**知道 RAG/Agent 概念，但没亲手搓过完整项目、不知道怎么设计和实现**的人。
> 每个技术点统一结构：**是什么 → 为什么 → 方案谱系 → 怎么选 → 怎么实现 → 数据流 → 常见坑**。
> 原则：专业性必须有，复杂度不必。能照着设计、照着写代码，且每步能在面试讲清"为什么这么设计"。

---

## 怎么用这份指南

1. **按 Part 顺序读 = 重建搭建顺序**：RAG 内核 → Agent → 接口 → 工程化。
2. **每个技术点先看"方案谱系"和"怎么选"**——这是从"知道一个"升级到"知道有哪些、该选哪个"的关键。
3. **"怎么实现"是设计级**（数据结构、数据流、关键组件），不是抄代码。你照着自己写，每一步可追溯。
4. **"常见坑"对照诊断书**——上次项目踩的坑大多在这些清单里。

---

# Part 1 — RAG 内核：从概念到实现

> RAG 的本质是两句话：**"先检索相关片段，再让 LLM 基于片段回答"**。但"怎么检索得准""怎么切得对""怎么记住用户"才是专业 RAG 的全部技术含量。

## 1.1 文档解析（Parsing）

### 是什么
把 PDF/DOCX/PPTX/HTML/Markdown 等异构文件，转成统一的**纯文本/Markdown 中间表示**，供下游切片。

### 为什么
LLM 不认识 PDF 二进制。必须先"读懂"文档结构（标题、表格、列表、段落），否则切出来的片段是乱的。

### 方案谱系
| 解析器 | 擅长 | 特点 |
|--------|------|------|
| **Docling（IBM）** | PDF/DOCX/PPTX/HTML | 保留结构（标题层级、表格），输出 Markdown |
| **MarkItDown（微软）** | MD/TXT/CSV/简单格式 | 轻量、快 |
| **Unstructured.io** | 通用，元素级（Title/NarrativeText/Table） | 重，依赖多 |
| **Apache Tika** | 几乎所有格式 | 需 Java，结构保留差 |
| **PyMuPDF/pdfplumber** | 纯 PDF | 表格/版面精细控制 |

### 怎么选
- 富文档（PDF/PPT/带表格）→ Docling（保留结构）
- 纯文本/简单格式 → MarkItDown
- 需要元素级标注（区分标题/正文/表格）→ Unstructured
- **统一原则**：无论输入什么，输出统一 Markdown，下游不感知格式

### 怎么实现
**关键组件**：`detect_format()`（按扩展名路由）+ `parse()`（调解析器）+ 文件校验（存在/大小/格式）。
**异步纪律**：解析器是同步的（CPU 密集 + 文件 I/O），**必须** `asyncio.to_thread()` 包装，否则阻塞事件循环。
**数据流**：
```
文件路径 → 校验(存在/大小/格式) → 路由解析器 → to_thread(解析) → Markdown 文本 + 元数据
```

### 常见坑
- ❌ 同步解析器直接在 async 函数里调用 → 阻塞事件循环（上次项目 loader.py 已用 to_thread，正确）
- ❌ 不校验文件大小 → 超大文件 OOM
- ❌ 不同格式各自一套下游逻辑 → 应统一中间表示

---

## 1.2 切片策略谱系（Chunking）⭐ 重点

### 是什么
把长文档切成**检索单元（chunk）**。切片质量直接决定检索上限——切得不好，再好的检索也召回垃圾。

### 为什么
- 向量库按 chunk 存储/检索，chunk 太大→检索不精确+context 浪费，太小→语义断裂。
- **切片是 RAG 的第一道精度闸门**。

### 方案谱系（2026 完整版）

| 策略 | 怎么切 | 适用 | 成本 | 上次项目用了？ |
|------|--------|------|------|--------------|
| **固定大小** Fixed-size | 每 N 字符/token 切，带 overlap | 原型、均匀输入 | $ | 部分 |
| **递归字符** Recursive | 按分隔符优先级切（段落→句子→词→字符） | 通用默认（LangChain 默认） | $ | ✅ |
| **文档结构** Document-based | 按标题/页/段落结构切 | 结构化文档（法律/手册） | $ | ✅（Markdown 标题） |
| **父子切片** Parent-Child | 小块检索、大块（父）喂 LLM | 需精确检索 + 完整上下文 | $ | ❌（未做） |
| **语义切片** Semantic | 嵌入每个句子，按相似度突变点切 | 长文、话题切换（转录/文章） | $$ | ✅（按需） |
| **晚切片** Late Chunking（Jina） | 先对**整篇**嵌入得 token 向量，再池化成 chunk | ≤8K token 文档、保全文上下文 | $$ | ❌ |
| **上下文检索** Contextual Retrieval（Anthropic） | 切片前用 LLM 给每块加"全文上下文摘要"前缀 | 高精度场景 | $$$（每块一次 LLM 调用） | ❌ |

### 关键概念：为什么有这么多切片法？
切片的核心矛盾是 **"检索精度" vs "上下文完整性"**：
- 小块 → 检索精确，但上下文不足 → 答案片面
- 大块 → 上下文足，但检索稀释（relevant 信号被无关内容淹没）

**父子切片、晚切片、上下文检索**都是为解决这个矛盾而生的高级策略。

### 怎么选（决策树）
```
起步 → 递归字符切片（512 token / 50-100 overlap）—— 先让它跑起来
  ↓ 需要更高精度？
结构化文档 → 文档结构切片（按标题）+ 父子检索
长文话题切换 → 语义切片
预算够、要最高精度 → 上下文检索（Anthropic）+ 混合检索 + 重排
长上下文 embedding 模型 → 晚切片（Jina）
```

### 怎么实现
**关键数据结构**：
```python
@dataclass
class Chunk:
    content: str          # 切片文本
    metadata: dict        # chunk_index, source_path, header_path, char_count, ...
```
**递归字符切片算法**（你上次实现了，是样板）：
1. 按最高优先级分隔符切（`["\n\n", "\n", "。", ".", " ", ""]`）
2. 若某片段仍 > chunk_size，用下一级分隔符递归切
3. 合并相邻片段到 ≤ chunk_size
4. 相邻 chunk 保留 overlap（尾部文本共享），避免上下文断裂

**父子切片实现要点**：存两个粒度——child（小，用于检索）+ parent_id（大，用于喂 LLM）。检索命 child，返回其 parent。

**上下文检索实现要点**：切片后、嵌入前，对每块调一次轻量 LLM（如 Haiku）生成"这块在全文档中的位置/作用"摘要，拼到 chunk 前面再嵌入。

### 数据流
```
Markdown 文本 → 选策略 → 切分 → 加 overlap → 加元数据 → Chunk 列表 → 嵌入 → 入库
```

### 常见坑
- ❌ chunk_size 硬编码 → 应来自 config（上次项目参数化，正确）
- ❌ 无 overlap → 跨块信息断裂
- ❌ 切片打乱后丢失来源/位置元数据 → 无法回溯引用
- ❌ 一上来就用最贵的（上下文检索）→ 先递归切片跑通，按需升级

---

## 1.3 嵌入与向量索引（Embedding & Indexing）

### 是什么
**嵌入**：文本 → 高维向量（语义相近→向量相近）。
**索引**：把向量组织成可快速近邻搜索的数据结构。

### 为什么
- 向量检索的本质是"语义相似度匹配"，靠 embedding 把语义编码进向量空间。
- 暴力遍历全库算相似度是 O(N)，索引（IVF/HNSW）降到近似 O(logN)。

### 方案谱系
**嵌入模型**：OpenAI text-embedding-3、智谱 embedding-3、BGE、Jina v2（支持晚切片）、Cohere。
**索引类型**：
| 索引 | 原理 | 特点 |
|------|------|------|
| **FLAT** | 暴力遍历 | 精确，慢，小库 |
| **IVF_FLAT** | 聚类成簇，查时只扫近簇 | 近似，快，精度可调（nprobe） |
| **HNSW** | 层次化小世界图 | 查询极快，构建慢，内存大 |
| **IVF_PQ** | IVF + 乘积量化压缩 | 省内存，精度损失 |

**相似度度量**：Cosine（方向相似，最常用）、L2（距离）、IP（内积）。

### 怎么选
- 中小库 + 精度优先 → IVF_FLAT（上次项目用这个，nprobe 调高提精度）
- 大库 + 延迟优先 → HNSW
- 海量库 + 内存敏感 → IVF_PQ

### 怎么实现
**嵌入 Pipeline（4 层，上次设计了）**：
```
文本列表 → ①Redis缓存(命中直返) → ②Singleflight去重(并发同查只算1次)
        → ③批量拆分(避免超API限制) → ④分布式限流(防超QPS) → 嵌入API → 写回缓存
```
**缓存 key**：必须用 SHA-256（跨进程一致），不能用 Python `hash()`（每进程加盐不同）。

### 常见坑
- ❌ 用 Python `hash()` 做缓存 key → 跨 worker 不一致（上次用 content_hash，正确）
- ❌ 每次请求都调嵌入 API → 必须缓存
- ❌ 不限流 → 撞 API QPS 限制被拒
- ❌ 索引参数（nlist/nprobe）硬编码 → 应进 config

---

## 1.4 检索策略谱系（Retrieval）⭐ 重点

### 是什么
给定查询，从知识库召回相关 chunk。**检索质量直接决定答案质量**——"垃圾进，垃圾出"。

### 为什么
单一检索都有盲区：
- 向量检索：语义相似强，但精确关键词（型号/代码/专有名词）匹配弱
- 关键词检索（BM25）：精确匹配强，但不理解同义词/语义
- 没有任何一种检索能通吃

### 方案谱系（完整版）

| 策略 | 怎么工作 | 最适合 | 上次项目用了？ |
|------|---------|--------|--------------|
| **稀疏检索** BM25 | 词频统计，关键词匹配 | 精确关键词、ID、代码、人名 | ✅ |
| **稠密检索** Vector | 语义相似度 | 语义相似、同义改写 | ✅ |
| **混合检索** Hybrid | 向量+BM25，RRF 融合 | 通用，几乎总是更好 | ✅ |
| **HyDE** | LLM 先生成"假设答案文档"，用它做向量检索 | 零样本/语义查询（query-doc 嵌入鸿沟大） | ❌ |
| **多查询/RAG-Fusion** | LLM 生成多个查询变体，各检索后 RRF 融合 | 模糊/多面查询 | ❌ |
| **父子检索** Parent-Child | 检索小块，返回父块 | 需精确检索+完整上下文 | ❌ |
| **Ensemble** | 多个检索器并行，结果合并 | 无单一检索器主导时 | ❌ |
| **图谱检索** GraphRAG | 实体关系遍历（多跳推理） | 跨文档实体关系推理 | ✅（Neo4j） |

### 关键技术：RRF（倒数排名融合）
融合多路结果的核心公式（不依赖各路分数绝对值，只依赖排名）：
```
RRF_score(d) = Σ_i  weight_i / (k + rank_i + 1)   # k 通常=60
```
**为什么用 RRF**：向量分数（cosine 0-1）和 BM25 分数（无界）不可直接比，RRF 用排名绕过了这个问题。

### 怎么选（决策树）
```
通用基线 → 混合检索（向量+BM25，RRF）—— 90% 场景够用
  ↓ 需要实体关系推理？
是 → 加图谱检索（GraphRAG，三路融合）
  ↓ 查询模糊/多义？
是 → 加多查询/RAG-Fusion
  ↓ 零样本、检索召回差？
是 → 加 HyDE
  ↓ 检索精但答案缺上下文？
是 → 父子检索（小块检索、大块喂 LLM）
```

### 怎么实现（混合检索，上次项目的样板）
**关键组件**：`HybridRetriever`，三路并行/串行 → RRF 融合 → 去重 → 截断 top_k。
**数据流**：
```
查询 → 嵌入
     ├→ 向量检索（Milvus）→ 排序列表1
     ├→ BM25 检索（内存索引）→ 排序列表2
     └→ 图谱检索（Neo4j，可选，失败降级）→ 排序列表3
              ↓
     RRF 融合（按 content 去重，分数累加）
              ↓
     按融合分数降序 → 截断 top_k → RetrievalResult(degraded=是否降级)
```
**降级语义**：图谱不可用 → degraded=True，仍用向量+BM25 返回（用户无感知）。

### 常见坑
- ❌ 只用向量检索 → 精确关键词召回差
- ❌ 三路结果直接按分数加和 → 分数不可比，必须用 RRF（按排名）
- ❌ 检索串行（向量→BM25→图谱）→ 延迟叠加，应并行 `asyncio.gather`
- ❌ 降级不标记 → 故障不可观测（上次项目有 degraded 标记，正确）

---

## 1.5 重排（Reranking）

### 是什么
检索是**粗筛**（快但粗），重排是**精排**（慢但准）。对 top-K 候选用更强的模型重新打分排序。

### 为什么
检索用的 Bi-Encoder（query、doc 分别编码）快但不捕捉 query-doc 交互特征；重排用 Cross-Encoder（query+doc 拼接编码）精确但慢。两阶段：先粗筛 top-10，再精排 top-3。

### 方案谱系
| 重排器 | 类型 | 特点 |
|--------|------|------|
| **Cohere Rerank** | API | 最强质量，付费 |
| **BGE Reranker** | 本地 Cross-Encoder | 免费但需下载模型 |
| **bge-reranker-v2-m3** | 本地，多语言 | 中文友好 |
| **原始排序** Raw | 无 ML，按检索分排序 | 兜底，保证成功 |

### 怎么实现（降级链）
```
首选 Cohere → (失败/无key) → BGE 本地 → (失败/未装) → Raw 兜底
```
**关键**：降级链每一层都要在目标环境验证真实可用，不能只靠 mock 测试（上次项目 Cohere 无 key、BGE 未装，实际只跑 Raw）。

### 常见坑
- ❌ 设计了降级链但每层都没在 prod 验证 → 实际只跑兜底
- ❌ BGE 模型运行时下载 → 首调用超时降级，应预打包

---

## 1.6 记忆系统（Memory）⭐ 你的最大概念盲区

> 这是 RAG 和 Agent 的分水岭。**RAG 是无状态的检索，记忆是有状态的积累**。上次项目只有 RAG（无记忆），所以 Agent 无法自进化。

### 是什么
让系统**跨会话记住**用户偏好、历史交互、学到的经验，而不是每次都从零开始。

### 为什么 RAG ≠ 记忆
| 维度 | RAG（上次项目现状） | 真正的记忆（Memory） |
|------|---------------------|---------------------|
| 状态 | **无状态**，查静态文档索引 | **有状态**，跨会话持久 |
| 更新 | 文档不变则结果不变 | 需要**显式写入机制**更新内部状态 |
| 学习 | 无 | 从交互中积累偏好和经验 |
| 例子 | 查"公司制度"→返回文档段 | 记住"用户偏好简洁回答""上次纠正过 X" |

**类比**：RAG 像"查百科全书"，记忆像"你的私人助理记的本子"。

### 方案谱系（记忆类型，借鉴认知科学）

| 类型 | 存什么 | 例子 | 实现 |
|------|--------|------|------|
| **短期/工作记忆** | 当前会话上下文 | 这轮对话前面说了啥 | 对话历史（Redis TTL） |
| **长期-语义记忆** | 事实/知识 | "用户是工程师""公司用 Milvus" | 向量库/知识库 |
| **长期-情景记忆** | 过去事件（带上下文） | "上周二用户问过 X，答案是 Y" | 时序存储 + 检索 |
| **长期-程序记忆** | 技能/工作流 | "处理退款要按这 5 步" | 技能库/SOP |

### 记忆架构谱系
| 架构 | 代表 | 特点 |
|------|------|------|
| **向量记忆** | 简单 RAG 扩展 | 记忆存向量库，按相似度检索 |
| **图记忆** | Mem0g / GraphRAG | 记忆存知识图谱，支持关系推理 |
| **混合记忆** | Mem0 / Letta / Zep | 向量 + 图 + 时序，动态提取/合并 |
| **全上下文** | OpenAI Memory | 把所有历史塞进 context（贵） |

### 怎么选
- 只需会话连贯 → 短期记忆（对话历史）
- 需记住用户事实 → 长期语义记忆（向量库）
- 需跨会话学习/个性化 → Mem0 式混合记忆（提取→合并→检索）
- 需关系推理 → 图记忆（你已有 Neo4j，天然适合！）

### 怎么实现（记忆的三个核心操作，区别于 RAG）
```
① 提取（Extract）：从交互中抽出值得记的事实/偏好
   "用户说：我是后端工程师" → 记忆条目：{user.role: backend_engineer}
② 合并/更新（Consolidate）：新记忆与旧记忆去重、冲突解决、更新
   旧：{user.role: student} + 新：{user.role: backend_engineer} → 冲突，以新为准
③ 检索（Retrieve）：回答时拉相关记忆注入 context
   查询 → 相似度 + 时序 + 聚类 → 相关记忆 → 注入 prompt
```
**关键区别**：RAG 只做③（检索静态文档），记忆要做①②③（动态提取+合并+检索）。这就是"显式写入机制"。

### 上次项目为什么没记忆（诊断书呼应）
- 有 Neo4j 但只用于**文档实体**，没用于用户记忆
- Reviewer 拒绝原因不沉淀 → 无法从错误学习（无情景记忆）
- 只有会话级对话历史（短期），无长期

### 常见坑
- ❌ 把 RAG 当记忆用 → 无状态，记不住用户
- ❌ 记忆只存不合并 → 越积越脏，冲突记忆泛滥
- ❌ 记忆无遗忘机制 → 无限膨胀，检索噪声大
- ❌ 记忆无隐私/租户隔离 → 用户 A 看到用户 B 的记忆（致命）

---

## 1.7 生成与引用（Generation & Citation）

### 是什么
基于检索到的片段 + 用户问题，让 LLM 生成答案，并强制标注来源。

### 为什么
- 无引用 → LLM 可能幻觉，且无法溯源验证
- 强制引用 → 把答案锚定在真实文档上，可验证、可信任

### 怎么实现（上次项目的成功样板）
1. 检索结果按序编号：`[来源 1] ... [来源 2] ...`
2. Worker 的 system prompt 明确要求："每个关键论点必须标注 [来源 N]"
3. Reviewer 检查：答案里是否有引用标记 + 是否对应真实来源
4. 结果：幻觉率 0%、引用准确率 100%

### 常见坑
- ❌ 不强制引用 → 幻觉不可控
- ❌ 对抗性/不可答输入不处理 → 应明确拒答而非编造（上次项目对抗查询零幻觉，正确）

---

# Part 2 — Agent 设计：范式与编排

> Agent 的本质是 **"能自主感知-决策-行动-观测的循环"**。不是"调一次 LLM 生成"。

## 2.1 什么是 Agent / 为什么多 Agent

**单次 LLM 调用 ≠ Agent**。Agent 的特征是**自主循环**：根据观察决定下一步动作。

**为什么多 Agent**：一个 LLM 同时做意图理解+检索+生成+质检，prompt 过长、职责混乱、难调优。拆成专职 Agent（像团队分工）更可控、可调试、可演进。

## 2.2 范式谱系 ⭐

| 范式 | 机制 | 适用 | 短板 |
|------|------|------|------|
| **ReAct** | Thought→Action→Observation 循环 | 动态环境、工具调用 | 短视，无全局规划 |
| **Plan-and-Execute** | 先规划全局计划，再逐步执行 | 复杂多步任务 | 计划僵化，环境变需重规划 |
| **Reflexion** | 失败后自省，沉淀反思记忆 | 可重试任务（编程/推理） | 多次尝试，延迟/成本高 |
| **Multi-Agent** | 多 Agent 分工协作 | 复杂工程化 | 协调成本、矛盾仲裁 |

**核心洞察**：ReAct 胜速度，Plan-Execute 胜正确性，Reflexion 胜学习。趋势是**混合**。

### 上次项目是什么范式
**固定工作流 + 轻量多 Agent**（Router→Worker→Reviewer），**不是真智能体**：
- Worker 开环，不调用工具（无 ReAct）
- 无全局规划（无 Plan-Execute）
- 反思不沉淀（无 Reflexion）→ 无法自进化

## 2.3 怎么选范式
```
知识库 QA（可控优先）→ 固定工作流（上次范式，合理）
需要调用工具（搜索/计算/DB）→ ReAct
复杂多步任务 → Plan-and-Execute
需要从错误学习 → + Reflexion
需要专家分工 → Multi-Agent
```

## 2.4 编排框架选型
| 框架 | 定位 |
|------|------|
| **LangGraph** | 图编排，条件路由/循环检测/状态持久/流式（上次选型，正确） |
| **CrewAI** | 角色协作，简洁 |
| **AutoGen** | 对话式多 Agent |
| **OpenAI/Google/Claude SDK** | 官方一体化 |

## 2.5 Agent + 记忆 + RAG 怎么协同
```
用户问题
  ↓
[短期记忆] 当前会话上下文
[长期记忆] 用户偏好/历史（Mem0 式）──┐
[RAG 检索] 知识库文档片段 ──────────┤→ 注入 Agent 的 context
[工具] web_search/db_query（ReAct 调用）─┘
  ↓
Agent 推理 + 行动循环 → 答案
  ↓
[记忆写入] 本次交互值得记的事实/纠错（这就是"自进化"的来源）
```
**关键**：Agent 跑完后**回写记忆**，下次更聪明。这是从"会查文档"升级到"会学习"的分水岭。

---

# Part 3 — 接口与全栈设计

## 3.1 API 契约设计

### 是什么
定义前后端/客户端与服务端的**接口契约**：URL、请求/响应 schema、状态码、错误结构。

### 怎么实现（专业要点）
- **Schema 单一来源**：所有请求/响应用 Pydantic 定义，前端从 OpenAPI 生成类型（上次项目正确）
- **统一错误结构**：所有错误返回同一 schema `{error: {code, message, details}}`，不要每个路由各写各的
- **分页统一**：所有列表用同一套 `skip/limit + Query(ge=, le=)` 校验，禁止裸 `int`
- **流式用 SSE**：LLM 逐 token 输出用 SSE（Server-Sent Events），不用 WebSocket（除非需要双向）

### 常见坑（上次项目踩的）
- ❌ 同一故障不同状态码（Redis 宕：list 返 200 空、delete 返 503）→ 统一策略
- ❌ 分页校验不一致 → 客户端可传 `limit=1000000`
- ❌ SSE 超时后先 error 再 done（空 sources）→ 破坏终态语义

## 3.2 认证与授权模型

### 是什么
**认证（AuthN）**：你是谁。**授权（AuthZ）**：你能干什么。两件事，别混。

### 怎么实现
- **认证**：JWT（携带 user_id/tenant_id/role claims）+ API Key（显式映射到身份，**禁止默认租户**）
- **授权**：逐路由 guard，基于 role/tenant，中间件统一注入
- **租户身份唯一来源**：只能从认证态派生，**禁止接受客户端传入 tenant_id**（上次项目 IDOR 漏洞的根因）

## 3.3 异常体系设计 ⭐ 上次最乱的地方

### 是什么
自定义异常类层次 + **异常→HTTP 状态码的统一映射表**。

### 怎么实现
**异常层次**（按业务域）：
```
RAGAgentError（基类）
├─ StorageError → 503
├─ RetrievalError → 503（降级时 200+degraded）
├─ ValidationError → 422
├─ AuthError → 401/403
├─ QuotaExceeded → 429
└─ ...
```
**铁律**：
1. 每种业务异常对应**明确**状态码，全项目唯一映射表
2. **禁止静默吞异常**：每个 except 至少 `logger.warning` 带上下文
3. 全局兜底 handler **先放行** HTTPException/ValidationError，再兜其余
4. 状态变更（计费/计数）**原子化**（Lua/MULTI），禁止非原子读-改-写

### 常见坑（上次项目踩的）
- ❌ 6 处 `except Exception: pass` 无日志 → 故障黑洞
- ❌ 全局 handler 吞掉 HTTPException → 404 变 500
- ❌ 费用聚合非原子 → 计费丢更新

## 3.4 流式响应设计（SSE done right）

### 怎么实现
- 事件序列：`thinking → retrieval → answer(逐token) → done`
- **终态语义**：`done` 是唯一终态；超时/错误时 `done` 要带 `error` 字段，不要发"空 sources 的假成功"
- **背压**：客户端断连要能感知并停止生成（`await request.is_disconnected()`）

---

# Part 4 — 工程化保障（Quality Gates）

> 这部分是把"会写功能"升级到"能交付可靠系统"的关键。上次项目功能写了，但保障层空心。

## 4.1 分层门禁（Layer Gates）
**规则**：L0 过门禁才能开 L1，逐层上锁。每层有验收脚本（`validate_pN.sh`），**过了才进下一层**。
上次项目有这些脚本但没真正执行——重建必须当真。

## 4.2 测试金字塔（真实 vs mock）
```
        E2E（少，真服务，关键路径）
       集成（少，真后端，CI 起服务）   ← 上次全是 mock，是假的
      单元（多，快，mock）
```
**铁律**：集成测试必须打**真实** Milvus/Neo4j/Redis，禁用 mock 冒充集成。关键不变量有专项测试：租户隔离（双租户泄漏测试）、降级（中途杀服务）、熔断（真实 Redis）。

## 4.3 可观测性闭环 ⭐ 上次最大表象
**四环必须全连通**，断一环全链失效：
```
产生指标(代码 inc) → 导出(/metrics 端点) → 采集(Prometheus) → 展示(Grafana)
```
**铁律**：每个被仪表盘查询的指标，必须能 grep 到真实写入点；上线后人为制造一次命中，确认数字真的变化（防"指标假"）。
**追踪**：FastAPI 自动 instrument + OTLP exporter 真实导出 → Jaeger 真有 span。

## 4.4 一个 PR 的标准生命周期（构建纪律）
```
1. 选当前层最小一个单元
2. 写该单元 DoD（含可运行验收命令）
3. TDD：先写失败测试
4. 实现到通过
5. 真实验证（打真实服务，非 mock）
6. 一个 PR，描述贴 DoD + 验证证据
7. 人审 + code-review 过才 merge
8. 更新 PROGRESS.md
9. 该层单元全完成 → 跑层门禁 → 过了进下一层
```
**核心纪律**：一次 vibecoding = 一个 PR 单元，不是一堆任务。门禁必须**阻断**，不能 warn-skip。

---

# 总结：从"知道"到"会实现"的地图

| 你知道的 | 这份指南帮你建立的 | 实现关键 |
|---------|-------------------|---------|
| 向量检索 | 完整检索谱系 + 怎么选 + 怎么融合 | 混合检索 + RRF |
| 切片 | 完整切片谱系 + 父子/语义/晚切片/上下文 | 先递归起步，按需升级 |
| RAG | RAG ≠ 记忆，记忆的提取/合并/检索三操作 | Mem0 式混合记忆 |
| Agent | ReAct/Plan-Execute/Reflexion 范式 + 何时用 | 按需选范式，Agent+记忆+RAG 协同 |
| 接口 | 契约设计 + 异常映射表 + SSE 终态 | 统一 schema/错误/状态码 |
| 工程 | 门禁 + 真实测试 + 可观测闭环 + PR 纪律 | 门禁阻断，不 warn-skip |

> **下次开干时**：我们按 Part 1→4，一个单元一个 PR，每个 DoD 带"我手动验证了它真的在跑"。我会带你走完，但不替你写——你写、我审、过门禁才前进。

---

## 参考来源

### 切片策略
- [Anthropic – Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)
- [Jina AI – Late Chunking](https://jina.ai/news/late-chunking-in-long-context-embedding-models/)
- [Firecrawl – Best Chunking Strategies for RAG 2026](https://www.firecrawl.dev/blog/best-chunking-strategies-rag)
- [Pinecone – Chunking Strategies](https://www.pinecone.io/learn/chunking-strategies/)

### 检索策略
- [Atlan – 12 Advanced RAG Techniques](https://atlan.com/know/advanced-rag-techniques/)
- [Neo4j – Advanced RAG Techniques](https://neo4j.com/blog/genai/advanced-rag-techniques/)
- [NirDiamant/RAG_Techniques (GitHub)](https://github.com/NirDiamant/RAG_Techniques)

### 记忆系统
- [Mem0 – State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- [Mem0 Research Paper (arXiv)](https://arxiv.org/html/2504.19413v1)
- [Letta – RAG is not Memory](https://www.letta.com/blog/rag-vs-agent-memory/)
- [Graph-Based Agent Memory Guide](https://shibuiyusuke.medium.com/graph-based-agent-memory-a-complete-guide-to-structure-retrieval-and-evolution-6f91637ad078)

### Agent 范式
- [Andrew Ng – Agentic Design Patterns (Reflection)](https://www.deeplearning.ai/the-batch/agentic-design-patterns-part-2-reflection)
- [ReAct vs Plan-and-Execute](https://dev.to/jamesli/react-vs-plan-and-execute-a-practical-comparison-of-llm-agent-patterns-4gh9)
