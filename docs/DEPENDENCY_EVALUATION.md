# 第三方依赖技术选型评估

核验日期：2026-07-01

本阶段只完成第三方 GitHub 项目和开源依赖选型，不开始大规模业务代码开发。结论基于官方 GitHub 仓库、官方文档、发布记录、PyPI 包元数据、安全说明和 LICENSE 文件；本文件不是法律意见。

## 第一版唯一技术组合

第一版采用：

| 层级 | 采用项 | 锁定建议 | 角色 |
| --- | --- | --- | --- |
| 第一层编排 | `langgraph` | `==1.2.7`，进入实现前通过恢复/审批 smoke 矩阵 | 工作流、状态图、checkpoint、中断恢复、人工审批 |
| checkpoint 存储 | `langgraph-checkpoint-postgres` | `==3.1.0` | LangGraph checkpoint 存入 PostgreSQL |
| 外部接口 | `fastapi` | `==0.138.2` | 控制 API、审批回调、管理接口 |
| 内部协议 | `pydantic` | `==2.13.4` | Project、Task、Approval、Audit、Worker DTO |
| 业务数据库 | PostgreSQL | 固定受支持小版本或镜像 digest | 业务状态、审计、权限、预算、checkpoint |
| Coding Worker | Codex Adapter | 内部接口 | 第一版受控 Coding Worker |
| 执行隔离 | Docker + Git worktree | 固定镜像 digest | 不可信代码、测试、构建、仿真隔离 |

第一版不同时引入 CrewAI、MetaGPT、OpenHands、Microsoft Agent Framework 作为核心编排框架。OpenAI Agents SDK 暂不作为第一层底座，可作为后续 Worker runtime 候选。

## 候选项目总览

| 项目 | 官方仓库 | 当前状态 | Python 兼容 | 许可证 | 第一版结论 |
| --- | --- | --- | --- | --- | --- |
| LangGraph | https://github.com/langchain-ai/langgraph | release `1.2.7`，2026-06-30，活跃 | `>=3.10` | MIT | 采用 |
| OpenAI Agents SDK | https://github.com/openai/openai-agents-python | release `v0.17.7`，2026-06-24，活跃 | `>=3.10` | MIT | 不进第一层；后续 Worker 候选 |
| CrewAI | https://github.com/crewAIInc/crewAI | release `1.15.1`，2026-06-27，活跃 | `>=3.10,<3.14` | MIT | 不采用 |
| MetaGPT | https://github.com/FoundationAgents/MetaGPT | GitHub release `v0.8.1`，PyPI `0.8.2`，发布节奏偏旧 | `>=3.9,<3.12` | MIT | 不采用 |
| OpenHands | https://github.com/OpenHands/OpenHands | tag `cloud-1.40.0`，PyPI `openhands-ai 1.8.0`，活跃 | `>=3.12,<3.14` | MIT，`enterprise/` 另行授权 | 不进第一版；后续高风险 Worker 候选 |
| Microsoft Agent Framework | https://github.com/microsoft/agent-framework | release `python-1.10.0`，2026-06-30，活跃 | `>=3.10` | MIT | 不采用 |

## LangGraph

**用途**：第一层决策和控制层的工作流、状态图、checkpoint、人工审批中断和失败恢复底座。

**官方仓库和维护主体**：`langchain-ai/langgraph`，维护主体为 LangChain/LangGraph 团队。

**维护状态和发布**：仓库未归档，2026-07-01 仍有提交。最新 release 为 `1.2.7`，发布于 2026-06-30。仓库包含 docs、examples、libs、CI、集成测试和 release workflow。

**兼容性**：`langgraph` 要求 Python `>=3.10`，声明支持 Python 3.10-3.13。`langgraph-checkpoint-postgres==3.1.0` 要求 Python `>=3.10`。生产基线建议 Linux 容器；Windows 仅作为开发端。

**许可证和商业使用**：MIT。允许商业使用、复制、修改、分发和再授权，但必须保留版权和许可声明。

**核心功能**：状态图、durable execution、persistence、interrupt/resume、human-in-the-loop、memory、streaming、subgraph、tool node、PostgreSQL checkpoint saver。

