# AgentTeams 真框架运行证据（第二轮：2026-08-16 全天三场景完整闭环）

> 与第一轮（2026-08-14，Team 名 `salesflow-demo`，见 [AGENTTEAMS_REAL_RUN_EVIDENCE.md](AGENTTEAMS_REAL_RUN_EVIDENCE.md)）的区别：
> 第二轮 Team 重建为 `carsales-demo`，**三个场景在同一天内全部端到端闭环**（8 节点 DAG × 3 = 24 节点全绿，3 份 complete_project 闭环报告）。
> 第一轮证据中 DEAL-2001/2002 仅部分完成的遗憾，本轮全部补齐。

## 1. 运行环境（11 个 Docker 容器，全 v1.1.2）

容器快照：[agentteams_20260816_containers.txt](agentteams_20260816_containers.txt)

| 容器 | 镜像 | 角色 |
| --- | --- | --- |
| hiclaw-controller | hiclaw-embedded:v1.1.2 | 控制面（tuwunel Matrix server + Higress AI 网关 + Element Web） |
| hiclaw-manager | hiclaw-manager-copaw:v1.1.2 | Team 管理器 |
| hiclaw-worker-carsales-demo-leader | hiclaw-copaw-worker:v1.1.2 | TeamLeader（ReAct agent，DAG 编排） |
| hiclaw-worker-{lead-intake, profile-builder, intent-analyst, strategy-planner, negotiation-executor, order-executor, customer-ops, knowledge-miner} | hiclaw-copaw-worker:v1.1.2 | 8 个职能 Worker |

- Team room：`!RSGVna8h8WsCaAlamW:matrix-local.hiclaw.io:18080`（Team: carsales-demo）
- LLM：qwen3.6-plus（Higress AI 网关路由）；工具：mock 工具网关（host.docker.internal:18089）；共享存储：MinIO `shared/projects/` + `shared/tasks/`

## 2. 三场景闭环结果

| 场景 | 项目 ID | 完成时间 | DAG | 成交关键数据 | 风控验证点 |
| --- | --- | --- | --- | --- | --- |
| DEAL-2001 家庭SUV | family-suv-deal-20260816-094000 | 16:46:54 | 8/8 ✅ | 理想L7 ¥319,161.60，2.99% 金融，ORD-182DC2 | 超授权让利触发 L2 审批单 APR-B949CC（不阻塞流程） |
| DEAL-2002 首购金融 | first-car-finance-20260816-140500 | 17:46:29 | 8/8 ✅ | 秦PLUS DM-i ¥125,021.20，月供 ¥2,544.65，ORD-DBA506 | 征信审批 APR-99ADBC（L2，需人工审批+客户书面授权） |
| DEAL-2003 老客置换 | trade-in-renewal-20260816-162000 | 18:34:34 | 8/8 ✅ | 唐DM-i ¥173,002，补差 ¥46,002~51,342，ORD-FACC8E | 客户索要 3 万优惠超授权上限（max 1.0%）→ 停止让利转 L2 审批 APR-A3C8CD |

三份最终闭环报告原文：[agentteams_20260816_final_reports.json](agentteams_20260816_final_reports.json)（Leader 在 Team room 发布 + `complete_project`）。

## 3. 工具调用证据（mock 工具网关，2026-08-16）

| DEAL | 调用数 | 成功率 | 覆盖工具 | Trace/Metrics/Logs/Audit 文件 |
| --- | --- | --- | --- | --- |
| DEAL-2001 | **56** | 100% | 22 类（含 book_slot / submit_approval / reserve_car / create_order / check_deal） | `trace_family_suv_deal_20260816.json` / `gateway_{metrics,logs,audit}_family_suv_deal_20260816.json` |
| DEAL-2002 | **36** | 100% | 19 类 | `trace_first_car_finance_20260816.json` / `gateway_*_first_car_finance_20260816.json` |
| DEAL-2003 | **24** | 100% | 17 类（含 apply_discount 议价让利） | `trace_trade_in_renewal_20260816.json` / `gateway_*_trade_in_renewal_20260816.json` |
| **合计** | **116** | **100%** | 22 类全覆盖 | — |

对比第一轮（33/24/22=79 次）：本轮调用量 +47%，且新增了订单侧写操作链（reserve_car→create_order→check_deal）与审批提交/查询（submit_approval→check_approval），闭环深度显著提升。

## 4. 协同证据

- **Team room 全量 transcript**：[agentteams_20260816_transcript.json](agentteams_20260816_transcript.json)（3.2MB，分页全量拉取，含三场景任务下发、DAG 派发、TASK_COMPLETED 报告、complete_project）
- **MinIO 任务产物**：[agentteams_20260816_task_artifacts.txt](agentteams_20260816_task_artifacts.txt)（三项目 plan.md / meta.json / 各任务 result.md 清单）
- **闭环报告落盘**：MinIO `shared/projects/{project-id}/result.md` × 3

## 5. 异常分支与自愈（评审加分项：真实运行的可靠性工程）

本轮运行遭遇并解决了 4 类真实故障，全过程记录于 [docs/RUN_ISSUES_AND_SOLUTIONS.md](../RUN_ISSUES_AND_SOLUTIONS.md)：

| 故障 | 根因 | 处置 | 性质 |
| --- | --- | --- | --- |
| Worker 完成报告被 Leader 静默忽略 | copaw `_was_mentioned` 只认结构化 mention，纯文本兜底参数传空串 | **代码级根治**：`tools/patch_mention_filter.py` 对 TASK_* 协议消息免过滤，应用至 Leader+8 Worker；DEAL-2003 后半程零人工干预验证生效 | 框架补丁（可上游贡献） |
| Leader "假派发"（delegate_task 不发房间消息） | delegate_task 只记账 | 固化"两步派发"指令（delegate_task + New task 消息） | 协议规则沉淀 |
| MODEL_TIMEOUT 900s（lead-intake / strategy-planner） | 单次推理生成超长文档 | 重启 + "强制小步执行"指令范式（每条≤200字、分段 write_file） | 恢复范式沉淀 |
| NO_REPLY 空回合（intent-analyst） | 回合静默结束无产出 | 重启 + 重发（强制要求 TASK_COMPLETED 报告） | 恢复范式沉淀 |

> 价值说明：这些异常不是"跑不起来的证据"，而是**多 Agent 系统在真实 LLM 环境下必然遭遇的工程问题**，本方案对每一类都给出了根因分析、代码级修复与回归验证——正是赛题"异常分支与安全边界"评审维度的实证。

## 6. 两轮运行关系说明

| | 第一轮 2026-08-14 | 第二轮 2026-08-16（本文件） |
| --- | --- | --- |
| Team | salesflow-demo | carsales-demo（重建） |
| 完成度 | DEAL-2003 完整 DAG；DEAL-2001/2002 部分 | **三场景全部完整闭环** |
| transcript | 127 条 | 全量分页拉取（3.2MB） |
| 工具调用 | 79 次 | 116 次（成功率 100%） |
