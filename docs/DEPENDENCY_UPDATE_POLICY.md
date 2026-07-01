# 依赖升级与锁定策略

核验日期：2026-07-01

## 目标

依赖管理目标是可复现、可审计、可回滚。第一版不得依赖第三方仓库 `main` 分支，不得把大型第三方源码复制到本仓库，不得使用未固定版本的生产镜像。

## 版本基线

| 依赖 | 锁定建议 | 说明 |
| --- | --- | --- |
| Python | `3.12.x` | 与 LangGraph、FastAPI、OpenHands 未来候选兼容；避开 MetaGPT `<3.12` |
| `langgraph` | `==1.2.7` | 第一层编排底座 |
| `langgraph-checkpoint-postgres` | `==3.1.0` | PostgreSQL checkpoint |
| `fastapi` | `==0.138.2` | 外部 API |
| `pydantic` | `==2.13.4` | 内部协议 |
| PostgreSQL | 固定受支持小版本或镜像 digest | 不使用 `latest` |

暂不锁定为生产依赖：

- `openai-agents`；
- `crewai`；
- `metagpt`；
- `openhands-ai`；
- `agent-framework`。

`langgraph==1.2.7` 发布于 2026-06-30，距离本次核验时间很近。进入第一版实现分支前必须满足以下任一条件：

- 完成至少 7 天 soak，且无影响 checkpoint、interrupt/resume、PostgreSQL saver 的阻断问题；
- 或在本项目分支通过恢复、审批、拒绝审批、worker 失败、回滚、checkpoint 清理 smoke 矩阵，并由维护者显式接受新版本风险。

## 锁定机制

Python 依赖应使用以下任一方式产生 lockfile：

- `uv.lock`；
- `requirements.txt` + hash pin；
- `poetry.lock`。

无论工具如何，生产依赖必须满足：

- 直接依赖精确锁定；
- transitive dependency 可复现；
- CI 使用 lockfile 安装；
- 依赖 PR 展示 lockfile diff；
- 构建产物记录 lockfile hash。

Docker 镜像必须：

- 固定 tag；
- 生产或高风险 worker 固定 digest；
- 记录基础镜像来源；
- 扫描 OS package CVE；
- 禁止挂载宿主 Docker socket 给不可信 worker。

## 升级节奏

| 类型 | 节奏 | 要求 |
| --- | --- | --- |
| 安全修复 | 高危通告后 24-72 小时内评估 | 可走紧急分支，必须保留审计 |
| patch/minor | 每月集中评估一次 | 分支升级、跑测试、更新文档 |
| major | 单独 ADR | 需要迁移计划、回滚计划和兼容测试 |
| LangGraph checkpoint 相关 | 不随普通 patch 自动合并 | 必须验证恢复、审批、失败重试 |
| OpenHands 或代码执行 runtime | 单独安全评审 | 必须验证沙箱和许可证目录 |

## 升级检查清单

每次依赖升级 PR 必须包含：

1. 版本变更摘要；
2. 官方 release note 链接；
3. LICENSE/NOTICE 变化；
4. `pip-audit` 或等价 Python 漏洞扫描结果；
5. SBOM diff；
6. 关键测试结果；
7. 回滚方式；
8. 是否影响 checkpoint、审批、权限、预算、审计；
9. 是否新增 shell、网络、浏览器、容器或外部 provider 能力；
10. 是否新增遥测或数据外发默认行为。

## LangGraph 专项策略

LangGraph 是第一版核心依赖。升级时必须额外验证：

- workflow 从 checkpoint 恢复；
- interrupt 后人工审批恢复；
- 审批拒绝后的返工路径；
- worker 失败后的 retry/backoff；
- state schema 迁移；
- PostgreSQL checkpoint 表兼容性；
- `LANGGRAPH_STRICT_MSGPACK=true` 或显式 allowlist；
- checkpoint 不保存 API key、原始密钥、完整 env dump；
- 并发 project/task 下的隔离；
- 权限和预算重新读取，不信任旧 checkpoint。

不允许直接升级到未发布 commit 或 `main`。

## Worker runtime 专项策略

OpenAI Agents SDK、CrewAI、OpenHands、Microsoft Agent Framework 如未来引入，必须先创建独立 ADR。ADR 至少回答：

- 作为哪类 Worker；
- 是否会运行不可信代码；
- 是否需要 API key；
- 是否产生外部费用；
- 是否有 telemetry/tracing；
- 权限如何受第一层控制；
- 数据模型如何被 Adapter 隔离；
- 如何锁版本和回滚；
- 如何做许可证和供应链扫描。

## 安全扫描

第一版实现阶段应加入：

- Python：`pip-audit` 或等价工具；
- 依赖元数据：license scan；
- SBOM：CycloneDX 或等价格式；
- Docker：镜像 CVE 扫描；
- GitHub：Dependabot/Renovate；
- secret scan；
- 禁止大文件和第三方源码误提交的检查；
- hash pin 或 lockfile hash 校验；
- 私有 package index 或 dependency confusion 防护；
- license allow/deny list；
- Sigstore/cosign 或等价镜像签名校验；
- SLSA provenance 或等价构建来源记录。

高危结果处理：

- 可利用且影响生产路径：阻断合并；
- 仅开发依赖：记录影响范围并限期修复；
- 无修复版本：记录缓解措施、隔离边界和重新评估日期。

## 兼容性矩阵

| 维度 | 目标 |
| --- | --- |
| Python | 3.12.x |
| OS | Linux 容器为生产基线；Windows 作为开发端不保证所有 worker 原生运行 |
| Database | PostgreSQL 受支持版本，固定小版本/digest |
| Coding Worker | Git worktree + Docker |
| Shell 权限 | 默认关闭，按任务审批 |
| Network 权限 | 默认关闭，按任务审批 |

## 回滚策略

依赖升级必须能够回滚：

- lockfile 回滚；
- Docker digest 回滚；
- database migration down 或 forward-fix；
- checkpoint schema 兼容处理；
- Adapter feature flag；
- worker runtime disabled flag。

如果升级影响 checkpoint 或业务 schema，必须先在 staging 中完成恢复演练。

## 文档同步

下列文件必须在相关变更时同步：

- `docs/DEPENDENCY_EVALUATION.md`；
- `docs/THIRD_PARTY_ARCHITECTURE.md`；
- `docs/LICENSE_INVENTORY.md`；
- `docs/DEPENDENCY_UPDATE_POLICY.md`；
- 相关 ADR；
- `ACCEPTANCE_REPORT.md`。

文档不一致时，以 ADR 为决策依据，以 `LICENSE_INVENTORY.md` 为许可证当前记录，以 lockfile 为实际依赖事实来源。

## Current Implementation Locking

The current implementation uses `pyproject.toml` for direct dependency pins and
`requirements-lock.txt` for reproducible local installation of runtime and dev
dependencies. `requirements.in` points at `.[dev]` so the lock file can be
regenerated from the project metadata.

The lock file was generated from the local Python 3.13 environment because this
host does not have Python 3.12 installed. Before production use, regenerate and
validate the lock file under the selected Python 3.12 baseline.

Direct runtime pins:

- `langgraph==1.2.7`
- `langgraph-checkpoint-postgres==3.1.0`
- `fastapi==0.138.2`
- `pydantic==2.13.4`
- `SQLAlchemy==2.0.51`
- `alembic==1.18.5`
- `psycopg[binary]==3.3.4`
- `uvicorn==0.49.0`
- `httpx==0.28.1`

Dev-only scan and QA tools are pinned in `[project.optional-dependencies].dev`.