**匹配程度**：与第一层高度匹配。它提供状态和恢复底座，但不替代 Project、Task、Approval、Audit、权限和预算领域层。与第二层只通过 Worker Adapter 间接交互。

**功能重叠**：与 CrewAI、MetaGPT、Microsoft Agent Framework 在多 agent 编排上重叠。因此第一版只选 LangGraph 一个编排底座。

**接入方式**：只在 `OrchestrationPort` 的 LangGraph Adapter 内使用；业务层禁止直接 import LangGraph 类型。checkpoint 只用于恢复上下文，业务状态以 PostgreSQL 领域表为权威来源。

**升级策略**：固定 `langgraph==1.2.7` 和 `langgraph-checkpoint-postgres==3.1.0`。由于 `1.2.7` 发布很近，进入实现前需完成 7 天 soak，或通过恢复、审批、拒绝审批、worker 失败、回滚、checkpoint 清理 smoke 矩阵。

**安全风险**：

- graph node/tool 可能触发 shell、网络、文件系统或外部服务，必须经过 Adapter 和权限层；
- checkpoint 可能保存用户目标、模型输出、工具结果和敏感上下文，必须最小化、分级、加密和设置 TTL；
- `langgraph-checkpoint-postgres` 官方 PyPI 安全说明要求设置 `LANGGRAPH_STRICT_MSGPACK=true`，或传入显式 `allowed_msgpack_modules` allowlist，以降低数据库被攻破后反序列化导致代码执行的风险；
- checkpoint 需使用独立 schema、最小权限 DB role、启动自检、备份清理策略；
- transitive dependency 纳入 `pip-audit`、SBOM、Dependabot/Renovate 和镜像扫描。

**是否需要运行不可信代码**：LangGraph 本身不需要；任何执行代码的节点必须调度隔离 Worker。

**持久化、中断恢复和人工审批**：具备，是采用的主要原因。人工审批由领域层创建，LangGraph interrupt 只负责暂停和恢复控制流。

**测试和文档**：较好。官方文档覆盖 overview、persistence、interrupts 等关键主题，仓库有多套测试和 CI。

**维护成本**：中等。需要维护 Adapter、checkpoint 兼容测试、状态迁移、恢复语义测试和审批回归测试。

**是否采用**：采用。

**优点**：贴合第一层状态编排；MIT 清晰；与 PostgreSQL/FastAPI/Pydantic 组合自然；不强制引入角色团队模型。

**缺点**：仍需自研领域层；业务状态和 checkpoint 需要一致性设计；升级可能影响恢复语义。

**未来重新评估条件**：checkpoint 或 interrupt/resume 出现不可接受的破坏性变化；其他框架提供更成熟且迁移成本可控的 durable workflow；系统需要跨 Python/.NET 的一体化编排。

**官方来源**：

- https://github.com/langchain-ai/langgraph
- https://github.com/langchain-ai/langgraph/releases/tag/1.2.7
- https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/pyproject.toml
- https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-postgres/pyproject.toml
- https://github.com/langchain-ai/langgraph/blob/main/LICENSE
- https://docs.langchain.com/oss/python/langgraph/overview
- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://pypi.org/project/langgraph-checkpoint-postgres/

## OpenAI Agents SDK

**用途**：Agent、tool、handoff、guardrail、sessions、tracing、Sandbox Agents 等 multi-agent runtime。第一版不作为核心编排底座。

**官方仓库和维护主体**：`openai/openai-agents-python`，维护主体 OpenAI。

**维护状态和发布**：仓库未归档，2026-07-01 仍有提交。最新 release/PyPI 为 `0.17.7`，发布于 2026-06-24。仓库包含 docs、examples、src、tests 和发布 workflow。

**兼容性**：Python `>=3.10`，声明支持 3.10-3.14。纯 SDK 跨平台；Sandbox Agents、本地 shell 或 computer-use 需要独立安全策略。

**许可证和商业使用**：MIT，允许修改和商业使用，需保留版权和许可声明。

**核心功能**：Agents、Runner、tools、handoffs、guardrails、human-in-the-loop、sessions、tracing、MCP、Sandbox Agents、voice/realtime 扩展。

