# ADR-002: Coding Worker 接入策略

日期：2026-07-01
状态：Accepted

## 背景

系统第二层需要 Coding Worker。Coding Worker 后续要能读取任务、修改代码、运行测试、报告结果，并在必要时请求人工审批。Codex 将作为运行阶段的 Coding Worker 之一。候选执行组件还包括 OpenHands，OpenAI Agents SDK、CrewAI、MetaGPT、Microsoft Agent Framework 也可能在未来成为某类 worker runtime。

Coding Worker 是高风险组件，因为它可能运行 shell、修改文件、访问网络、使用 API key、提交代码或触发部署。

## 决策

第一版只设计 Coding Worker Adapter 边界，并优先接入 Codex。暂不接入 OpenHands，也不把其他 agent 框架作为 Coding Worker 的默认 runtime。

Codex 通过 `CodingWorkerAdapter` 接入第一层：

- 第一层创建任务、权限和预算；
- Adapter 为任务准备独立 Git worktree；
- 任何 shell、测试、build、formatter、linter、用户代码执行或依赖下载默认必须进入 Docker sandbox 或远程受控沙箱；
- 只有纯规划、dry-run、diff 汇总和允许路径内的只读检查可以不进入 Docker，但仍必须经过权限检查和审计；
- Codex 只在授权目录内工作；
- 测试、diff、命令记录、产物路径和错误原因回传第一层；
- 提交、推送、部署、扩大权限和使用真实 API key 都必须经过第一层审批。

## 接口边界

Coding Worker 不拥有 Project/Task 的最终状态。它只返回 `WorkerResult`。

WorkerResult 至少包含：

- `status`；
- `summary`；
- `changed_paths`；
- `commands` 或命令摘要；
- `tests` 或验证结果；
- `evidence`；
- `requires_approval`；
- `error`；
- `cost/runtime` 摘要。

第一层负责决定：

- 是否接受结果；
- 是否返工；
- 是否请求人工验收；
- 是否提交 Git；
- 是否扩大权限；
- 是否停止任务。

## Codex Adapter

Codex Adapter 的第一版目标是 dry-run 和受控代码任务：

- 只读取任务上下文和允许路径；
- 使用独立 worktree；
- 默认不访问生产凭据；
- 命令执行和文件修改进入审计；
- 输出结构化验收摘要。

Codex Adapter 不应：

- 直接写业务数据库；
- 直接绕过审批提交或推送；
- 直接持有全局 API key；
- 直接修改非任务 worktree；
- 把 prompt、chain-of-thought 或敏感上下文写入公开日志；
- 自行开启外发 tracing、telemetry、provider 调试日志或新的模型供应商。

## OpenHands 策略

OpenHands 第一版不接入。原因：

- 它是强执行型 AI-driven development 环境，天然涉及不可信代码和 shell；
- 需要较完整的 Docker/runtime 安全边界；
- 仓库包含 `enterprise/` 特殊授权目录，`enterprise/LICENSE` 为 PolyForm Free Trial License 1.0.0，不允许分发副本，且每个日历年超过 30 天使用需要商业许可；
- 与 Codex Coding Worker 功能重叠；
- 引入后维护成本和安全审查成本高。

未来重新评估 OpenHands 的前置条件：

- 第一层权限、预算、审批和审计已经实现；
- Git worktree + Docker sandbox 已通过回归测试；
- 可以固定 `openhands-ai` 版本、容器镜像 digest 和依赖 lock；
- license scan 能覆盖源码、构建上下文、容器镜像层和发布包，并确认没有打包 `enterprise/`；
- 网络、文件、shell、凭据权限均可由外层控制；
- 有明确场景证明 OpenHands 相对 Codex Adapter 提供增量价值。

## Git worktree 策略

每个 Coding Task 使用独立 worktree。worktree 是工作区隔离，不是安全边界：

- worktree 名称包含 project/task id；
- 初始分支来自受控 base ref；
- 任务完成后保留 diff 和验证日志；
- 合并、提交、推送由第一层审批；
- 失败任务可保留 worktree 供审计或返工；
- 清理前保存必要产物；
- 禁用或隔离 Git hooks；
- 默认禁用 submodule 和 LFS，确需启用需审批；
- 禁用或审查 clean/smudge filter；
- 所有写入路径做 realpath 校验，防止 symlink/path traversal；
- 合并前扫描 diff、权限位、二进制文件和大文件；
- 防止跨 worktree ref 污染和共享 object store 误用。

## Docker 策略

Docker 用于所有 shell、测试、build、formatter、linter、用户代码执行、依赖下载和其他不可信代码执行：

- 使用固定镜像 digest；
- 非 root 用户运行；
- 只挂载任务 worktree；
- 不挂载宿主 Docker socket；
- 默认无网络；
- 限制 CPU、内存、进程数和运行时间；
- 通过 allowlist 暴露工具；
- `cap-drop=ALL`，禁用 privileged；
- 默认只读 rootfs，临时目录显式挂载；
- 启用 seccomp/AppArmor 或平台等价策略；
- 禁止 host PID、host IPC、host network；
- 需要网络时使用 egress allowlist；
- 禁止挂载 SSH agent、Git 凭据、云凭据和宿主 Docker socket；
- 校验镜像来源、签名或 digest；
- 容器日志进入审计。

## 外部模型和遥测

Coding Worker 默认不得外发 tracing、telemetry、原始代码、私有仓库内容、用户 prompt 或 provider 调试数据。发送到外部模型/provider 的内容必须受项目策略、用户授权和数据分级控制。日志、trace、错误报告必须脱敏，并记录 provider 的数据保留、训练使用、地域和删除策略。

## 安全后果

正面影响：

- Codex 可以成为可控 worker，而不是无限权限自动化进程；
- OpenHands 被留到安全边界成熟后再接入；
- 第一层保留审批、验收和状态权威；
- Git worktree 和 Docker 降低任务之间的污染。

负面影响：

- 第一版 Coding Worker 能力会比直接接入 OpenHands 更保守；
- Adapter、审计和隔离需要额外实现；
- 高风险任务需要更多人工审批。

## 验证要求

第二阶段骨架实现必须验证：

1. 能创建任务级 worktree；
2. Codex Adapter dry-run 能返回结构化 `WorkerResult`；
3. 未授权路径不能写入；
4. shell/network 权限默认关闭；
5. 需要扩大权限时返回审批请求；
6. diff、测试结果和错误原因能进入 Audit；
7. 运行测试或 shell 时必须进入 Docker/远程沙箱；
8. 失败任务可以被第一层重新调度。
