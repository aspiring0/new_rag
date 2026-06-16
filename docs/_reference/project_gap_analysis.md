# 项目重建参考基线（Rebuild Reference Baseline）

> 调研日期：2026-06-17
> 定位：这是一份**推翻重建的储备文档**，不是修复清单。
> 用途：为下一次"从底层逐层专业搭建"提供可追溯的基线。每个维度记录三件事——**当前真实状态**（基线快照）、**暴露的教训**（重建须避开的陷阱）、**专业基线要点**（重建该层时必须建立的决策与原则，不含代码补丁）。
> 核查方法：所有"当前真实状态"均经实地核查（git/gh 命令、真实 `.env`、运行时 docker exec、全仓库 grep）。

---

## 如何使用本文档

1. **按层从底向上读**：Layer 0 → Layer 5，正是重建时的搭建顺序。底层未稳，上层勿动。
2. **每层独立可验收**：每层结尾的"专业基线要点"是该层的**验收清单**——一项不达标，该层不算完成。
3. **由你亲自实现**：本文档只给原则与决策点，不给代码。你对照基线要点自己写，每步可追溯、可解释、可面试讲清。
4. **不写修复补丁**：刻意不写"把 X 行改成 Y"。"专业基线要点"是原则级（如"租户身份只能来自服务端认证态"），不是行级修复。

---

## 全景分层总览

| 层 | 维度 | 一句话状态 |
|----|------|-----------|
| **L0 工程地基** | Git 协作 · 依赖 · 配置 · 规范分层 | 协作流程缺失，地基不稳 |
| **L1 基础设施** | 存储连接 · 部署编排 · 多租户 | 连接生命周期与健康门禁缺失 |
| **L2 RAG 管线** | 解析分块 · 向量库 · 嵌入 · 摄入一致性 · 检索 · 重排 · 生成 | 业务逻辑扎实，外围保障空心 |
| **L3 Agent** | 范式框架 · 技能 · 工具 | 是固定工作流，非真智能体 |
| **L4 接口全栈** | API 契约 · 认证授权 · 异常体系 · 安全防御 | 异常处理与租户边界是重灾区 |
| **L5 质量运维** | 测试 · 可观测性 · 性能并发 · 成本 · 发布 | 可观测性与测试真实性是最大表象 |

---

# Layer 0 — 工程地基（Engineering Foundation）

> 没有这一层，后面所有层都建在沙地上。**重建必须先立这一层，再写一行业务代码。**

## 0.1 Git 协作与版本控制

**当前真实状态**
- 仓库历史 **0 个 PR**（`gh pr list --state all` → `[]`），仅有 `main` 单分支。
- `main` 无任何保护规则（protection → 404，rulesets → `[]`），所有工作直接提交 main。
- 工作区 **32 个未提交文件**（10 改 + 22 新增），含 vendored `.whl` 直接躺在根目录。
- CI 的 `pull_request` 触发器**从未触发过**；`gh run list` 为空。
- 提交格式部分符合规范（`type(scope): desc`），但 CLAUDE.md 要求的 `type(task_id):` 位置不对（ID 被放成 `(ID)` 后缀）。
- 声称"全面重建"，但 git 根部仍残留旧的脏提交（`second_updata_multi_agent` 含拼写错误）。

**暴露的教训**
- "无法审查代码"的本质是**协作流程根本没建立**：无分支、无 PR、无 review 入口、无保护。
- 直接提交 main + 无保护 = 任何错误直奔主干，无法回溯、无法隔离实验。
- 未提交文件堆积 = 工作无原子单位，无法定位"哪个改动引入了什么"。

**专业基线要点（重建须建立）**
- 分支模型：所有改动走 feature/fix 分支，禁止直推 main。
- PR 必备：每个合并单元一个 PR，PR 是 review、CI、回滚的最小单位。
- 分支保护：main 要求 PR + 通过状态检查 + 禁止 force-push + 线性历史。
- 提交规范：落实 `type(task_id): description`，每个提交是一个逻辑原子（可单独 revert）。
- `.gitignore` 纪律：二进制制品（`.whl`）、数据库文件、`venv/`、`data/`、`logs/` 一律不入库。
- 历史干净：重建即从干净初始提交开始，不背旧账。

## 0.2 依赖锁定与版本管理

