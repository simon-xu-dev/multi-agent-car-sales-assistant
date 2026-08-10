# 使用 AgentTeams 运行 CarSales Demo

这份手册面向第一次试运行 demo 的参赛者。运行机器可以是本地 Mac、Linux 服务器或云主机；mock 工具网关和 AgentTeams 都部署在同一台机器上。

核心流程：

1. 启动 HTTP mock 工具网关。
2. 安装 AgentTeams，并按安装器引导完成 LLM 配置。
3. 找到 Docker Worker 可访问的工具网关地址。
4. 在 `manager` 房间创建 8 个业务 Worker，并在创建 Team 时生成独立 TeamLeader Worker。
5. 在 Matrix 会话列表中进入名称以 `Team` 开头的 Team 房间，通过 `@<team_leader_name>` 分别发送三个销售任务。

## 1. 准备运行机器

需要：

- Docker 或兼容运行时。
- Python 3。
- 一个 AgentTeams 可使用的 LLM API Key。

检查：

```bash
python3 --version
docker --version
```

如果没有 Docker，按系统查看官方安装文档：

| 系统 | 官方安装入口 |
| --- | --- |
| Mac | https://docs.docker.com/desktop/setup/install/mac-install/ |
| Ubuntu | https://docs.docker.com/engine/install/ubuntu/ |
| Debian | https://docs.docker.com/engine/install/debian/ |
| CentOS | https://docs.docker.com/engine/install/centos/ |
| RHEL | https://docs.docker.com/engine/install/rhel/ |
| 其他 Linux | https://docs.docker.com/engine/install/ |
| Linux 免 sudo 后置配置 | https://docs.docker.com/engine/install/linux-postinstall/ |

安装完成后验证：

```bash
docker run hello-world
```

## 2. 启动 Mock 工具网关

在一个终端中启动服务，并保持它运行：

```bash
cd <DEMO_DIR>
python3 tools/mock_tool_server.py --host 0.0.0.0 --port 18089
```

另开一个终端验证：

```bash
curl http://127.0.0.1:18089/health
curl http://127.0.0.1:18089/scenarios
curl -X POST http://127.0.0.1:18089/tools/family_suv_deal/mock_crm.list_sessions \
  -H 'Content-Type: application/json' \
  -d '{}'
```

这一步只验证宿主机本机访问。后面还需要验证 Docker 容器访问。

## 3. 安装 AgentTeams

执行安装脚本：

```bash
bash <(curl -sSL https://higress.ai/hiclaw/install.sh)
```

安装器会引导完成语言、安装模式、版本、LLM、API Key、API 联通性测试、Embedding、Manager/Worker 运行时、端口、域名、E2EE、Docker API 安全代理和共享目录等配置。按引导操作即可，关键是看到模型 API 联通性测试通过。

可参考的 demo 样例：

| 引导项 | 样例值 |
| --- | --- |
| 语言 | 中文 |
| 版本 | 最新稳定版，例如 `v1.1.2` |
| LLM | 使用已有 API Key 的模型服务，例如 `qwen3.7-plus` |
| API 联通性 | 必须测试通过 |
| Embedding | 可启用；失败后接受自动禁用也可以 |
| Manager/Worker 运行时 | `qwenpow`（`copow`/`QwenPaw`） |
| Element Web 端口 | 默认 `18088` |
| Matrix E2EE | 建议禁用 |
| Docker API 安全代理 | 建议启用 |
| 共享主机目录 | 可保持默认；本 demo 不依赖共享目录读取文件 |

安装完成后检查：

```bash
docker ps | grep hiclaw
```

打开 Element Web：

```text
http://<AGENTTEAMS_HOST>:18088
```

在运行机器本机访问时通常是：

```text
http://127.0.0.1:18088
```

安装配置通常保存到当前用户 HOME 下的 `hiclaw-manager.env`，后续需要调整模型或端口时从这里排查。

## 4. 确定工具网关地址

Worker 在 Docker 容器中运行，不能直接使用 `http://127.0.0.1:18089` 访问宿主机上的 mock 工具网关。单机 Docker 部署优先使用 `hiclaw-manager` 所在网络的 gateway 地址。

先找到 manager 容器名：

```bash
docker ps --format '{{.Names}}' | grep manager
```

如果容器名是 `hiclaw-manager`，查看 gateway：

```bash
docker inspect -f '{{range .NetworkSettings.Networks}}{{println .Gateway}}{{end}}' hiclaw-manager
```

假设输出是 `172.18.0.1`，则 `<MOCK_TOOL_BASE_URL>` 使用：

```text
http://172.18.0.1:18089
```

从容器内验证：

```bash
docker exec -it hiclaw-manager curl http://172.18.0.1:18089/health
```

如果这条命令返回 `{"ok": true, ...}`，说明后续 Worker 可以访问工具网关。

`host.docker.internal` 只在部分 Docker Desktop 环境可用。如果容器里报 `Could not resolve host: host.docker.internal`，就使用上面的 gateway 地址。

## 5. 创建 Agent 和 Team

进入 Element Web 的 `manager` 房间。

打开 [create_agents_messages.md](create_agents_messages.md)，先把文件中的 `<MOCK_TOOL_BASE_URL>` 全部替换为第 4 步确认的地址，例如：

```text
http://172.18.0.1:18089
```

然后将 [create_agents_messages.md](create_agents_messages.md) 中"复制到 Manager 的完整创建请求"整段发送给 `manager`。这段请求已经包含 8 个业务 Worker 和 1 个 Team 的完整定义，并明确要求：

