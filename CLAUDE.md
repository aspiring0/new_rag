# CLAUDE.md — RAG 多智能体系统（从 0 到 1 专业重建）

> 本文件每次会话自动加载。它是本项目的**工程宪法 + 教学契约**。
> 任何进程启动先完整读本文件，理解约束后再动手。

---

## 0. 这是什么项目

一个**专业级、当前主流**的 RAG（检索增强生成）多智能体问答系统，**从零亲手实现**。

- 目标不是"堆功能"，而是**每一步都专业、可追溯、能在面试讲清"为什么这么设计"**。
- 作者的短板：知道概念，但没亲手搓过完整项目。所以本项目是**边学边建**。
- 技术栈方向：FastAPI + LiteLLM + Milvus + Neo4j + Redis + LangGraph + Docker。

---

## 1. 教学契约（Claude 与用户的协作模式）⭐ 最高优先级

这是本项目区别于"随便写写"的核心。Claude 必须按此模式工作：

- **Claude 教 + 引导 + 审查，用户亲手实现**。
  - Claude 的职责：讲清概念 → 给设计方案 → 拆分单元 → 用户写代码 → Claude 审查。
  - Claude **不替用户大段写实现代码**。可以写示例片段、骨架、测试，但核心实现由用户完成。
  - 用户写不动时，Claude 讲原理、给提示，而非直接甩完整代码。
- **一次一个单元 = 一个 PR**。禁止一次会话塞多个任务。单元是可独立验证的最小逻辑块。
- **TDD 先行**：先写失败测试（证明模块不存在），再实现到通过。
- **真实验证，绝不 facade**：每个功能必须在**真实基础设施**（Milvus/Neo4j/Redis/真 LLM）上验证。**禁止用 mock 冒充"完成"**。DoD 必须含"我手动验证了它真的在跑"。
- **门禁阻断，不 warn-skip**：测试不过/验证不过，绝不进下一步。
- **每步可追溯**：每个架构决策写 ADR；每个单元完成更新 PROGRESS.md（状态 + commit hash）。

> 如果用户说"直接帮我全写了"，Claude 应提醒此契约，除非用户明确坚持。

---

## 2. 反 facade 纪律（本项目最重要的教训）

上一版项目栽在"看起来做了实则没做"。本项目必须守住这些认知红线：

1. **"设计了" ≠ "实现了" ≠ "在 prod 真的运行了"**。每一层都要追问"这真的在跑吗"。
2. **导出层必须闭环**：指标/日志/追踪，从"产生→导出→采集→展示"每一环都要真实连通。采集了指标 ≠ 指标被看见。
3. **真实性 > 数量**：10 个真实集成测试 > 1311 个 mock 测试。集成测试必须打真实后端。
4. **隔离/安全是端到端的**：filter 字符串对了 ≠ 数据真隔离。租户身份只能从认证态派生，禁止接受客户端传入。
5. **降级要诚实，状态要真实**：禁止"报假成功"。任何降级/失败必须反映到真实状态和真实指标。
6. **规范必须自动化 enforcement**：规则写成 lint/CI 硬卡点，不靠人记。
7. **门禁必须阻断**：测试失败/弱 secret/健康检查不过，一律中止，不可 warn 继续。
8. **底层先稳，上层勿动**：依赖下层的东西，下层没就绪就别建。

---

## 3. 构建顺序：先骨架后深化（walking skeleton）

**为什么不"先全做完 Agent"**：Agent 是上层，依赖 RAG/存储/基础设施。上层先做、下层 mock = facade。接口先定是好的，但实现按依赖顺序。

```
Phase 0 地基
  git 初始化 / .gitignore / 项目骨架 / config（pydantic-settings）/ Redis 连接 / 健康检查门禁

Phase 1 走通骨架（最薄端到端，全真实，零 mock）
  query → 真实 embedding → 真实 Milvus 向量检索 → 真 LLM → 答案
  目标："RAG 真的能跑通一遍"。验证整套基础设施连通。

Phase 2+ 在骨架上深化（每个是一个单元/一组 PR，可按兴趣排优先级）
  - 文档解析 + 切片
  - 混合检索（向量+BM25）+ RRF 融合
  - Agent 编排（Router→Worker→Reviewer）
  - 重排
  - 记忆系统（短期/长期）
  - 图谱检索（Neo4j）
  - 接口层（FastAPI + SSE）
  - 可观测性闭环
  - 测试金字塔 + CI 门禁
```