**当前真实状态**
- `requirements.txt` 全部精确锁定（`==`），无 `>=`，符合规范。
- 新增依赖需 ADR（CLAUDE.md 规则 #5）。
- 隐患：`sentence-transformers==3.3.1` 已锁定，但运行环境未安装，BGE 首调用要下载几百 MB 模型；本地 `.whl` 强制重装是脆弱 monkey-patch（`Dockerfile:38-40`）。

**暴露的教训**
- 锁定版本 ≠ 运行时可用。锁了但没装、装了但下载外部资源，都是隐性故障。
- 用 vendored `.whl` 绕过版本冲突，是把问题藏起来而非解决。

**专业基线要点（重建须建立）**
- 精确锁定 + 锁文件（`requirements.txt` 或 `poetry.lock`/`uv.lock`）双保险。
- 每个依赖可追溯：为什么引入（ADR）、用于何处、是否在运行时真正可用。
- 外部资源（模型权重）需预下载或打包，不能依赖首调用即时拉取。
- 容器构建可复现：同一 lockfile → 同一镜像。

## 0.3 配置管理（Config & Secrets）

**当前真实状态**
- `core/config.py` 用 pydantic-settings 集中配置（符合规范）。
- 但 `os.getenv` 泄漏到 config.py 之外：`web_search.py:58`、`security.py:72,111`、`auth.py:163`（**每次请求读一次**）。
- 关键 key 默认空字符串（`zhipu_api_key=""`、`cohere_api_key=""`），pydantic **只校验类型不校验存在性** → 缺 key 时静默启动，首请求才 401。
- 弱 secret（`jwt_secret="dev-secret-change-in-production"`）：`_check_production_security()` 只 `warn`，不 `raise`。
- 启动期从不调用任何 `health_check()`；lifespan 的预检全包在 `try/except: warning` 里。

**暴露的教训**
- 配置校验停留在"类型对"，缺"关键值必须存在"——这是 fail-silent 而非 fail-fast。
- 配置源不唯一（config.py 与散落的 os.getenv 并存），值会漂移、会读性能差。
- secret 弱值只告警不阻断，等于没防护。

**专业基线要点（重建须建立）**
- 单一配置源：所有配置项只从 `config.py` 读，禁止业务代码碰 `os.getenv`。
- 启动期 fail-fast 校验：关键 key（LLM/Embedding/DB/secret）缺失或缺省值即拒启动，分环境（dev 放行、prod 拒绝）。
- secret 管理：dev 用占位、prod 用强随机 + 外部注入（env/secret manager），禁止弱值进 prod。
- 配置可观测：启动时打印"已加载哪些后端、哪些 key 就绪"（脱敏），让就绪状态显式。

## 0.4 编码规范与分层架构

**当前真实状态**
- CLAUDE.md 有 10 条强制规则 + 12 条反模式，规范本身专业完整。
- 已核查干净：无 `eval/exec`、`hashlib` 仅在 hash.py、无 md5、Neo4j 用 MERGE、LLM 全异步、解析器正确 to_thread。
- 但多处违反：async 路径里同步 I/O 未包装（`chunk_document`、`open/shutil`）、魔法数字散落（`nlist:128`、超时、SCAN count 100 vs 500 不一致）、`os.getenv` 泄漏、`dict`/`list` 裸标注。

**暴露的教训**
- 规范写在文档里 ≠ 规范被执行。没有自动化 enforcement，规则会持续被无声违反。
- 魔法数字不一致（SCAN count 各文件不同）说明"无统一来源"时必然漂移。

**专业基线要点（重建须建立）**
- 分层架构强制：core / infra / rag / agents / api / observability 职责单一，依赖单向（上层依赖下层）。
- 自动化 enforcement：ruff/mypy/pre-commit 把"async 包装、类型注解、魔法数字、os.getenv 泄漏"变成 CI 硬卡点，而非靠人记。
- 规范即代码：把 CLAUDE.md 规则转成可执行的 lint 规则与测试断言。

---

# Layer 1 — 基础设施（Infrastructure）

## 1.1 存储选型与连接生命周期

