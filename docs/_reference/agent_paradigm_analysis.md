# Agent 范式调研与当前设计不足分析

> 本文从专业 Agent 架构视角，对比 2026 主流 Agent 范式与平台，分析本系统当前多 Agent 设计的不足，并给出改进方向。
> 调研日期：2026-06-17

---

## 一、2026 主流 Agent 范式全景

### 1.1 四大基础范式（Andrew Ng 划分）

| 范式 | 核心机制 | 适用场景 | 不足 |
|------|---------|---------|------|
| **ReAct**（推理+行动） | Thought→Action→Observation 循环 | 动态环境、≤3 步简单工具调用 | **短视**：无全局规划，长链任务易跑偏 |
| **Plan-and-Execute** | 先规划全局计划，再逐步执行 | 复杂多步任务、研究型任务 | 计划僵化，环境变化需重规划 |
| **Reflection（反思/Reflexion）** | 失败后口头自省，沉淀反思记忆 | 可重试任务（编程、数学、推理） | 多次尝试增加延迟和 token 成本 |
| **Multi-Agent Collaboration** | 多 Agent 分工协作 | 复杂工程化落地 | 协调成本高、矛盾仲裁复杂 |

**关键洞察**（业界共识）：
- ReAct **胜在速度**，Plan-and-Execute **胜在正确性**
- 纯规划器环境变化时会崩，纯 ReAct 会短视——主流趋势是**混合架构**（Plan-and-Execute + 重规划，或 ReAct 之上叠加 Reflexion）
- Reflexion 让 Agent 具备"跨会话从错误中学习"的能力，是迈向自进化的关键

### 1.2 主流编排框架定位（2026 收敛趋势）

| 框架 | 定位 | 优势 |
|------|------|------|
| **LangGraph** | 编排层（状态图） | 复杂可控的工业级工作流、循环、有状态 |
| **CrewAI** | 单 Agent 实现 | 角色扮演协作，简洁 |
| **AutoGen/AG2** | 对话式多 Agent | 研究对话场景 |
| **OpenAI Agents SDK** | 官方一体化 | 与 OpenAI 生态深度集成 |
| **Google ADK** | 官方一体化 | Gemini + Android 系统级 |
| **Claude Agent SDK** | 代码执行任务 | 编码类 Agent |

2026 编排范式收敛趋势：**编排层用 LangGraph，单 Agent 实现用 CrewAI，代码执行用 Claude Agent SDK**——分层协作而非单一框架包打天下。

### 1.3 Agent 记忆机制（本系统最大缺口）

业界已明确区分 **RAG ≠ Agent Memory**：

| 维度 | RAG（本系统现状） | 真正的 Agent Memory |
|------|------------------|-------------------|
| 机制 | 查询时从**静态文档索引**检索 | 需要**显式写入机制**更新内部状态 |
| 时效 | 文档不变则答案不变 | 跨会话**持久化并适应** |
| 学习 | 无 | 从交互中**积累偏好和经验** |
| 典型实现 | 向量库（Milvus） | 短期记忆（checkpoints）+ 长期记忆（Mem0/图记忆） |

前沿研究（A-Mem、ACM 记忆机制综述）正走向**动态自组织记忆**，支持 Agent 自进化。

---

## 二、本系统当前设计对照

### 2.1 当前范式定位

本系统的 Agent 编排是：
```
Router（关键词路由）→ LoadSkill → Retrieve → Worker（生成）→ Reviewer（启发式审核 + 最多2轮修订）
```

**范式归类**：本质是 **固定工作流（Workflow）+ 轻量 Multi-Agent**，而非真正的智能体范式。

