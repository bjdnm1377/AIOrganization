# ADR-001: 第一层 Agent 编排框架

日期：2026-07-01
状态：Accepted

## 背景

本项目要构建两层 AI 组织系统。第一层负责理解用户目标、规划项目、拆解任务、调度 Worker、管理状态、权限、预算、人工审批、审查验收、返工和失败恢复。第二层包含 Research、Coding、Document、Review、Circuit、Simulation、Virtuoso 等 Worker。

候选项目：

- `langchain-ai/langgraph`；
- `openai/openai-agents-python`；
- `crewAIInc/crewAI`；
- `FoundationAgents/MetaGPT`；
- `OpenHands/OpenHands`；
- `microsoft/agent-framework`。

## 决策

第一版采用 LangGraph 作为第一层 workflow、state orchestration、checkpoint、interrupt/resume 底座。

第一版同时采用：

- 自研 Project、Task、Approval、Audit、Permission、Budget 领域层；
- FastAPI 作为外部控制接口；
- Pydantic 作为内部协议；
- PostgreSQL 作为业务状态数据库和 LangGraph checkpoint 存储；
- Adapter 隔离 LangGraph；
- Docker + Git worktree 隔离高风险执行任务。

第一版不引入 CrewAI、MetaGPT、OpenHands、Microsoft Agent Framework 作为核心编排框架。OpenAI Agents SDK 不进入第一层，可在后续作为 Worker runtime 候选。

## 采用 LangGraph 的理由

LangGraph 官方定位和文档覆盖 durable execution、persistence、human-in-the-loop、interrupt/resume、memory、streaming 等能力，直接匹配第一层可恢复状态编排需求。

LangGraph 许可证为 MIT，Python 要求 `>=3.10`，最新 release `1.2.7` 发布于 2026-06-30，仓库维护活跃。`langgraph-checkpoint-postgres==3.1.0` 可与 PostgreSQL 组合，满足第一版持久化方向。

## 未采用候选项的理由

### OpenAI Agents SDK

OpenAI Agents SDK 适合 agent runtime、tool、handoff、guardrail、sessions、tracing 和 Sandbox Agents，但不是项目级审批、预算、审计和 durable workflow 的完整底座。第一版若同时引入，会与 LangGraph 产生双编排和双状态语义。

### CrewAI

CrewAI 的 Crew/Flow/Task/Agent 抽象与 LangGraph 以及本项目自研 Project/Task/Approval/Audit 领域层重叠。它更适合作为后续某类 Worker runtime 或概念参考。

### MetaGPT

MetaGPT 的软件公司式 SOP 有参考价值，但最新稳定发布较旧，Python 兼容为 `>=3.9,<3.12`，与第一版 Python 3.12 目标不匹配。

### OpenHands

OpenHands 是强执行型 Coding Worker 候选，涉及代码编辑、shell、容器和浏览器交互。它不适合作为第一层编排底座，且仓库 `enterprise/` 目录存在 PolyForm Free Trial 特殊授权，第一版不引入。

### Microsoft Agent Framework

Microsoft Agent Framework 维护活跃、MIT、Python/.NET 双生态，但与 LangGraph 在 agent workflow 上重叠。第一版没有足够理由同时承担双框架复杂度。

## 后果

正面影响：

- 第一层拥有明确、可恢复的 workflow 底座；
- 业务领域模型由本项目控制；
- 第三方框架被 Adapter 隔离，未来可替换；
- 人工审批可以用 LangGraph interrupt/resume 承载；
- PostgreSQL 可以同时承载业务状态和 checkpoint。

负面影响：

- 需要自研 Project、Task、Approval、Audit、Permission、Budget；
- 需要维护 LangGraph Adapter 和 checkpoint 兼容测试；
- 需要避免业务状态和 checkpoint 状态不一致；
- LangGraph 版本升级必须审查恢复语义。

## 迁移成本分析

如果未来从 LangGraph 迁移到 Microsoft Agent Framework 或其他编排底座，主要成本集中在：

- `OrchestrationPort` 实现；
- workflow DSL 映射；
- checkpoint/resume 迁移；
- interrupt/approval 映射；
- worker dispatch node 改造；
- 恢复兼容测试。

由于 Project、Task、Approval、Audit、Permission、Budget 不依赖 LangGraph 类型，迁移不应扩散到整个系统。

迁移仍然不是零成本。未来替换编排底座时必须处理：

- in-flight workflow 的暂停、完成或双跑；
- 历史 checkpoint 的保留、转换或清理；
- 审批 token 和 interrupt/resume 关联；
- WorkerRun、幂等键和审计日志关联；
- 审计回放和结果可追溯；
- 新旧编排底座并行验证窗口；
- 回滚策略和迁移失败恢复。

## 验证要求

第二阶段骨架实现必须验证：

1. 一个 Project 可以创建 workflow；
2. workflow 可以写入 checkpoint；
3. ApprovalGate 可以 interrupt；
4. 人工审批后可以 resume；
5. worker 失败可以记录并进入返工路径；
6. 恢复时重新读取权限和预算，而不是信任旧 checkpoint；
7. `LANGGRAPH_STRICT_MSGPACK=true` 或显式 `allowed_msgpack_modules` allowlist 已启用；
8. checkpoint 不保存 API key、访问 token、完整 env dump 或不必要的原始 prompt；
9. checkpoint schema、DB role、TTL、加密和备份清理策略通过启动自检。