**当前真实状态**
- 选型有 ADR 支撑：Milvus（向量，partition key 多租户）、Neo4j（图谱，MERGE 幂等）、Redis（缓存/队列/限流/计费）。
- 连接单例：Neo4j 和 Milvus 正确用 `asyncio.Lock` 防竞态；**Redis 没有**（`redis.py:39-58` TOCTOU 未修，改进计划标注但未做）。
- `health_check()` 方法三处都有（neo4j/redis/milvus），**但启动期从不调用**。
- Neo4j 已接入检索（`graph_store=None` 那个 bug 早修了），但 `Neo4jStore.__init__` 不预检连通性 → 宕机时静默降级。

**暴露的教训**
- "连上了吗"是运行时第一个要回答的问题，但系统用静默降级回避了它。
- 连接单例的线程安全是基本功，Redis 漏锁说明这类"看不见的并发 bug"最易被忽略。

**专业基线要点（重建须建立）**
- 连接生命周期三件套：**锁定单例**（asyncio.Lock 防 TOCTOU）+ **启动健康探测**（fail-fast）+ **运行时自愈**（失败重置、下次重连）。
- 健康门禁：启动期对每个后端做真实探活，关键后端不可达即拒启动（而非带病上岗）。
- 连接池参数化、可观测（池大小、活跃连接数暴露为指标）。

## 1.2 部署与环境编排

**当前真实状态**
- `docker-compose.yml` 13 服务，绝大多数有 healthcheck（api/frontend/milvus/etcd/minio/neo4j/redis/jaeger/prometheus/grafana）。
- 但 **`redis-exporter`、`node-exporter` 无 healthcheck**。
- `api.depends_on.neo4j` 用 `service_started` 而非 `service_healthy` → API 可能比 Neo4j 先就绪 → 首批查询降级（Redis/Milvus 正确用了 healthy）。
- prod overlay 用 `!reset` 需 Compose ≥ 2.24；frontend 端口 80 冲突（已遇到）。

**暴露的教训**
- 启动顺序错一个 `service_started`，整个图检索首请求就静默退化。
- healthcheck 完整性是"服务编排"的核心，漏一个 exporter 就少一块监控视野。

**专业基线要点（重建须建立）**
- 启动依赖图：被依赖方必须 `condition: service_healthy`，禁止用 `service_started` 兜底。
- healthcheck 全覆盖：每个服务都要有，start_period 给足冷启动时间。
- 环境分层：dev / staging / prod overlay 清晰，prod 资源限制、日志、重启策略、端口收敛（敏感端口不暴露）。
- 编排可验证：`docker compose up` 后有一条"全服务 healthy"的验收脚本。

## 1.3 多租户隔离

**当前真实状态**
- 隔离设计专业：Milvus partition key + `TenantFilteredStore` 基类 + ContextVar 协程级传播 + Neo4j 租户标签。
- **但有真实后门**：
  - `chat.py:232,302`：`body.tenant_id or user.tenant_id` → 客户端传入的 tenant_id **静默覆盖**认证态 → IDOR。
  - API Key 认证硬编码 `tenant_id="default"`、`role="service"` → 任何 key 持有者读写 default 租户。
- 租户隔离的测试只断言 filter **字符串**生成正确，从未用真实双租户数据验证无泄漏。

**暴露的教训**
- 隔离代码写得严谨，但一个"接受客户端 tenant_id"的口子就把整面墙拆了——**隔离是端到端的，任何一环松懈等于全无**。
- "filter 字符串对"不等于"数据真的隔离"。必须用真实数据测泄漏。

**专业基线要点（重建须建立）**
- 租户身份唯一来源：**只能从服务端认证态派生**（JWT claims / API key 映射），禁止接受客户端传入的 tenant_id。
- fail-closed：无租户上下文即拒（RuntimeError），不留默认值兜底。
- 隔离测试金标准：双租户真实数据 + 交叉查询 + 断言"互不可见"，覆盖 Milvus/Neo4j/Redis 三库。

---

# Layer 2 — RAG 数据管线（RAG Pipeline）

> 业务逻辑层是本项目最扎实的部分，但外围保障（计数、状态真实性、运行时生效）空心。

## 2.1 文档解析与分块

**当前真实状态**
- 解析器路由专业：Docling（PDF/DOCX/PPTX/HTML，保留结构）+ MarkItDown（MD/TXT），统一输出 Markdown，`to_thread` 包装（合规）。
- 分块三策略：递归字符（分隔符优先级）、Markdown 标题层级（带 header_path）、语义切分（按需）。
- 参数化（chunk_size/overlap 来自 config，合规）。

**暴露的教训**
- 这一域基本无大问题，可作为重建的"已达标样板"参照。

