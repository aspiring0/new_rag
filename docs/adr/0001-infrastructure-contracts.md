# ADR-0001:基础设施接口契约蓝图

| 字段 | 值 |
|---|---|
| Status | Accepted |
| Date | 2026-06-17 |
| Deciders | mikasa + Claude |
| Related | [infra_blueprint.md](../design/infra_blueprint.md)(契约详述)、[project_gap_analysis.md](../_reference/project_gap_analysis.md)(决策动因) |

## Context(背景与动因)

上一版 RAG 项目「业务逻辑扎实,但底层基础设施空心、统一契约缺位、所有保障机制都做了一半」(诊断书原话)。关键翻车点:

- **存储连接**:Neo4j/Milvus 用了 `asyncio.Lock`,**Redis 漏锁**(TOCTOU);`health_check()` 三个后端都写了、启动期从不调 → 带病上岗。
- **多租户**:partition key + `TenantFilteredStore` 设计专业,但接受**客户端传入 `tenant_id`** → IDOR 后门。
- **接口**:12 个异常类**无统一映射表**,Redis 宕机时三个路由返三种状态码(200 空 / 503 / 200 零指标)→ "一致性灾难区"。
- **Docker**:`api.depends_on.neo4j` 用 `service_started` 而非 `service_healthy` → 图检索首请求静默退化。
- **可观测性**:`/metrics` 端点不存在,仪表盘全空但数字常驻 → "信任陷阱"。

**根因:底层契约没在写功能代码前统一定死,各模块各写各的。**

## Decision(决策)

**在写任何 RAG/Agent 功能代码(P0-02 起)之前,先定一份「基础设施接口契约蓝图」,作为后续所有实现单元的接口宪法。** 蓝图只定契约(签名/字段/服务清单/映射表),不写实现;实现按 PROGRESS 单元逐个 PR、亲手实现。核心决策十条:

1. **先契约后实现**:蓝图先于功能单元完成,后续单元照契约实现,接口天然一致。
2. **存储连接统一抽象**:抽象基类 `BaseStore`,统一 `health_check()` + `close()`(幂等);连接单例三件套(`asyncio.Lock` 防 TOCTOU + 启动健康探测 + 运行时自愈);Redis/Milvus/Neo4j 各一子类。
3. **多租户端到端隔离**:`TenantFilteredStore(BaseStore)`;租户上下文 `ContextVar` 协程级传播;**租户身份唯一来源是服务端认证态,禁止客户端传入**;fail-closed(无上下文即 `RuntimeError`)。
4. **向量库单 collection + partition key**:不用每租户一 collection(运维成本高);partition key 路由 + 双租户泄漏测试兜底。
5. **异常→HTTP 唯一映射表**:`StorageError→503` 等,全项目唯一表,杜绝"同故障不同状态码"。
6. **配置单一源 fail-fast**:`config.py` 唯一源,禁业务 `os.getenv`;关键 key 缺失 prod 拒启动、dev 放行。
7. **Docker 全 `service_healthy` 依赖图**:被依赖方一律 `condition: service_healthy`,禁 `service_started`;healthcheck 全覆盖。
8. **Neo4j `MERGE` 幂等 + 标签白名单**:防重复节点、防注入(CLAUDE.md 反模式:禁 CREATE)。
9. **可观测性四环闭环**:产生→导出→采集→展示,断一环全链失效;`trace_id`/`tenant_id` 用 `ContextVar` 贯穿(与多租户复用同一套)。
10. **SHA-256 `content_hash` 作缓存/去重 key**:跨进程一致,禁 Python `hash()`(CLAUDE.md 编码规则 4)。

## Consequences(后果)

**正面**
- 接口天然一致,从根上杜绝"一致性灾难区"。
- 每层契约可追溯(本 ADR + 蓝图),面试可讲清"为什么这么设计"。
- 上一版红线(Redis 漏锁、IDOR、同故障多状态码、`service_started`、`/metrics` 缺失)在契约层即堵死。
- 后续单元实现时有明确依据,减少返工。

**成本/权衡**
- 前期投入一个 docs 单元写契约(本次完成)。
- 契约可能在实现中微调(如 `BaseStore` 签名细化),届时同步更新本 ADR 与蓝图,**保持单一真相源**。
- 部分契约(可观测性、图谱 schema)Phase 1+ 才落地,蓝图先预留接口。