**匹配程度**：与第二层 Worker runtime 中高匹配，尤其是模型调用、guardrail 和 tracing；与第一层项目级审批、预算、审计、持久化状态机匹配不足。

**功能重叠**：与 LangGraph 在 workflow、handoff、tool orchestration 上重叠。与 Codex/OpenHands 在 Sandbox Agent 的文件检查、命令执行、patch 应用上重叠。

**Sandbox Agent 与 Codex/OpenHands 的关系**：官方包说明将 Sandbox Agents、human-in-the-loop、sessions、tracing 列为核心概念，并说明 Sandbox Agent 可在受控 filesystem 中检查文件、运行命令、应用 patch、保留 workspace state。第一版不采用它作为 Coding Worker，是因为当前优先建立外层权限、预算、审批、审计和 Docker/worktree 隔离；后续只有在需要 OpenAI SDK 原生 guardrail、handoff、tracing 或 sandbox runtime 的增量价值时，才通过 Worker Adapter 重评。

**接入方式**：第一版不接入。后续如采用，只能通过 `WorkerRuntimeAdapter` 接入，禁止 session、trace、message 类型扩散到领域模型。

**升级策略**：后续采用时锁定 `openai-agents` 和 `openai` SDK 主版本，并验证 tool schema、handoff、session、tracing 行为。

**安全风险**：tool 可能访问文件、网络、shell 或外部 API；tracing/session 可能记录敏感上下文；API key、配额和费用必须由本系统权限/预算层控制；默认关闭外发 tracing/telemetry。

**是否需要运行不可信代码**：SDK 本身不需要；Sandbox/local shell/computer-use 会间接执行不可信代码，必须隔离。

**持久化、中断恢复和人工审批**：有 sessions、human-in-the-loop、guardrails，但不等同项目级 durable workflow 和审批引擎。

**测试和文档**：较好。官方文档完整，仓库有 tests、examples 和发布 workflow。

**维护成本**：中等。主要在 OpenAI SDK 兼容、tracing 数据治理、API key、模型/工具权限和费用控制。

**是否采用**：第一版不采用为核心依赖；列入后续 Worker runtime 候选。

**优点**：OpenAI 官方维护；MIT 清晰；guardrail、handoff、tracing 对 Worker 有价值。

**缺点**：与 LangGraph 编排重叠；项目级状态、权限、审批和恢复不足；增加 provider 耦合。

**不采用理由**：第一版已选择 LangGraph 作为唯一编排底座，避免双状态和双恢复语义。

**未来重新评估条件**：Worker 需要 OpenAI 原生 guardrail/handoff/tracing；SDK 提供成熟可审计可恢复 workflow；某一 Worker 明确受益。

**官方来源**：

- https://github.com/openai/openai-agents-python
- https://github.com/openai/openai-agents-python/releases/tag/v0.17.7
- https://github.com/openai/openai-agents-python/blob/main/pyproject.toml
- https://github.com/openai/openai-agents-python/blob/main/LICENSE
- https://openai.github.io/openai-agents-python/
- https://github.com/openai/openai-agents-python/blob/main/SECURITY.md
- https://pypi.org/project/openai-agents/

## CrewAI

**用途**：Crew、Flow、Task、Agent、Tool、Memory、Knowledge 等角色协作框架。

**官方仓库和维护主体**：`crewAIInc/crewAI`，维护主体 crewAI Inc.

**维护状态和发布**：活跃维护，最新 release/PyPI `1.15.1`，发布于 2026-06-27。仓库有 docs、lib、scripts、tests、type-checker、CodeQL、vulnerability-scan workflow。

**兼容性**：Python `>=3.10,<3.14`。

**许可证和商业使用**：MIT，允许修改和商业使用，需保留版权和许可声明。

**核心功能**：Crews、Flows、Tasks、Agents、Tools、Memory、Knowledge、human input、planning、telemetry、tracing/observability 集成。

**匹配程度**：与第一层部分匹配，但更偏角色团队和任务执行框架，不适合作为本项目 Project/Task/Approval/Audit 权限核心。对 Research/Document Worker 有参考价值。

**功能重叠**：与 LangGraph 在多 agent、流程、任务、状态和工具编排上高度重叠。

**接入方式**：第一版不接入；仅作为概念参考。后续若引入，只能作为单个 Worker runtime，被 Adapter 包裹。