**专业基线要点（重建须建立）**
- 格式无关的统一中间表示（Markdown），上层不感知输入格式。
- 结构保留（标题路径、表格、列表）随 chunk 元数据流转。
- 解析/分块全异步、可超时、可重试。

## 2.2 向量存储 Schema 与索引

**当前真实状态**
- 单 collection + partition key 多租户（ADR-011），schema 6 字段（id=SHA256 / tenant_id=partition key / content / metadata / embedding / embedding_version）。
- IVF_FLAT 索引（nlist=128, nprobe=32），upsert 幂等（内容哈希覆盖）。
- 索引参数 `nlist/nprobe` 硬编码在代码而非 config；内容截断 8192 字符。

**暴露的教训**
- Schema 设计良好（含 embedding_version 支持迁移），但调优参数应可配置可演进。
- 单 collection 多租户是对的，但必须配合强隔离测试（见 1.3）。

**专业基线要点（重建须建立）**
- Schema 版本化（embedding_version 字段），支持平滑迁移。
- 索引参数（index type / nlist / nprobe / metric）全部进 config，可调可不改码。
- 写入幂等（内容哈希 upsert），删除可追溯（soft-delete）。

## 2.3 嵌入 Pipeline

**当前真实状态**
- 设计了 4 层：Redis 缓存（24h，work）→ Singleflight 去重（**当前是占位，未实现**）→ 批量拆分（50）→ 分布式限流（RedisSemaphore，work）。
- 缓存 key 用 SHA-256（合规，跨进程一致）。
- **计数断层**：摄入路径的 embedding 缓存命中（`embedding.py:115`）**完全不计指标**，只有查询路径计数。

**暴露的教训**
- "设计了 4 层"不等于"实现了 4 层"。Singleflight 是 ADR-009 的核心，却是占位。
- 高频路径（摄入）不被计量 = 看不到真实缓存收益。

**专业基线要点（重建须建立）**
- 每一层都要"实现 + 验证生效"，占位层必须有明确的 TODO 与降级行为。
- 所有缓存路径统一计数（命中/未命中），不分摄入/查询。

## 2.4 数据摄入、一致性、生命周期、迁移

**当前真实状态**
- Outbox Saga 状态机专业（UPLOAD→PENDING→VECTORS_STORED→GRAPH_STORED），Neo4j 失败不阻断向量存储，reconciliation 对账，迁移支持回滚。
- **但状态汇报不诚实**：KB sync 在 Neo4j 失败时标记 `graph_status="ready"` + "stub mode" 消息，外部看像成功实则没做。
- 后台摄入任务 `asyncio.create_task` 未保存引用 → 可能被 GC 中断。

**暴露的教训**
- 状态机的价值在于"状态真实"，一旦报假成功，整个可靠性承诺崩塌。
- asyncio 任务不持有引用是 Python 官方警告的经典陷阱。

**专业基线要点（重建须建立）**
- 状态诚实原则：任何降级/失败都要反映到真实状态，禁止"成功伪装"。
- 幂等摄入 + 可重试 + 可对账 + 可取消。
- 后台任务必须持有强引用（任务集），完成时清理。

## 2.5 混合检索与融合

**当前真实状态**
- 向量 + BM25 + 图谱三路，RRF 融合（k=60，权重 0.7/0.3/1.0），自动降级。
- Recall@5=77.5%、MRR=0.76。图谱增益依赖查询类型（实体关系查询才显著）。
- BM25 索引 TTL 缓存（300s），jieba 中文分词。

**暴露的教训**
- 业务逻辑扎实。降级语义（"显式跳过" vs "故障降级"）区分清晰，是好设计。
- 完整性 33.2% 偏低，根因在检索召回 + 无规划，属 Agent 层问题（见 L3）。

**专业基线要点（重建须建立）**
- 多路检索 + 排名融合（RRF），权重可配置。
- 降级语义显式（跳过 ≠ 故障），故障可观测。
- 中文分词（jieba）+ BM25 索引 TTL 刷新。

## 2.6 重排（Reranking）

**当前真实状态**
- 设计了三级降级链（Cohere API → BGE 本地 → Raw），代码 + mock 测试完备。
- **但实际只跑 Raw**：Cohere 无 key 跳过、BGE 运行环境未安装跳过。
- BGE 若启用，首调用下载数百 MB 模型，冷容器可能超时降级。

