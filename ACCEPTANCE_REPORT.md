# 第三方依赖选型阶段验收报告

日期：2026-07-01

阶段目标：完成第三方 GitHub 项目和开源依赖的技术选型，不开始大规模业务代码开发。

## 阶段结论

第一版推荐采用：

- LangGraph：第一层 workflow、state orchestration、checkpoint、interrupt/resume 底座；
- `langgraph-checkpoint-postgres`：LangGraph checkpoint 的 PostgreSQL 持久化；
- FastAPI：外部控制 API；
- Pydantic：内部 DTO、配置和边界校验；
- PostgreSQL：业务状态、审计、预算、权限和 checkpoint 存储；
- Docker + Git worktree：Coding/Simulation/Virtuoso 等高风险执行任务隔离；
- Codex Adapter：第一版 Coding Worker 接入方式。

第一版不采用：

- OpenAI Agents SDK：不进第一层；保留为后续 Worker runtime 候选；
- CrewAI：不采用，避免与 LangGraph 和内部领域层重叠；
- MetaGPT：不采用，Python `<3.12` 兼容限制和维护节奏不满足第一版；
- OpenHands：不进第一版；后续仅可作为高风险 Coding Worker 候选；
- Microsoft Agent Framework：不采用，保留为未来替代或 Microsoft/Azure worker runtime 候选。

## 核心理由

LangGraph 最贴合第一层“状态编排、checkpoint、中断恢复、人工审批”的需求。Project、Task、Approval、Audit、Permission、Budget 和 WorkerRun 保持自研，第三方框架通过 Adapter 隔离，避免把第三方数据模型扩散到业务域。

OpenHands、CrewAI、MetaGPT、Microsoft Agent Framework 与第一层编排或第二层 Coding Worker 能力存在重叠。第一版只选择一个编排底座，先把权限、预算、审批、审计、Docker/worktree 隔离和 Codex Adapter 打牢。

## 关键许可证风险

- LangGraph、OpenAI Agents SDK、CrewAI、MetaGPT、Microsoft Agent Framework、FastAPI、Pydantic 均按官方 LICENSE 记录为 MIT，允许商业使用和修改，但必须保留版权和许可证声明。
- PostgreSQL 使用 PostgreSQL License，允许商业使用、修改和分发，需保留版权和许可声明。
- OpenHands 根 LICENSE 指出 `enterprise/` 目录单独授权；`enterprise/LICENSE` 是 PolyForm Free Trial License 1.0.0，不允许分发副本，且每个日历年超过 30 天使用需要商业许可证。第一版明确排除 `enterprise/`。

## 审查处理

已使用独立架构审查子 Agent 和安全/许可证审查子 Agent。

已解决的高/中风险发现：

- 将 Coding Worker 沙箱策略从“必要时 Docker”修正为：shell、测试、build、formatter、linter、用户代码执行和依赖下载默认必须进入 Docker 或远程受控沙箱；
- 明确 WorkerRun 只有一个实际启动入口：LangGraph node 调用 Worker Dispatcher side-effect port；
- 增加 `LANGGRAPH_STRICT_MSGPACK=true` 或显式 allowlist 的 checkpoint 反序列化安全要求；
- 增加 checkpoint 敏感数据分级、TTL、加密、独立 schema/DB role 和启动自检要求；
- 增加外部模型/provider、tracing、telemetry、私有代码和 prompt 外发边界；
- 明确 Git worktree 不是安全边界，并补充 symlink、submodule、LFS、hooks、clean/smudge、realpath 和 diff 扫描控制；
- 强化 Docker sandbox：非 root、无 privileged、`cap-drop=ALL`、只读 rootfs、seccomp/AppArmor、无 host PID/IPC/network、egress allowlist、禁止挂载 SSH agent/Git/cloud 凭据；
- 明确 OpenHands `enterprise/` 的 PolyForm Free Trial 限制；
- 补充 LangGraph 替换成本：in-flight workflow、历史 checkpoint、审批 token、WorkerRun、幂等键、审计回放、双跑和回滚。

## 生成文件

- `docs/DEPENDENCY_EVALUATION.md`
- `docs/THIRD_PARTY_ARCHITECTURE.md`
- `docs/LICENSE_INVENTORY.md`
- `docs/DEPENDENCY_UPDATE_POLICY.md`
- `docs/DECISIONS/ADR-001-agent-orchestration-framework.md`
- `docs/DECISIONS/ADR-002-coding-worker-integration.md`
- `ACCEPTANCE_REPORT.md`

## 未执行事项

- 未安装所有候选框架；
- 未 fork 或复制第三方仓库源码；
- 未接入真实 API key；
- 未启动会产生费用的服务；
- 未实现完整业务代码。

## 下一阶段建议

进入第一版骨架实现：

1. 初始化 Python 3.12 项目结构和依赖锁；
2. 建立 FastAPI health/control skeleton；
3. 定义 Pydantic DTO 和领域边界；
4. 建立 PostgreSQL schema/migration 草案；
5. 实现 LangGraph Adapter 最小 workflow；
6. 验证 checkpoint、interrupt、人工审批 resume；
7. 实现 Codex Adapter dry-run；
8. 实现 Git worktree + Docker sandbox spike；
9. 加入 license scan、SBOM、secret scan 和基础供应链检查。

## 验收选项

- 通过：进入第一版骨架实现；
- 驳回：重新进行依赖选型；
- 暂停：暂不继续；
- 调整目标：重新规划技术组合。