| 主流范式要素 | 本系统是否具备 |
|-------------|--------------|
| ReAct 循环（思考-行动-观察） | ❌ 无。Worker 直接生成，无工具调用循环 |
| Plan-and-Execute（先规划后执行） | ❌ 无。Router 只做一次性意图分发 |
| Reflection/Reflexion（自省学习） | ⚠️ 弱。Reviewer 是质量门禁，但**不沉淀反思记忆**，下次相同错误还会犯 |
| Tool Use（动态工具调用） | ❌ 无。MCP 工具已定义但 Agent 不会动态选择调用 |
| 记忆机制（短/长期） | ❌ 无自进化记忆。仅有对话历史（会话级） |
| 自主决策 | ⚠️ 仅规则驱动，非 LLM 自主规划 |

### 2.2 设计不足分析（6 个核心差距）

#### 不足 1：缺乏 ReAct 式工具调用循环（最大短板）

**现状**：Worker 拿到检索结果后直接调 LLM 生成答案，**全程不调用任何外部工具**。系统定义了 web_search、db_query、code_runner 等 MCP 工具，但 Agent 运行时不会根据需要自主调用。

**主流做法**：ReAct Agent 在生成时可以输出"我需要搜索 X"→调用 web_search→观察结果→继续推理。本系统是**"开环"**的，而主流是**"闭环"**（感知-决策-行动-观测）。

**影响**：知识库没有的信息，Agent 无法主动联网查证；用户问"帮我算一下..."，Agent 无法调用 code_runner 实际执行。

#### 不足 2：无全局规划（Plan-and-Execute 缺失）

**现状**：Router 只做一次性意图分类，没有任务分解。复杂问题（如"对比 A、B、C 三家公司并给出投资建议"）会被当作单次生成处理。

**主流做法**：Planner 先输出步骤计划（①查A ②查B ③查C ④对比 ⑤总结），Executor 逐步执行，必要时重规划。

**影响**：复杂多跳任务的完整性仅 33.2%（量化报告数据），根因之一就是缺乏规划。

#### 不足 3：Reviewer 的"反思"不沉淀（Reflexion 缺失）

**现状**：Reviewer 判定不合格 → 打回 Worker 重做。但**拒绝原因没有持久化**，下一次遇到同类问题，Worker 还会犯同样的错。

**主流做法（Reflexion）**：把每次失败反思存入 episodic memory，后续任务检索相关反思作为 few-shot 提示，实现"跨会话学习"。

**影响**：系统无法自进化，相同错误的改进依赖人工修改 prompt/技能。

#### 不足 4：路由是确定性关键词匹配，非智能分发

**现状**：Router 用关键词子串匹配选技能。对于"帮我分析一下最近的行业趋势"这类没有明确触发词的模糊查询，会兜底到默认技能。

**主流做法**：用 LLM 做语义级意图理解 + 动态路由，或混合（LLM 兜底 + 规则加速）。

**权衡**：关键词匹配零成本零延迟，是合理的工程权衡，但在技能增多/查询模糊时准确率下降。当前 11 个技能还可控。

#### 不足 5：无真正的记忆系统

**现状**：只有会话级对话历史（Redis TTL 24h）。Agent 不记得"这个用户上次问过什么、偏好什么、之前的回答哪里被纠正过"。

**主流做法**：
- **短期记忆**：LangGraph Checkpointer（线程级状态）
- **长期记忆**：Mem0 / 图记忆（Neo4j 可扩展为记忆图）

**讽刺的是**：本系统已经有 Neo4j，完全有基础设施做图记忆，但目前只用于文档实体，未用于用户偏好/经验记忆。

#### 不足 6：Agent 间是固定流水线，非动态协作

**现状**：Router→Worker→Reviewer 是写死的线性图。Agent 之间不能动态委派、不能根据任务复杂度增减参与方。

**主流做法（如 CrewAI/MetaGPT）**：Agent 可以根据任务自主决定"我需要请教专家 Agent"，实现动态协作。

**权衡**：固定流水线**可控、可调试、可测试**（这是企业级 RAG 的正确选择），但灵活性低。本系统定位是知识库问答而非通用智能体，这个权衡是合理的。