**暴露的教训**
- "设计了降级链"不等于"降级链在 prod 真实运行"。每一 tier 必须验证在目标环境真实生效。

**专业基线要点（重建须建立）**
- 降级链每一 tier 都要在目标环境验证可用，而非只靠 mock。
- 本地模型预打包/预下载，不依赖运行时拉取。
- degraded 状态真实上报（可观测）。

## 2.7 生成与引用

**当前真实状态**
- 强制引用标注 `[来源 N]`，Reviewer 4 项检查含引用校验，幻觉率 0%、引用准确率 100%。
- 引用编号机制：检索结果按序编号，Worker system prompt 要求引用。

**暴露的教训**
- 这是本项目最成功的部分——RAG 约束机制有效，对抗/不可答查询零幻觉。

**专业基线要点（重建须建立）**
- 强制引用 + 可溯源（每个引用能定位到源文档片段）。
- 对抗性输入与不可答输入的明确处理策略（拒答优于编造）。

---

# Layer 3 — Agent 编排（Agent Orchestration）

> 详见 `agent_paradigm_analysis.md`。当前是"固定工作流 + 轻量多 Agent"，非真正智能体。

## 3.1 Agent 范式与框架

**当前真实状态**
- LangGraph 图编排：Router→LoadSkill→Retrieve→Worker→Reviewer，条件边 + 修订循环（max 2 轮）+ recursion_limit=10 兜底。
- Router 用关键词匹配（确定性、零成本），Reviewer 用启发式规则（非 LLM）。

**暴露的教训**
- **不是真智能体**：Worker 开环不调用工具、Reviewer 反思不沉淀（无自进化）、复杂任务无全局规划、无长期记忆。
- 选 LangGraph 是对的（条件路由/循环检测/流式），但只用了它的"工作流"能力，没用"智能体"能力。

**专业基线要点（重建须建立）**
- 先定范式再选框架：知识库 QA 用固定工作流（可控）合理；若要"会调用工具、会学习"，须上 ReAct + Reflexion + 记忆。
- 工具调用闭环（思考-行动-观测）、反思沉淀（跨会话学习）、任务规划（复杂多步分解）——按需引入，不要假装有。
- 已有 Neo4j 可低成本扩展为图记忆，是"弱自学习"的现实路径。

## 3.2 技能系统

**当前真实状态**
- 11 个技能，YAML frontmatter + Markdown 指令 + eval/golden.json，registry 自动发现，CI 评估。
- **技能评估是关键词匹配**，非语义评估（已知中严重度问题）。

**暴露的教训**
- 标准化技能格式（ADR-006）做得好，但评估手段弱 = 无法度量技能真实质量。

**专业基线要点（重建须建立）**
- 标准化技能定义（frontmatter + 指令 + eval 集）。
- 评估从关键词匹配升级到语义/LLM 评判，CI 阈值卡点。

## 3.3 工具调用（MCP）

**当前真实状态**
- 沙箱隔离专业（Docker network=none, read_only, mem_limit, 非 root, 不挂 docker.sock）。
- **但工具是桩**：`db_query` 抛 NotImplementedError、`web_search` 即使有 key 也返回 `[]`。
- 而且 Worker 根本不在运行时调用这些工具（见 3.1）。

**暴露的教训**
- 定义了工具却不实现、实现了却不调用 = 工具层是摆设。
- 沙箱安全做得好，但安全壳里没有真正执行的代码。

**专业基线要点（重建须建立）**
- 工具要么真正实现并接入 Agent 调用循环，要么明确从能力清单移除，不留半成品。
- 沙箱隔离原则（独立容器、无网络、只读、资源限制、无 docker.sock）保留。

---

# Layer 4 — 接口与全栈（API & Full-stack）

## 4.1 API 契约（Routes / Schemas / SSE）

**当前真实状态**
- Pydantic schemas 单一来源，SSE 流式（thinking→retrieval→answer→done）。
- **不一致**：分页有的用 `Query(ge=,le=)` 校验、有的裸 `int`（可传 limit=1000000）；Redis 宕机时不同路由返回 200/空 或 503，行为不一；上传元数据重复写两次（竞态）；`ensure_collection` 每次上传都调（应启动期一次）。
- SSE 超时后先发 error 再发 done（空 sources），破坏协议终态语义。

