# PROGRESS.md — 进度账本

> 每个新会话**先读本文件**确定"上次到哪、下一步是什么"。
> 每完成一个单元：勾选状态 + 填 commit hash + 记验证证据。

---

## 怎么用

- 单元状态：`⬜ pending` / `🔨 进行中` / `✅ done`
- 每个 `✅` 必须满足：测试通过 + 真实验证（非 mock）+ 已 commit + 已 merge 到 main（经 PR）。
- 进入下一 Phase 前，该 Phase 所有单元必须 `✅`，且跑通该 Phase 门禁脚本。

---

## 当前焦点

**Phase 0 — 工程地基**　下一个单元：`P0-03 content_hash`（P0-02 配置管理已完成 ✅）

---

## Phase 0 — 工程地基（foundation）

| ID | 单元 | 状态 | Commit |
|----|------|------|--------|
| P0-01 | 项目骨架 + git + .gitignore | ✅ | #1 (09ebaa3) |
| P0-1.5 | **基础设施契约蓝图（ADR-0001 + 蓝图文档）** | ✅ | #2,(3bdcaec)|
| P0-02 | 配置管理（pydantic-settings + fail-fast） | ✅ | #3 (待 merge) |
| P0-03 | content_hash（SHA-256 工具） | ⬜ | — |
| P0-04 | 异常体系 + **异常→HTTP 映射表** | ⬜ | — |
| P0-05 | 结构化日志（trace_id/tenant_id ContextVar） | ⬜ | — |
| P0-06 | **BaseStore 抽象基类** + Redis 连接单例（三件套） | ⬜ | — |
| P0-07 | 启动健康门禁（lifespan fail-fast） | ⬜ | — |
| P0-08 | Phase 0 门禁脚本 + 验收 | ⬜ | — |
| P0-09 | Docker 编排骨架（compose + service_healthy 依赖图） | ⬜ | — |