**升级策略**：后续采用时固定版本，生成 SBOM，对 transitive dependencies 做漏洞扫描。

**安全风险**：工具和 agent 可触发网络、文件、浏览器、代码执行；telemetry/observability 可能外发运行数据；CrewAI Task/Agent 模型不应成为本项目业务模型。

**是否需要运行不可信代码**：框架本身不要求，但实际工具可能执行不可信代码，必须沙箱化。

**持久化、中断恢复和人工审批**：有 flows state、human input、memory，但不满足项目级审批、预算、审计和失败恢复。

**测试和文档**：较好。官方文档和 CI 比较完整。

**维护成本**：中高。依赖面、工具生态和 telemetry 治理成本较高。

**是否采用**：不采用。

**优点**：产品化程度高；角色协作表达友好；文档和 CI 较完整；MIT 清晰。

**缺点**：与 LangGraph 重叠；抽象可能侵入内部领域层；依赖面较宽。

**不采用理由**：第一版需要单一、可控、可恢复的第一层底座，CrewAI 会与内部领域层争夺主导模型。

**未来重新评估条件**：需要快速构建角色型 Research/Document Worker；CrewAI 的 flow persistence、审批、权限和审计更成熟；可作为隔离 Worker runtime。

**官方来源**：

- https://github.com/crewAIInc/crewAI
- https://github.com/crewAIInc/crewAI/releases/tag/1.15.1
- https://github.com/crewAIInc/crewAI/blob/main/pyproject.toml
- https://github.com/crewAIInc/crewAI/blob/main/LICENSE
- https://docs.crewai.com/
- https://docs.crewai.com/concepts/flows

## MetaGPT

**用途**：软件公司式多 agent 框架，面向自然语言到软件工程流程的角色分工、文档和代码生成。

**官方仓库和维护主体**：`FoundationAgents/MetaGPT`，维护主体 FoundationAgents。PyPI home page 历史上指向 `geekan/MetaGPT`，本次以 FoundationAgents 官方仓库为准。

**维护状态和发布**：仓库未归档，但最新 GitHub release 为 `v0.8.1`，发布于 2024-04-22；PyPI 最新 `0.8.2`。主分支 `setup.py` 标 `1.0.0`，但不能将 main 分支当生产依赖。

**兼容性**：`python_requires=">=3.9,<3.12"`，与第一版 Python 3.12 目标不兼容；部分依赖固定旧版本。

**许可证和商业使用**：MIT，允许修改和商业使用，需保留版权和许可声明。

**核心功能**：多角色软件开发流程、SOP、role/task/action、文档、代码、评审流水线。

**匹配程度**：可作为 Coding/Document Worker 的概念参考，不适合第一层通用控制底座。

**功能重叠**：与 LangGraph、CrewAI 在多 agent 编排和软件工程流程上重叠，也与 Codex Coding Worker 定位重叠。

**接入方式**：第一版不接入，不复制源码，不引入其数据模型。

**升级策略**：不锁定生产依赖。未来需等 Python 3.12+ 兼容、稳定 release、依赖安全扫描和维护节奏恢复。

**安全风险**：软件生成和执行流程可能运行不可信代码；旧依赖和 Python `<3.12` 增加供应链维护成本；SECURITY.md 的支持版本边界不够清晰。

**是否需要运行不可信代码**：如果用于 Coding Worker，会生成并可能执行代码，必须隔离；第一版不使用。

**持久化、中断恢复和人工审批**：不满足第一层项目级持久化、审批和恢复要求。

**测试和文档**：有 docs、examples、tests 和 CI，但 release 节奏、Python 兼容和依赖新鲜度不足。

**维护成本**：高。

**是否采用**：不采用。

**优点**：软件工程角色/SOP 思路有参考价值；MIT 清晰。

**缺点**：Python 版本不匹配；稳定 release 较旧；预设流程较重。

**不采用理由**：与 Python 3.12、可维护性和第一层通用控制目标不匹配。

**未来重新评估条件**：发布支持 Python 3.12/3.13 的稳定版本；明确安全支持版本；可作为隔离 Worker runtime；与 Codex 职责边界清晰。