1. 所有 Worker 使用 `qwenpow`（`copow`/`QwenPaw`）运行时。
2. `manager` 必须逐个创建 Worker，不能并行创建。
3. 必须确认前一个 Worker 创建成功且正常运行后，再创建下一个 Worker。
4. 创建 Team 时必须生成新的独立 Worker `carsales-demo-leader` 作为 TeamLeader，不能把 8 个业务 Worker 中的任何一个直接指定为 leader。

Worker 初始化会拉起运行时并写入依赖，低规格机器上并发创建可能造成高 I/O 消耗甚至阻塞。因此不要手动把 Worker 创建任务拆开并并行发送。

注意：

- `manager` 只负责创建和管理。
- 销售任务后续发给 Matrix 会话列表中名称以 `Team` 开头的 Team 房间，并在消息里 `@<team_leader_name>`，不发给 `manager`。
- 8 个业务 Worker 的 AgentSpec、Skill 和工具契约已经内联在创建消息中。
- Worker 不需要读取宿主机上的 `agents/...` 或 `skills/*/SKILL.md` 文件。
- `skills/*/SKILL.md` 主要用于评审、PPT/文档追溯和后续 Registry 替换。

## 6. 发送销售任务

打开 [run_demo_task_message.md](run_demo_task_message.md)。

在 Element Web/Matrix 会话列表中找到名称以 `Team` 开头、对应 `carsales-demo` 的 Team 房间。通常 `manager` 在创建完成摘要里会告诉你 Team 房间名称和 `team_leader_name`。

进入 Team 房间后，在输入框先输入并选中 leader mention：

```text
@<team_leader_name>
```

然后把第一个销售任务复制到这条 @ 消息里发送。必须逐个任务发送：等 `DEAL-2001` 报告完整输出后，再用同样方式 `@<team_leader_name>` 并发送第二个销售消息。不要同时发送多个任务，避免 Team 并发调度时上下文和工具状态互相干扰。

如果你只看到 `manager` 房间，可以先问：

```text
carsales-demo 对应的 Team 房间在哪里？请告诉我 Matrix 会话列表中名称以 Team 开头的房间名称，以及需要 @ 的 team_leader_name。
```

任务消息只包含客户咨询、deal_id 和 scenario_id。车型目录、库存、政策、知识库、试驾档期应由 Agent 通过 HTTP 工具网关主动查询。

## 7. 判断是否跑通

`DEAL-2001 / family_suv_deal` 应包含：

| 检查项 | 期望信号 |
| --- | --- |
| 线索归并 | 官网 + 企微 + 电话 3 条会话归并为 1 条线索 |
| 画像 | 二胎家庭、预算 25-28 万、六座/安全偏好，置信度与证据引用 |
| 推荐 | 理想 L7 / 问界 M7 对比矩阵，库存可用 |
| 低风险自动 | 试驾预约成功（L1）、标准报价（L1） |
| 高风险审批 | 超 1% 授权优惠生成 L2 审批任务、订单草稿（L2） |
| 闭环验证 | check_deal 输出 pending_approval + 执行证据汇总 |

`DEAL-2002 / first_car_finance` 应包含：

| 检查项 | 期望信号 |
| --- | --- |
| 画像 | 首购、预算 12-15 万、月供敏感 |
| 金融方案 | 2 组对比（厂家低息 2.99% vs 银行 3.99%），月供可复算 |
| 审批 | 征信授权生成 L2 审批任务，审批前订单仅草稿 |
| 合规 | 征信数据边界说明 |

`DEAL-2003 / trade_in_renewal` 应包含：

| 检查项 | 期望信号 |
| --- | --- |
| 历史画像 | 3 年车主记忆召回（购车/保养/续保/活动） |
| 置换方案 | 旧车评估 9.8 万 + 置换补贴 1.2 万 |
| 议价底线 | 3 万额外优惠超授权且触及底线 -> 停止让步，输出转人工交接单 |
| 售后 | 权益模板消息已发送（L1），复购线索状态更新 |
| 沉淀 | 案例脱敏入库 |

如果团队要求你人工提供完整车型、库存、政策或历史记录，可以提醒：

```text
请通过已配置的 HTTP mock 工具网关主动查询，不要让我人工收集完整证据。
```

## 8. 查看运行证据（可观测）

工具网关记录了全量工具调用 Trace，可用于评审与回放：

```bash
curl http://127.0.0.1:18089/tools/family_suv_deal/tools/trace
```

每个场景独立状态，重置后重新演示：

```bash
curl -X POST http://127.0.0.1:18089/tools/family_suv_deal/reset -H 'Content-Type: application/json' -d '{}'
```

## 后续替换点

| 当前内容 | 后续替换方向 |
| --- | --- |
| HTTP mock 工具网关 | 真实 MCP Server 或 Higress MCP 代理（映射见 `tools/MCP_MAPPING.md`） |
| `scenarios/*.json` | 真实 CRM、DMS、价格系统、金融审批、知识库数据源 |
| `at/create_agents_messages.md` 中 8 个业务 Worker 的内联 AgentSpec/Skill | Nacos AI Registry 中的 Prompt、Skill、AgentSpec、AgentTeam Spec |
| `skills/*/SKILL.md` 评审材料 | 发布到 Nacos AI Registry 或 AgentTeams Skill Registry，由 Worker 按版本/标签动态加载 |
| mock 知识库检索 | PolarDB for PostgreSQL + pgvector 向量库实现 RAG |
| 工具网关 Trace | LoongSuite / AgentScope Studio / AgentLoop 全链路可观测与评估 |
