# 第三方许可证清单

核验日期：2026-07-01

说明：本清单不是正式法律意见。结论基于官方 GitHub LICENSE/COPYRIGHT、仓库结构、发布记录和包元数据。所有 MIT/PostgreSQL License 依赖在再分发源码副本、二进制、容器镜像或文档包时都应保留版权和许可证声明。

## 清单

| 项目名称 | 仓库 | 许可证 | 使用方式 | 是否修改源码 | 是否需要保留版权声明 | 是否包含非开源或特殊授权目录 | 当前结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LangGraph | https://github.com/langchain-ai/langgraph | MIT | 第一版生产依赖，作为第一层 workflow/checkpoint/interrupt 底座 | 否 | 是 | 未发现目录级特殊授权 | 可采用，锁定 `langgraph==1.2.7` |
| LangGraph PostgreSQL Checkpoint | https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-postgres | MIT | 第一版生产依赖，保存 checkpoint 到 PostgreSQL | 否 | 是 | 未发现目录级特殊授权 | 可采用，锁定 `langgraph-checkpoint-postgres==3.1.0` |
| OpenAI Agents SDK | https://github.com/openai/openai-agents-python | MIT | 第一版不采用；后续 Worker runtime 候选 | 否 | 是 | 未发现目录级特殊授权 | 暂不引入核心依赖 |
| CrewAI | https://github.com/crewAIInc/crewAI | MIT | 第一版不采用；仅概念参考 | 否 | 是 | 未发现目录级特殊授权 | 不采用，避免与 LangGraph 重叠 |
| MetaGPT | https://github.com/FoundationAgents/MetaGPT | MIT | 第一版不采用；仅参考软件工程角色/SOP | 否 | 是 | 未发现目录级特殊授权 | 不采用，Python 兼容和维护节奏不满足第一版 |
| OpenHands | https://github.com/OpenHands/OpenHands | 根许可证说明：`enterprise/` 以 `enterprise/LICENSE` 单独授权，其余 MIT | 第一版不采用；后续高风险 Coding Worker 候选 | 否 | 是，限 MIT 开源部分 | 是，`enterprise/` 为 PolyForm Free Trial | 后续重评必须排除 `enterprise/` |
| OpenHands Enterprise 目录 | https://github.com/OpenHands/OpenHands/tree/main/enterprise | PolyForm Free Trial License 1.0.0 | 不使用、不复制、不打包 | 否 | 不适用；未获单独授权不得使用、复制或分发 | 是；不允许分发副本，每年超过 30 天使用需商业许可 | 明确排除 |
| Microsoft Agent Framework | https://github.com/microsoft/agent-framework | MIT | 第一版不采用；未来替代底座或 Microsoft/Azure Worker runtime 候选 | 否 | 是 | 未发现目录级特殊授权 | 不采用，避免双编排 |
| FastAPI | https://github.com/fastapi/fastapi | MIT | 第一版生产依赖，外部 API | 否 | 是 | 未发现目录级特殊授权 | 可采用，锁定 `fastapi==0.138.2` |
| Pydantic | https://github.com/pydantic/pydantic | MIT | 第一版生产依赖，内部 DTO、配置和边界校验 | 否 | 是 | 未发现目录级特殊授权 | 可采用，锁定 `pydantic==2.13.4` |
| PostgreSQL | https://github.com/postgres/postgres / https://www.postgresql.org/ | PostgreSQL License | 第一版数据库服务 | 否 | 是 | 未发现特殊商业限制；GitHub 仓库是官方 mirror | 可采用，固定受支持小版本或镜像 digest |

## 许可证要点

### MIT 许可证项目

LangGraph、OpenAI Agents SDK、CrewAI、MetaGPT、Microsoft Agent Framework、FastAPI、Pydantic 的官方许可证均为 MIT 或在包元数据中声明 MIT。MIT 许可证通常允许商业使用、修改、复制、分发、再授权和私有使用。

必须做到：

- 在源码副本、容器镜像、二进制分发、文档包或第三方 notices 中保留版权和许可声明；
- 不移除原始 LICENSE；
- 不暗示原作者为本项目提供担保。

### PostgreSQL License

PostgreSQL License 是宽松许可证，允许使用、复制、修改和分发，但需要保留版权和许可声明。生产使用应优先依赖官方发行版、官方容器镜像或组织内批准的 PostgreSQL 发行渠道。

### OpenHands 特殊边界

OpenHands 根 LICENSE 明确说明：

- `enterprise/` 目录内容使用 `enterprise/LICENSE`；
- 上述限制之外的内容按 MIT 许可。

`enterprise/LICENSE` 是 PolyForm Free Trial License 1.0.0。该许可证不允许分发副本，并限制每个日历年超过 30 天的使用需要商业许可证。

因此第一版和后续任何 OpenHands spike 都必须：

- 不复制 `enterprise/` 目录；
- 不把整个仓库 vendor 到本项目；
- 不从 GitHub `main` 直接作为生产依赖；
- 在依赖扫描中检查源码、构建上下文、容器镜像层和发布包是否意外包含 `enterprise/`；
- 对容器镜像和分发包做 license scan。

## 当前允许的商业使用和修改结论

| 项目 | 是否允许商业使用 | 是否允许修改 | 当前限制 |
| --- | --- | --- | --- |
| LangGraph | 是 | 是 | 保留 MIT 声明；通过 Adapter 使用 |
| OpenAI Agents SDK | 是 | 是 | 保留 MIT 声明；第一版不接入 |
| CrewAI | 是 | 是 | 保留 MIT 声明；第一版不接入 |
| MetaGPT | 是 | 是 | 保留 MIT 声明；第一版不接入 |
| OpenHands 开源部分 | 是 | 是 | 仅限 MIT 部分；排除 `enterprise/` |
| OpenHands enterprise 目录 | 不按 MIT 判断 | 不按 MIT 判断 | 不使用；PolyForm Free Trial 不允许分发副本，超过试用需商业授权 |
| Microsoft Agent Framework | 是 | 是 | 保留 MIT 声明；第一版不接入 |
| FastAPI | 是 | 是 | 保留 MIT 声明 |
| Pydantic | 是 | 是 | 保留 MIT 声明 |
| PostgreSQL | 是 | 是 | 保留 PostgreSQL License 声明 |