### P0-01 项目骨架 + git + .gitignore
- **目标**：建立目录结构、git 仓库、依赖锁定文件骨架。
- **DoD**：
  - [x] `git init`，main 分支
  - [x] `.gitignore` 排除 venv/data/logs/.env/__pycache__/*.pyc
  - [x] 目录骨架：`src/{core,infra,rag,agents,api,observability}/`、`tests/unit/`、`docs/{adr,_reference}/`
  - [x] `requirements.txt`（先空或仅基础依赖，精确锁定）
  - [x] 每个 package 有 `__init__.py`
  - [x] `python -c "import src.core"` 不报错
- **验证命令**：`python -c "import src.core, src.rag, src.agents, src.api"`
- **完成**：PR #1 已 merge（09ebaa3，--no-ff via "Create a merge commit"）。

### P0-1.5 基础设施契约蓝图
- **目标**：在写功能代码前，统一定义底层接口契约（L0/L1/L4/L5），作为后续所有单元的「接口宪法」。对应诊断书「底层先稳，上层勿动」铁律。
- **产出**：`docs/adr/0001-infrastructure-contracts.md`（十条决策）+ `docs/design/infra_blueprint.md`（契约详述）。
- **DoD**：
  - [ ] ADR-0001 记录十条核心决策（Context/Decision/Consequences）
  - [ ] 蓝图覆盖 L0 配置 / L1 连接抽象+多租户+Docker+schema / L4 异常映射 / L5 可观测性
  - [ ] 蓝图契约自洽（`BaseStore` 被 `TenantFilteredStore` 继承；ContextVar 被日志和多租户复用）
  - [ ] 对照诊断书「认知红线 8 条」逐条堵死
- **验证**：后续 P0-02 / P0-04 / P0-06 能照蓝图契约直接实现、无歧义；ADR-0001 登记进 ADR 索引。

### P0-02 配置管理
- **目标**：单一配置源，启动校验关键 key（fail-fast）。
- **DoD**：
  - [ ] `src/core/config.py` 用 pydantic-settings，所有配置项集中
  - [ ] 业务代码禁止 `os.getenv`（lint 卡）
  - [ ] 关键 key（LLM/Embedding/Redis）缺失或弱默认值时，prod 拒启动（dev 放行）
  - [ ] 先写测试：缺 key 抛特定异常；非法类型被拒
- **验证**：`pytest tests/unit/core/test_config.py -v` + 故意删 key 看是否 fail-fast

### P0-03 content_hash
- **目标**：跨进程一致的 SHA-256 哈希工具，替代 Python `hash()`。
- **DoD**：
  - [ ] `src/core/hash.py` 暴露 `content_hash(text) -> str`
  - [ ] **先写测试**：基本正确性 + 已知 SHA-256 哈希值 + 跨进程一致性（subprocess 验证）
  - [ ] 业务代码禁止直接 import hashlib（lint 卡，仅 hash.py 可用）
- **验证**：`pytest tests/unit/core/test_hash.py -v`

### P0-04 异常体系 + HTTP 映射表
- **目标**：自定义异常层次 + **全项目唯一的「异常→HTTP 状态码」映射表**。
- **DoD**：
  - [ ] `src/core/exceptions.py`：基类 `RagError` + 业务子类（StorageError/RetrievalError/ValidationError/AuthError/QuotaExceeded/NotFoundError）
  - [ ] **异常→HTTP 映射表**（见蓝图 L4）：StorageError→503、Validation→422、Auth→401/403、Quota→429、NotFound→404
  - [ ] **先写测试**：继承关系、属性、映射表覆盖所有子类
- **验证**：`pytest tests/unit/core/test_exceptions.py -v`

### P0-05 结构化日志
- **目标**：JSON 日志，带 trace_id/tenant_id（ContextVar）。
- **DoD**：
  - [ ] `src/observability/logger.py`：StructuredFormatter + get_logger
  - [ ] `trace_id_var` / `tenant_id_var`（ContextVar，**与多租户复用同一套**）
  - [ ] **先写测试**：日志含 trace_id/tenant_id 字段
- **验证**：`pytest tests/unit/observability/test_logger.py -v`

### P0-06 BaseStore 抽象基类 + Redis 连接单例
- **目标**：先建存储连接统一抽象，Redis 作为首个实现（蓝图 L1）。
- **DoD**：
  - [ ] `src/core/base_store.py`：抽象基类 `BaseStore`（`health_check()` + 幂等 `close()`）
  - [ ] `src/infra/redis.py`：`RedisStore(BaseStore)`，连接池单例
  - [ ] **用 `asyncio.Lock` 防 TOCTOU**（上次 Redis 漏锁，本次必须做对）
  - [ ] health_check() + idempotent close()
  - [ ] **先写测试**（用 fakeredis）：set/get、健康检查、单例、锁正确性
- **验证**：`pytest tests/unit/infra/test_redis.py -v`

### P0-07 启动健康门禁
- **目标**：应用启动时对关键后端做真实探活，不可达则拒启动。
- **DoD**：
  - [ ] `src/api/lifespan.py`（或 startup）：启动期调 `redis_conn.health_check()`
  - [ ] 关键后端不可达 → **拒启动**（非 warning 继续，杜绝带病上岗）
  - [ ] dev 模式可降级为 warning，prod 必须 fail-fast
- **验证**：故意停 Redis，启动应失败；启动 Redis，启动成功

### P0-08 Phase 0 门禁
- **目标**：写 Phase 0 验收脚本，全过才进 Phase 1。
- **DoD**：
  - [ ] `scripts/validate_p0.sh`：跑 config import + hash 跨进程检查 + 所有 core/infra 单元测试
  - [ ] 脚本退出码非 0 时**禁止**进 Phase 1
- **验证**：`bash scripts/validate_p0.sh` 返回 0

### P0-09 Docker 编排骨架
- **目标**：按蓝图 L1 建本地基础设施编排（先 Redis，后续加 Milvus/Neo4j）。
- **DoD**：
  - [ ] `docker-compose.yml`：redis（带 healthcheck），app 依赖 redis 用 `condition: service_healthy`
  - [ ] `.dockerignore` 严格（排除 db/data/logs/venv）
  - [ ] **禁 `service_started` 兜底**（上次 neo4j 这一处坑）
- **验证**：`docker compose up -d` 后 redis 健康、app 能连上

---

## Phase 1 — 走通骨架（walking skeleton，到时细化）

> 目标：最薄端到端，**全真实基础设施，零 mock**：query → 真实 embedding → 真实 Milvus → 向量检索 → 真 LLM → 答案。

| ID | 单元（草案） | 状态 |
|----|------------|------|
| P1-01 | Milvus 连接单例 `MilvusStore(BaseStore)`（复用 P0-06 三件套） | ⬜ |
| P1-02 | LLM 封装（LiteLLM，async，主备 fallback） | ⬜ |
| P1-03 | Embedding（最小版 + Redis 缓存） | ⬜ |
| P1-04 | 向量存储（Milvus insert + search，含 partition key） | ⬜ |
| P1-05 | 最薄检索（仅向量，先不加 BM25/图谱） | ⬜ |
| P1-06 | 最薄生成（LLM + 检索上下文） | ⬜ |
| P1-07 | E2E 骨架测试（真实 Milvus+Redis+LLM，query→answer） | ⬜ |
| P1-08 | Phase 1 门禁 | ⬜ |

---

## Phase 2+ — 深化（roadmap，到时按兴趣排优先级）

- **文档处理**：解析（Docling/MarkItDown）+ 切片策略谱系（先递归起步）
- **混合检索**：BM25 + 向量，RRF 融合
- **Agent 编排**：Router → Worker → Reviewer（LangGraph）
- **重排**：降级链（Cohere/BGE/Raw）
- **记忆系统**：短期对话 + 长期记忆（Mem0 式提取/合并/检索）
- **图谱检索**：Neo4j 实体关系（`Neo4jStore(BaseStore)`，MERGE 幂等）
- **接口层**：FastAPI + SSE 流式
- **可观测性闭环**：/metrics 端点 + 采集 + 仪表盘
- **测试金字塔 + CI 门禁**：真实集成测试入 CI
- **多租户隔离**：`TenantFilteredStore` + 双租户泄漏测试（覆盖三库）

---

## 决策记录（ADR 索引）

> 每个重要架构决策写一个 ADR，在此登记。

| ADR | 标题 | 状态 |
|-----|------|------|
| ADR-0001 | 基础设施接口契约蓝图 | Accepted |

---

## 复盘区（每个 Phase 结束填）

### Phase 0 复盘
- 完成日期：—
- 走过的坑：—
- 下次改进：—