**官方来源**：

- https://github.com/FoundationAgents/MetaGPT
- https://github.com/FoundationAgents/MetaGPT/releases/tag/v0.8.1
- https://github.com/FoundationAgents/MetaGPT/blob/main/setup.py
- https://github.com/FoundationAgents/MetaGPT/blob/main/LICENSE
- https://github.com/FoundationAgents/MetaGPT/blob/main/SECURITY.md

## OpenHands

**用途**：AI-driven development 执行环境，面向代码修改、命令执行、浏览器/终端交互和软件工程自动化。

**官方仓库和维护主体**：`OpenHands/OpenHands`，维护主体 OpenHands/All Hands AI。

**维护状态和发布**：活跃维护。GitHub 最新 tag `cloud-1.40.0`，发布于 2026-06-26；PyPI `openhands-ai==1.8.0`。仓库包含 frontend、openhands、containers、enterprise、tests 和多套 CI。

**兼容性**：Python `>=3.12,<3.14`。实际运行强依赖 Docker/容器/浏览器/终端，生产应以 Linux 容器为准。

**许可证和商业使用**：根 LICENSE 明确 `enterprise/` 使用 `enterprise/LICENSE`，其余内容按 MIT。`enterprise/LICENSE` 是 PolyForm Free Trial License 1.0.0，不允许分发副本，且每个日历年超过 30 天使用需要商业许可证。因此不得复制、打包、构建进镜像或使用 `enterprise/`。

**核心功能**：AI 软件工程 agent、容器 runtime、代码编辑、shell、浏览器/前端任务、UI、server、runtime、多种 remote provider。

**匹配程度**：与第二层 Coding Worker 高度相关，但风险最高。与第一层不匹配，不能承担项目级编排和审批。

**功能重叠**：与 Codex Coding Worker 和 OpenAI Agents SDK Sandbox Agents 在代码执行层重叠。

**接入方式**：第一版不接入。后续如接入，只能通过 `CodingWorkerAdapter`，每个任务使用独立 Git worktree 和 Docker/远程沙箱，固定镜像 digest，默认最小权限。

**升级策略**：后续采用时固定 `openhands-ai`、前端包、容器镜像 digest 和 runtime provider。升级前必须跑沙箱逃逸、权限回归、许可证目录扫描和供应链扫描。

**安全风险**：天然运行不可信代码；Docker 配置错误可能暴露宿主机、Docker socket、网络或凭据；remote runtime provider 有数据出境风险；`enterprise/` 目录许可证边界必须机器检查；license scan 必须覆盖源码、构建上下文、镜像层和发布包。

**是否需要运行不可信代码**：是。必须隔离，不能给不受限 shell。

**持久化、中断恢复和人工审批**：有自身会话/任务能力，但不能替代第一层审批、审计和恢复。命令执行、文件写入、网络访问、提交/推送都必须由外层审批。

**测试和文档**：较好。仓库有 tests、前端 e2e/unit、Python tests、容器构建和发布 workflow。

**维护成本**：高。

**是否采用**：第一版不采用；保留为后续高风险 Coding Worker 候选。

**优点**：Coding Worker 能力强；容器 runtime 方向与隔离原则一致；维护活跃。

**缺点**：高风险代码执行；许可证有目录级特殊授权；与 Codex 重叠；安全审查成本高。

**不采用理由**：第一版先建立可控第一层骨架和 Codex Adapter，OpenHands 等外层安全边界成熟后再评估。

**未来重新评估条件**：第一层权限/预算/审批/审计已实现；Docker/worktree 沙箱通过回归；固定镜像 digest；license scan 稳定排除 `enterprise/`；证明相对 Codex 有增量价值。

**官方来源**：

- https://github.com/OpenHands/OpenHands
- https://github.com/OpenHands/OpenHands/releases/tag/cloud-1.40.0
- https://github.com/OpenHands/OpenHands/blob/main/pyproject.toml
- https://github.com/OpenHands/OpenHands/blob/main/LICENSE
- https://github.com/OpenHands/OpenHands/blob/main/enterprise/LICENSE
- https://docs.all-hands.dev/

## Microsoft Agent Framework

**用途**：Microsoft 维护的 Python/.NET agent 和 multi-agent workflow 框架。