**暴露的教训**
- API 一致性靠纪律维持，一旦多处各写各的，行为就发散。
- "同样的故障不同的状态码"会让调用方和监控都无法判断真相。

**专业基线要点（重建须建立）**
- 统一响应契约：统一的错误结构、统一的分页校验、统一的"后端不可用"状态码策略。
- 状态单一所有权：每个状态（如摄入状态）只有一个写入者，杜绝重复写竞态。
- SSE 协议严谨：终态语义明确，error 与 done 不混淆。

## 4.2 认证与授权（Auth & Authz）

**当前真实状态**
- JWT + API Key 双认证。
- **漏洞**：API Key 硬编码 `tenant_id="default"`、`role="service"`（绕过租户）；authz 未逐路由强制（admin 有 role 检查，其他路由未必）。

**暴露的教训**
- 认证（你是谁）和授权（你能干什么）是两件事，本项目认证做了、授权漏了。
- API Key 的身份与租户映射必须显式，不能给个默认值糊弄。

**专业基线要点（重建须建立）**
- 认证：JWT claims 携带身份/租户/角色，API Key 显式映射到身份（无默认租户）。
- 授权：逐路由 guard（基于角色/租户），中间件统一注入，路由声明所需权限。
- 认证态是租户身份的唯一来源（呼应 1.3）。

## 4.3 异常体系与错误处理（用户重点关注维度）

**当前真实状态**
- 有 12+ 自定义异常类（分层：RAGAgentError → 子类），`RAGError` 子树（Storage/Retrieval/Ingestion）。
- **但错误处理是最不一致的域**：
  - 6 处 `except Exception: pass` 无日志（BYOK 失败完全静默）。
  - 全局 `@app.exception_handler(Exception)` 可能吞掉本该 FastAPI 处理的 HTTPException/ValidationError。
  - Redis 宕机：list 返 200 空、delete 返 503、admin 返 200 零指标——同一故障三套行为。
  - 费用聚合 `record_chat_metrics` 非原子（注释声称原子实则不原子）→ 计费竞态丢更新。
  - SSE 超时分支是死代码（stream_agent 内无超时，外层 catch 永不触发）。

**暴露的教训**
- 异常体系是"一致性灾难区"：有类层级，但"异常→HTTP 状态码"的映射没有统一表，导致每个路由各写各的。
- 静默吞异常（except pass 无日志）= 把故障藏进黑洞，运维无从知晓。
- 状态变更的非原子操作 = 数据静默损坏（计费/计数）。

**专业基线要点（重建须建立）**
- 异常→HTTP 状态码映射表：每种业务异常对应明确状态码（如 StorageError→503、Validation→422、Auth→401/403、Quota→429），全项目唯一表。
- 禁止静默吞异常：每个 except 至少 `logger.warning` 并带上下文；可降级但不可无声。
- 全局兜底 handler 必须先放行 HTTPException/RequestValidationError，再兜其余。
- 状态变更原子化：Redis 用 Lua/MULTI，DB 用事务，禁止"读-改-写"非原子序列。
- 异常分层与业务域对齐（core / rag / agents / api 各有子树），可分级降级。

## 4.4 安全防御

**当前真实状态**
- 5 层 Prompt 注入防御（输入分类/XML 隔离/工具白名单/PII 检测/综合管道）。
- 沙箱隔离专业，Neo4j 用 MERGE + 标签白名单 + 关系类型校验，Milvus 过滤值正则白名单。
- **但**：`db_query` SQL 防注入只查关键词不强制参数化（摆设）；admin 用 `KEYS *`（O(N) 阻塞）；弱 secret 不阻断。

**暴露的教训**
- 防御要"纵深 + 真实有效"，装饰性检查（关键词查 SQL）给虚假安全感。
- `KEYS *` 是 Redis 生产禁忌，说明"知道该用 scan"和"处处用 scan"之间有执行落差。

**专业基线要点（重建须建立）**
- 注入防御：参数化查询（不用字符串拼接 SQL/Cypher）、白名单校验、输入隔离。
- Redis 遍历一律 `SCAN`（非 `KEYS`）。
- secret 强制（见 0.3）、PII 检测、工具白名单、沙箱隔离——纵深多层，每层真实有效。

---

# Layer 5 — 质量与运维（Quality & Operations）

## 5.1 测试策略