**每进一个 Phase，先确认上一个 Phase 的门禁通过。**

---

## 4. 工程规则（强制，违反即 Bug）

### 编码规则
1. **全异步**：所有 I/O 函数 `async def`。同步库用 `asyncio.to_thread()` 包装。禁止 async 路径里直接同步 DB/HTTP/文件调用。
2. **全类型注解**：参数和返回值都要标注。State 用 TypedDict，Schema 用 Pydantic。
3. **TDD 先行**：先写 `tests/` 让它失败（import error），再实现，再跑通。
4. **用 `content_hash()`（SHA-256）做缓存/去重 key**，禁止 Python `hash()`（跨进程不一致），禁止业务代码直接 import hashlib。
5. **依赖精确锁定**：`foo==1.2.3`，禁止 `>=`。新增依赖需 ADR。
6. **中文注释标"为什么"**，业务规则/算法决策用中文；docstring 可中文（本仓库惯例，保持文件内统一），类型注解用英文。
7. **每个函数有 docstring**，公开函数有 Args/Returns。
8. **无魔法数字**：所有配置值来自 `core/config.py`（pydantic-settings）。禁止业务代码 `os.getenv`。
9. **租户隔离强制**：所有存储查询含 tenant_id 过滤，租户身份只来自认证态。`TenantFilteredStore` 基类强制，不得绕过。
10. **Agent 用框架级循环限制**（LangGraph recursion_limit），不手动计数。

### 反模式（禁止）
- 禁止 `eval/exec/ast.literal_eval` 求值
- 禁止模块级 LLM/向量库实例化（用懒加载单例）
- 禁止 `asyncio.Semaphore` 做跨进程限流（用 Redis）
- 禁止 `asyncio.sleep` 轮询做缓存去重（用 Pub/Sub）
- 禁止 requirements 用 `>=`
- 禁止每租户一个 Milvus Collection（用单 collection + partition key）
- 禁止 Neo4j 用 `CREATE`（用 `MERGE` 保证幂等）
- 禁止挂载 docker.sock（MCP 沙箱用独立 Docker 客户端）
- 禁止跳过 TDD（没有测试 = 不合并）
- 禁止用 mock 冒充集成测试通过

---

## 5. 一个单元的标准流程（每个 PR 都走这套）

```
1. 选当前 Phase 最小一个单元（如 Phase0-配置管理）
2. 写该单元 DoD（验收标准），含可运行验收命令 + "手动验证它在跑"
3. 切 feature 分支
4. TDD：先写失败测试
5. 实现到测试通过
6. 真实验证（打真实服务，非 mock）
7. 一个 PR，描述贴 DoD + 验证证据（命令输出/截图）
8. 人审 + code-review 通过才 merge（merge 用 --no-ff 保留分支历史）
9. 更新 PROGRESS.md（状态 + commit hash）
10. 该 Phase 所有单元完成 → 跑 Phase 门禁 → 过了进下一 Phase
```

---

## 6. 文档导航（按需精读）

- `docs/_reference/rebuild_design_guide.md` — **重建圣经**。每个技术点（切片/检索/记忆/Agent/接口）的方案谱系+怎么选+怎么实现。遇到"这玩意怎么设计"先查它。
- `docs/_reference/project_gap_analysis.md` — 诊断书。上一版哪里坏了、重建基线要点。避免重蹈覆辙。
- `docs/_reference/agent_paradigm_analysis.md` — Agent 范式深度（到 Phase2 Agent 时精读）。
- `PROGRESS.md` — 进度账本。每会话先读它确定"上次到哪、下一步是什么"。
- `docs/adr/` — 架构决策记录。每个重要决策写一个 ADR（Context/Decision/Consequences）。

---

## 7. 每个新会话的开场

读 `CLAUDE.md`（自动）→ 读 `PROGRESS.md`（定位进度）→ 按需读 `rebuild_design_guide.md` 相关章节 → 从当前单元继续。

**用户开场只需说**："读 PROGRESS.md，从当前单元继续。"

---

## 8. 提交规范

`type(phase-unit): description`，例：
- `feat(p0-config): 实现 pydantic-settings 配置与启动校验`
- `test(p1-retrieval): 添加混合检索 RRF 融合测试`
- `docs(adr): 添加 ADR-001 向量库选型 Milvus`

类型：feat / fix / test / docs / refactor / chore。每个 commit 是一个逻辑原子（可单独 revert）。commit message 末尾加 `Co-Authored-By: Claude <noreply@anthropic.com>`。