## 许可证合规动作

第一版实现前必须加入：

1. `THIRD_PARTY_NOTICES.md` 或等价 notices 生成流程；
2. SBOM 生成，例如 CycloneDX；
3. license scan，覆盖 Python lockfile、Docker image、前端包和 vendored files；
4. CI 检查禁止把 OpenHands `enterprise/` 或其他第三方大仓库复制到本仓库；
5. 依赖升级 PR 中必须包含许可证 diff；
6. 发布包或镜像必须包含第三方许可证清单。

## 范围限制

本清单的“允许商业使用/允许修改”结论只覆盖已核对的直接依赖许可证，不覆盖 transitive dependencies、optional extras、前端资产、容器基础镜像、模型或托管服务条款、商标、专利、出口管制和组织内部采购要求。实现阶段必须用 lockfile、SBOM 和 license scan 重新生成实际依赖清单。

## 官方来源

- LangGraph LICENSE：https://github.com/langchain-ai/langgraph/blob/main/LICENSE
- OpenAI Agents SDK LICENSE：https://github.com/openai/openai-agents-python/blob/main/LICENSE
- CrewAI LICENSE：https://github.com/crewAIInc/crewAI/blob/main/LICENSE
- MetaGPT LICENSE：https://github.com/FoundationAgents/MetaGPT/blob/main/LICENSE
- OpenHands LICENSE：https://github.com/OpenHands/OpenHands/blob/main/LICENSE
- OpenHands enterprise LICENSE：https://github.com/OpenHands/OpenHands/blob/main/enterprise/LICENSE
- Microsoft Agent Framework LICENSE：https://github.com/microsoft/agent-framework/blob/main/LICENSE
- FastAPI LICENSE：https://github.com/fastapi/fastapi/blob/master/LICENSE
- Pydantic LICENSE：https://github.com/pydantic/pydantic/blob/main/LICENSE
- PostgreSQL COPYRIGHT：https://github.com/postgres/postgres/blob/master/COPYRIGHT

## Current Stage Direct Dependency Inventory

This section records the implementation dependencies currently locked in
`pyproject.toml` and `requirements-lock.txt`. It is not legal advice.

| Project | Repository / Package | License | Use | Source modified | Notice required | Special directories | Current conclusion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LangGraph | `langgraph==1.2.7` | MIT | Workflow orchestration and interrupt/resume adapter | No | Preserve upstream license in redistributions | No vendored source | Adopted behind orchestration adapter |
| langgraph-checkpoint-postgres | `langgraph-checkpoint-postgres==3.1.0` | MIT | PostgreSQL checkpoint saver | No | Preserve upstream license in redistributions | No vendored source | Adopted with strict msgpack serializer |
| FastAPI | `fastapi==0.138.2` | MIT | HTTP control/query API | No | Preserve upstream license in redistributions | No vendored source | Adopted |
| Pydantic | `pydantic==2.13.4` | MIT | Internal request/response protocol validation | No | Preserve upstream license in redistributions | No vendored source | Adopted |
| SQLAlchemy | `SQLAlchemy==2.0.51` | MIT | PostgreSQL ORM mapping and repository implementation | No | Preserve upstream license in redistributions | No vendored source | Adopted |
| Alembic | `alembic==1.18.5` | MIT | Database migrations | No | Preserve upstream license in redistributions | No vendored source | Adopted |
| psycopg | `psycopg[binary]==3.3.4` | LGPL-3.0-only with exceptions for package use | PostgreSQL driver and checkpoint connection | No | Preserve upstream license; review binary redistribution policy before packaging | Binary package included by lockfile | Adopted for local/dev, re-review before distributing binaries |
| Uvicorn | `uvicorn==0.49.0` | BSD-3-Clause | Local ASGI server | No | Preserve upstream license in redistributions | No vendored source | Adopted |
| HTTPX | `httpx==0.28.1` | BSD-3-Clause | FastAPI test client dependency path | No | Preserve upstream license in redistributions | No vendored source | Adopted |
| pytest | `pytest==9.1.1` | MIT | Tests only | No | Preserve upstream license in redistributions | Dev dependency only | Adopted for dev/test |
| Ruff | `ruff==0.15.20` | MIT | Formatting and lint only | No | Preserve upstream license in redistributions | Dev dependency only | Adopted for dev/test |
| mypy | `mypy==2.1.0` | MIT | Type checking only | No | Preserve upstream license in redistributions | Dev dependency only | Adopted for dev/test |
| pip-audit | `pip-audit==2.10.1` | Apache-2.0 | Vulnerability scan only | No | Preserve upstream license in redistributions | Dev dependency only | Adopted for dev/test |
| pip-licenses | `pip-licenses==5.5.5` | MIT | License report only | No | Preserve upstream license in redistributions | Dev dependency only | Adopted for dev/test |
| cyclonedx-bom | `cyclonedx-bom==7.3.0` | Apache-2.0 | SBOM generation only | No | Preserve upstream license in redistributions | Dev dependency only | Adopted for dev/test |
| detect-secrets | `detect-secrets==1.5.0` | Apache-2.0 | Secret scanning only | No | Preserve upstream license in redistributions | Dev dependency only | Adopted for dev/test |