**当前真实状态**
- 1311 单元测试通过（真实），68 个测试文件覆盖各域。
- **但"集成测试"是假的**：无项目级 conftest.py、`@pytest.mark.integration` 从未注册/跳过、integration 目录里全是 mock（内存 dict mock Milvus、字符串匹配 mock Neo4j、canned string mock LLM）。
- 唯一真实集成测试（`test_rag_real.py`）在每个失败点 `pytest.skip`，且**不在 CI**（CI 只跑 unit）。
- 熔断只测 fakeredis；租户隔离只断言 filter 字符串，未测真实泄漏。

**暴露的教训**
- "测试数量"是虚荣指标，"测试真实性"才是价值指标。1311 个里若全是 mock 的"集成测试"，对真实故障零防护。
- CI 只跑 unit + 集成测试自跳过 = **没有一道 CI 关卡真正验证系统行为**。

**专业基线要点（重建须建立）**
- 测试金字塔：单元（多，快，mock）→ 集成（少，真服务，CI 带服务起停）→ E2E（关键路径，真实数据）。
- 集成测试必须打真实后端（CI 用 service container 起 Milvus/Neo4j/Redis），禁用 mock 冒充集成。
- 关键不变量有专项测试：租户隔离（真实双租户泄漏测试）、降级（中途杀服务）、熔断（真实 Redis）、SSE（token 顺序）。

## 5.2 可观测性（最大表象，用户重点关注）

**当前真实状态**
- 监控栈配置漂亮（Prometheus + Grafana + Jaeger + 3 仪表盘 + 14 告警）。
- **但导出层完全断开**：
  - **`/metrics` 端点不存在** → Prometheus 采集 404 → 仪表盘全空。
  - 指标代码正确累加，但写进没人读的内存注册表，重启即丢。
  - Admin 缓存命中率**永远为 0**（`sys:cache_hits` 写入者不存在）。
  - 平均延迟**硬编码 `0.0`**（`chat.py:176,355`）。
  - embedding 摄入缓存命中不计指标（断头）。
  - OpenTelemetry 从未 instrument/export → Jaeger 永远空。

**暴露的教训**
- 这是全项目最危险的"信任陷阱"：仪表盘漂亮、数字常驻，但数字是 0 或错的，让人误以为系统健康。
- "采集了指标"≠"指标被看见"。导出端点、注册表、采集、展示是四个环节，断一个全链失效。

**专业基线要点（重建须建立）**
- 指标导出闭环：`/metrics` 端点真实暴露 → Prometheus 真实采集 → Grafana 查询真实有值。每一环上线后用真实流量验证。
- 指标与代码路径对齐：每个被仪表盘查询的指标，必须能追溯到真实的写入点（grep 得到 inc/observe）。
- 分布式追踪：FastAPI 自动 instrument + OTLP exporter 真实导出 → Jaeger 真实有 span（含检索/生成/DB 子 span）。
- 结构化日志：trace_id/tenant_id 贯穿，可按请求串联日志/指标/追踪。
- 仪表盘"防骗"：上线后人为制造一次缓存命中/一次延迟，确认数字真的变化。

## 5.3 性能与并发

**当前真实状态**
- 分布式限流专业（Redis Lua 信号量，跨进程），4 层嵌入 Pipeline。
- 50 并发 100% 成功、QPS=4.21。
- **但**：async 路径多处同步阻塞（chunk_document/open/shutil）、`KEYS *` 阻塞、三路检索串行（占端到端 85%）。

**暴露的教训**
- 限流做得好，但"async 纯度"不达标——同步阻塞会拖垮事件循环，抵消并发优势。
- 检索串行是延迟主因，有明确优化空间（并行化）。

**专业基线要点（重建须建立）**
- async 纯度：所有 I/O 异步或 to_thread 包装，CI lint 卡死同步阻塞调用。
- 并发原语：跨进程用 Redis（信号量/Pub-Sub），进程内用 asyncio 原语，不混用。
- 性能可度量：各阶段延迟（检索/生成/嵌入）独立打点，瓶颈可见可优化。

## 5.4 成本控制

**当前真实状态**
- 3 级费用熔断逻辑正确（单请求 token / 租户小时 / 全局日限），DeepSeek 较 GPT-4o 省 97.1%。
- **但**：`record_chat_metrics` 费用聚合非原子 → 计费丢更新；多层缓存节省因指标断层无法度量（5.2）。

