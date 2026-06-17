# 基础设施接口契约蓝图

> 本文档是项目所有底层基础设施的**「接口宪法」**。后续每个实现单元(P0-02 起)必须照此契约实现。
> 决策动因见 [ADR-0001](../adr/0001-infrastructure-contracts.md);上一版教训见 [project_gap_analysis.md](../_reference/project_gap_analysis.md)。

## 分层总览

| 层 | 职责 | 契约要点 | 落地单元 |
|---|---|---|---|
| L0 | 地基/配置 | 单一配置源、fail-fast、规范自动化 | P0-02 config、P0-03 hash |
| L1 | 基础设施 | 连接抽象、多租户、Docker 编排、schema | P0-06 BaseStore+Redis、P0-09 Docker |
| L4 | 接口契约 | 异常体系、HTTP 映射、响应契约 | P0-04 异常+映射表 |
| L5 | 可观测性 | 日志/指标/追踪四环闭环 | P0-05 日志、Phase2+ 指标 |

---

## L0 配置

**契约**
- `src/core/config.py` 用 pydantic-settings,**全项目唯一配置源**;导出单例 `settings`。
- 业务代码**禁止 `os.getenv`**(由 ruff/pre-commit 硬卡);所有配置项从 `settings` 读。
- **启动 fail-fast**:关键 key(`LLM_API_KEY` / `EMBEDDING_API_KEY` / `REDIS_URL` / `MILVUS_*` / `JWT_SECRET`)缺失或为缺省值 → prod **拒启动**、dev 放行(并 warn)。
- **secret**:dev 占位、prod 强随机 + 外部注入(env/secret manager);弱值禁止进 prod。
- 启动时打印「已加载哪些后端、哪些 key 就绪」(脱敏)。

**反模式(禁止)**
- 业务代码 `os.getenv(...)`(诊断书:`web_search.py:58`、`auth.py:163` 每请求读一次)。
- 关键 key 默认空串静默启动(诊断书:`zhipu_api_key=""` → 首请求才 401)。

---

## L1 存储连接抽象

**契约:抽象基类 `BaseStore`**

```python
class BaseStore(ABC):
    """所有存储连接的统一抽象。子类:RedisStore / MilvusStore / Neo4jStore。"""
    @abstractmethod
    async def health_check(self) -> bool: ...   # 真实探活,启动门禁调用
    @abstractmethod
    async def close(self) -> None: ...          # 幂等,可重复调用
```

**连接单例三件套(每个子类必须实现)**
1. **`asyncio.Lock` 防 TOCTOU**:懒加载单例,「检查-创建」两步必须加锁。⭐ 上一版 Redis 漏锁(`redis.py:39-58`),本次三库统一、Redis 必须补。
2. **启动健康探测**:lifespan 启动期调 `health_check()`,关键后端不可达即 fail-fast 拒启动(prod)、dev 可降级 warn。⭐ 上一版写了从不调。
3. **运行时自愈**:连接失败重置内部连接、下次重连。

**子类**
- `RedisStore(BaseStore)`:连接池;用途见 schema 规范(Redis)。
- `MilvusStore(BaseStore)`:单例;partition key 见多租户。
- `Neo4jStore(BaseStore)`:`__init__` 预检连通性(上一版静默降级,本次必须探活)。

---

## L1 多租户隔离

**契约**
- `TenantFilteredStore(BaseStore)`:所有存储访问按当前租户上下文过滤,**不得绕过**(CLAUDE.md 编码规则 9)。
- **租户上下文用 `ContextVar` 协程级传播**(async 安全,绑定当前 task),不层层传参;与日志的 `tenant_id_var` **复用同一套 ContextVar**。
- **租户身份唯一来源**:服务端认证态(JWT claims / API Key 显式映射,**无默认租户**)。**禁止接受客户端传入 `tenant_id`**(上一版 IDOR 根因 `chat.py:232`)。
- **fail-closed**:无租户上下文即 `raise RuntimeError`,不留默认值兜底。
- **Milvus:单 collection + partition key**(不用每租户一 collection);`tenant_id` 字段同时是 partition key。
- **隔离测试金标准**:双租户真实数据 + 交叉查询 + 断言「互不可见」,覆盖 Milvus/Neo4j/Redis 三库。⭐ 上一版只断言 filter 字符串生成正确,从未用真实双租户数据验证。