**官方仓库和维护主体**：`microsoft/agent-framework`，维护主体 Microsoft。

**维护状态和发布**：活跃维护。最新 release `python-1.10.0`，发布于 2026-06-30；PyPI `agent-framework==1.10.0`。仓库有 `python/`、`dotnet/`、docs、schemas、declarative-agents 和大量 CI。

**兼容性**：Python `>=3.10`，声明支持 3.10-3.14；同时支持 .NET。

**许可证和商业使用**：MIT，允许修改和商业使用，需保留版权和许可声明。仓库有 Microsoft SECURITY.md，漏洞报告走 MSRC。

**核心功能**：agents、multi-agent workflow、Python/.NET、OpenAI/Azure OpenAI provider、MCP、observability、deployment、schemas、declarative agents。

**匹配程度**：与第一层有潜在匹配，但第一版 LangGraph 已满足核心需求。与第二层 Microsoft/Azure Worker runtime 也可能匹配。

**功能重叠**：与 LangGraph 高度重叠。二者同时作为编排核心会造成双状态、双恢复、双 tool/runtime 体系。

**接入方式**：第一版不接入。未来作为替代底座或 Microsoft/Azure Worker runtime 候选，必须做 Adapter spike。

**升级策略**：后续采用时固定版本；跨 Python/.NET/provider 依赖需要更严格集成测试矩阵。

**安全风险**：agent/tool 可能触发外部服务和代码执行；provider、MCP、observability 可能引入凭据和数据外发；框架升级频繁，API 稳定性需实测。

**是否需要运行不可信代码**：框架本身不需要；使用工具、MCP server、代码执行或部署能力后可能运行不可信代码，必须隔离。

**持久化、中断恢复和人工审批**：具备一定 workflow 能力，但需 spike 验证是否满足项目级审批、审计、预算和恢复。

**测试和文档**：较好。仓库有 Python/.NET build、测试、文档、CodeQL 和 dependency maintenance workflow。

**维护成本**：中高。

**是否采用**：不采用。

**优点**：Microsoft 官方维护；MIT 清晰；Python/.NET 双生态；安全响应流程完整。

**缺点**：与 LangGraph 重叠；增加跨语言和 provider 复杂度。

**不采用理由**：LangGraph 更直接满足第一层状态编排和可恢复执行需求。

**未来重新评估条件**：需要 Python/.NET 同构编排；Azure/Microsoft 生态成为一等 provider；LangGraph 无法满足 durable workflow；spike 证明迁移收益大于成本。

**官方来源**：

- https://github.com/microsoft/agent-framework
- https://github.com/microsoft/agent-framework/releases/tag/python-1.10.0
- https://github.com/microsoft/agent-framework/blob/main/python/pyproject.toml
- https://github.com/microsoft/agent-framework/blob/main/LICENSE
- https://github.com/microsoft/agent-framework/blob/main/SECURITY.md
- https://learn.microsoft.com/en-us/agent-framework/

## 支撑依赖

**FastAPI**：采用 `fastapi==0.138.2` 作为外部 API 层。官方仓库 `fastapi/fastapi`，MIT，Python `>=3.10`，依赖 Pydantic。需要锁定 Starlette/Uvicorn 并纳入漏洞扫描。

**Pydantic**：采用 `pydantic==2.13.4` 作为内部协议和边界校验。官方仓库 `pydantic/pydantic`，MIT。第一版以 Python 3.12 为目标。

**PostgreSQL**：采用受支持 PostgreSQL 小版本作为业务状态和 checkpoint 数据库。许可证为 PostgreSQL License，允许商业使用、修改和分发，需保留版权和许可声明。不得使用 `postgres:latest`。

## 最终决策

第一版明确采用 LangGraph + 自研领域层 + FastAPI + Pydantic + PostgreSQL + Docker/Git worktree + Codex Adapter。该组合在候选方案中迁移面最小，因为核心领域模型由本项目控制，第三方实现被 Adapter 隔离。

未来替换 LangGraph 仍不是零成本，需要处理 in-flight workflow、历史 checkpoint、审批 token、WorkerRun 关联、幂等键、审计回放、双跑验证和回滚窗口。