---

## 三、改进路线建议（按优先级）

### P0 高价值、低成本（建议优先做）

1. **Worker 接入 ReAct 工具循环**
   - 让 Worker 在生成时可以调用 web_search / db_query
   - LangGraph 原生支持 tool node + 条件边，改造成本低
   - 价值：知识库外的信息能联网补全，回答完整性直接提升

2. **Reviewer 反思沉淀为长期记忆**
   - 把拒绝原因 + 修订后的好答案存入 Neo4j 或 Redis
   - 后续相似查询检索作为 few-shot 示例
   - 价值：实现"弱自进化"，这是简历上"自学习"的诚实版本

### P1 中等价值、中等成本

3. **复杂查询引入 Plan-and-Execute**
   - Router 识别出复杂任务后，走 Planner 分解 → Executor 逐步执行
   - 简单查询仍走当前快速流水线（混合架构）
   - 价值：多跳任务完整性从 33% 提升

4. **路由增加 LLM 兜底**
   - 关键词不匹配时，用轻量 LLM 做意图分类
   - 价值：模糊查询的技能匹配准确率

### P2 探索性、高成本

5. **完整记忆系统**（Mem0 或图记忆）
6. **动态多 Agent 协作**（MetaGPT 式）

---

## 四、面试诚实表述建议

面对"你的 Agent 设计有什么不足"这类追问，建议这样回答：

> "我的系统本质是**固定工作流 + 轻量多 Agent**，适合企业知识库问答这种可控场景。但和主流 ReAct/Plan-and-Execute 智能体相比有三个明确差距：
> 1. Worker 目前是开环的，不会自主调用工具循环；
> 2. Reviewer 的反思没有沉淀成记忆，无法自进化；
> 3. 复杂任务缺乏全局规划。
> 这些是我在后续迭代的重点方向——比如已经在 Neo4j 上有基础设施，可以低成本扩展图记忆实现弱自学习。"

**关键原则**：承认局限 = 展示工程判断力；夸大能力 = 面试官一追问就露馅。

---

## 参考来源

### Agent 范式
- [AI Agent 模式全景图：从 ReAct 到 Multi-Agent 的演进之路](https://zhuanlan.zhihu.com/p/1968071452067620000)
- [The 7 Design Patterns Every AI Agent Developer Should Know in 2026](https://pub.towardsai.net/the-7-design-patterns-every-ai-agent-developer-should-know-in-2026-c77f28b51565)
- [ReAct vs Plan-and-Execute 实战对比](https://dev.to/jamesli/react-vs-plan-and-execute-a-practical-comparison-of-llm-agent-patterns-4gh9)
- [LangChain Planning Agents](https://www.langchain.com/blog/planning-agents)

### 编排框架
- [2026 多 Agent 架构对比（腾讯云）](https://cloud.tencent.com/developer/article/2639437)
- [Best Multi-Agent Frameworks 2026](https://gurusup.com/blog/best-multi-agent-frameworks-2026)
- [Agent 智能体开发模式 2025-2026 前沿全景](https://zhuanlan.zhihu.com/p/2040719963787355165)

### 记忆机制
- [A Survey on the Memory Mechanism of LLM based Agents (ACM)](https://dl.acm.org/doi/10.1145/3748302)
- [A-Mem: Agentic Memory for LLM Agents](https://openreview.net/forum?id=FiM0M8gcct)
- [RAG Is Not Agent Memory (Letta)](https://www.letta.com/blog/rag-vs-agent-memory/)
- [Beyond RAG: Why AI Agents Need Long-Term Memory](https://xtrace.ai/blog/rag-vs-long-term-memory-ai-agents)

### Reflexion
- [Agentic Design Patterns Part 2: Reflection (DeepLearning.AI)](https://www.deeplearning.ai/the-batch/agentic-design-patterns-part-2-reflection)