---

## L1 Docker 编排

**契约**
- **服务清单**(按 Phase 增量,先 Redis):redis → milvus(+etcd+minio) → neo4j →(可观测栈 prometheus/grafana/jaeger 后续)。
- **依赖图**:被依赖方一律 `condition: service_healthy`,**禁 `service_started`**。⭐ 上一版 neo4j 这一处错 → 图检索首请求退化。
- **healthcheck 全覆盖**:每个服务配 healthcheck,`start_period` 给足冷启动(Milvus/Neo4j 冷启动慢)。
- **环境分层**:dev/prod overlay;`.dockerignore` 严格(排除 db/data/logs/venv,上一版漏排致镜像臃肿)。
- **验收**:`docker compose up` 后有「全服务 healthy」验收脚本。

---

## L1/L2 schema 规范

**Milvus collection(6 字段)**

| 字段 | 类型 | 说明 |
|---|---|---|
| id | VARCHAR(PK) | = SHA-256 content_hash |
| tenant_id | (partition key) | 多租户路由 |
| content | VARCHAR | 文本 |
| metadata | JSON | 元数据 |
| embedding | FLOAT_VECTOR | 向量 |
| embedding_version | INT | 支持平滑迁移 |

- 索引参数(`nlist`/`nprobe`)**进 config**,不硬编码(上一版硬编码 `nlist=128/nprobe=32`)。
- upsert 幂等(内容哈希覆盖)。

**Neo4j**
- 写入用 `MERGE`(幂等),**禁 `CREATE`**(CLAUDE.md 反模式);标签白名单 + 关系类型校验防注入。

**Redis(四职)**
- 缓存(embedding 24h)、锁、队列(摄入任务)、限流(Lua 信号量,**跨进程**禁 asyncio.Semaphore)、计费(Lua/MULTI 原子,**禁读-改-写非原子**)。
- 遍历一律 `SCAN`,**禁 `KEYS *`**(上一版 O(N) 阻塞)。
- 缓存/去重 key 用 SHA-256(`content_hash`),禁 Python `hash()`。

---

## L4 异常体系 + HTTP 映射

**异常类层次**

```
RagError(基类)
├── StorageError        # 存储/连接故障
├── RetrievalError      # 检索失败
├── ValidationError     # 输入校验
├── AuthError           # 认证
│   └── QuotaExceeded   # 配额(子类)
└── NotFoundError       # 资源不存在
```

**异常→HTTP 状态码唯一映射表(全项目唯一)**

| 异常 | HTTP | 说明 |
|---|---|---|
| ValidationError | 422 | 输入不合法 |
| AuthError | 401/403 | 未认证/无权限 |
| QuotaExceeded | 429 | 超配额 |
| NotFoundError | 404 | 资源不存在 |
| StorageError | 503 | 后端不可用 |
| RetrievalError | 500 | 检索内部错 |

**统一响应契约**
- 统一错误结构 `{code, message, ...}`;统一「后端不可用」状态码策略(上一版 200 空 / 503 / 200 零指标三套)。
- **禁静默吞异常**:每个 `except` 至少 `logger.warning` 带上下文(上一版 6 处 `except: pass`)。

---

## L5 可观测性闭环(契约预留)

**四环闭环(断一环全链失效)**

```
产生(代码 inc/observe) → 导出(/metrics 端点) → 采集(Prometheus) → 展示(Grafana)
```

- **日志**:结构化 JSON,`trace_id` / `tenant_id` 用 `ContextVar` 贯穿(与多租户复用)。
- **指标**:`/metrics` 端点真实暴露;每个被仪表盘查询的指标必须能 grep 到写入点。⭐ 上一版端点不存在、仪表盘全空。
- **追踪**:OTLP 真实导出 → Jaeger 真有 span。
- **防骗验证**:上线后人为制造一次缓存命中/一次延迟,确认数字真的变化。