**暴露的教训**
- 熔断"挡"的逻辑对了，但计费"记"的逻辑有竞态——挡得住超额，记不准实际。
- 成本节省无法度量（指标断）= 优化无据。

**专业基线要点（重建须建立）**
- 计费原子化（Lua/MULTI），无丢更新。
- 两层 token 计数（快速估算预检 + 精确计数后对账）。
- 成本节省可度量（缓存命中率、模型选择比例真实指标）。

## 5.5 发布与部署就绪

**当前真实状态**
- `deploy.sh` 存在但**不阻断**：单元测试失败只 warn 继续、冒烟测试失败 return 0。
- CI `deploy-staging` 是 echo 空壳；无 deploy-prod。
- 弱 JWT secret 只在 deploy.sh 阻断（且该脚本不被 CI 调用），其他路径（直接 compose up）不阻断。
- Dockerfile 多阶段 + 非 root + healthcheck，但 `.dockerignore` 漏排 db/data/logs，镜像臃肿。

**暴露的教训**
- 发布门禁写在脚本里但"不阻断"= 等于没有门禁。
- 部署就绪度是"任何部署路径都过同一套门禁"，不是"有一个脚本会检查"。

**专业基线要点（重建须建立）**
- 发布门禁硬阻断：测试失败、安全扫描失败、弱 secret、健康检查不过 → 一律中止，不可 warn-skip。
- CD 真实化：CI 真实构建/部署（非 echo），staging→prod 分级。
- 镜像精简：`.dockerignore` 严格，多阶段构建，非 root，healthcheck 完整。

---

# 跨层原则（Cross-Cutting Lessons）

这些不是某一层的事，而是**贯穿重建始终的认知准则**——本项目正是在这些准则上失分的：

1. **导出层必须闭环，不能只做采集端**
   指标/追踪/日志，从"产生→导出→采集→展示"每一环都要真实连通。本项目指标采集了却没导出端点，是典型的"做了一半"。

2. **真实性 > 数量**
   1311 个测试 < 10 个真实集成测试。技能 eval 关键词匹配 < 语义评判。宁可少而真，不要多而假。

3. **隔离与安全是端到端的，不是某一环的**
   filter 字符串生成对了 ≠ 数据隔离了。租户身份必须从认证态单一派生，任何接受客户端 tenant_id 的口子都是后门。

4. **降级要诚实，状态要真实**
   静默降级 + 报假成功 = 让运维失去感知。任何降级/失败必须反映到真实状态和真实指标。

5. **规范必须自动化 enforcement**
   写在 CLAUDE.md 的规则若不变成 lint/CI 硬卡点，必然被持续违反。规范即代码。

6. **门禁必须阻断，不能 warn-skip**
   测试失败、弱 secret、健康检查不过——任何"继续部署"的选择都是把风险推到生产。

7. **"设计了"≠"实现了"≠"在 prod 运行了"**
   Singleflight 占位、降级链只跑 Raw、工具是桩、MCP 不被调用——每一层都要追问"这真的在跑吗"。

8. **底层先稳，上层勿动**
   重建顺序即本文档顺序：L0 地基（git/依赖/配置/规范）→ L1 基础设施 → L2 RAG → L3 Agent → L4 接口 → L5 质量。跳层必返工。

---

# 附：核查方法说明

本报告所有"当前真实状态"均经实地核查：
- **Git/CI**：`git log`、`git branch -a`、`git status`、`gh pr list --state all`、`gh api .../branches/main/protection`、读取 `.github/workflows/*.yml`
- **基础设施**：读取真实 `.env`、`src/infra/*.py`、`docker-compose*.yml`、`docker exec` 实测 reranker backend
- **代码质量**：grep 验证 eval/exec/md5/os.getenv/KEYS、逐文件读取 routes/core/rag/agents
- **测试**：`find tests -name conftest.py`、读取 `tests/integration/*.py`、核对 `pytest.ini` markers
- **可观测性**：全仓库 grep `/metrics`/`make_asgi_app`/`FastAPIInstrumentor`/OTLP exporter/`sys:cache_hits` 写入者

> 本文档是重建的**起点基线**，不是终点方案。重建时，每个维度对照"专业基线要点"逐条落地，由你亲自实现，每步可追溯、可解释、可在面试讲清"为什么这么设计"。
