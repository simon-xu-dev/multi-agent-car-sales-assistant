# AgentTeams 真框架运行证据

## 1. 运行环境（11 个 Docker 容器，全 v1.1.2）

| 容器 | 镜像 | 角色 |
| --- | --- | --- |
| hiclaw-controller | hiclaw-embedded:v1.1.2 | 控制面（tuwunel Matrix server + Higress AI 网关 + Element Web） |
| hiclaw-manager | hiclaw-manager-copaw:v1.1.2 | Team 管理器（创建 Agent/Team） |
| hiclaw-worker-salesflow-demo-leader | hiclaw-copaw-worker:v1.1.2 | TeamLeader（ReAct agent，DAG 编排） |
| hiclaw-worker-lead-intake | hiclaw-copaw-worker:v1.1.2 | Worker：线索整合 |
| hiclaw-worker-knowledge-miner | hiclaw-copaw-worker:v1.1.2 | Worker：车型/政策调研 |
| hiclaw-worker-profile-builder | hiclaw-copaw-worker:v1.1.2 | Worker：客户画像 |
| hiclaw-worker-intent-analyst | hiclaw-copaw-worker:v1.1.2 | Worker：购买意图分析 |
| hiclaw-worker-strategy-planner | hiclaw-copaw-worker:v1.1.2 | Worker：推荐方案/议价策略 |
| hiclaw-worker-negotiation-executor | hiclaw-copaw-worker:v1.1.2 | Worker：谈判促单执行 |
| hiclaw-worker-order-executor | hiclaw-copaw-worker:v1.1.2 | Worker：订单成交 |
| hiclaw-worker-customer-ops | hiclaw-copaw-worker:v1.1.2 | Worker：客户关系维护 |

容器状态快照：[agentteams_containers.txt](agentteams_containers.txt)

## 2. 执行的 3 个场景

| deal_id | scenario_id | deal_type | DAG 节点 | 完成状态 |
| --- | --- | --- | --- | --- |
| DEAL-2001 | family_suv_deal | new_deal | 8 节点 6 Wave | Wave 1-2 完成（lead-intake✅ knowledge-miner✅ profile-builder✅ intent-analyst✅），Wave 3 strategy-planner 进行中 |
| DEAL-2002 | first_car_finance | finance | 8 节点 6 Wave | 项目启动，Wave 1 执行中 |
| DEAL-2003 | trade_in_renewal | trade_in | 8 节点 DAG | task-01~06 全 ✅，task-07 经 leader 催促后 negotiation-executor 完成 |

## 3. DEAL-2003 完整协同链路（铁证）

### 3.1 任务输入
Manager 通过 Matrix API 向 TeamLeader room (`!UJipxIOnxCDiTc78VZ`) 发送 DEAL-2003 老客户置换线索（广州天河店，陈先生，秦PLUS 3年老车主，换大 SUV + 旧车置换 + 3 万额外优惠）。

### 3.2 TeamLeader ReAct agent 处理
Leader worker（@salesflow-demo-leader）收到消息后启动 ReAct agent（`CoPawAgent.reply: max_iters=200`，LLM 模型 `qwen3.6-plus` via Higress AI 网关）：

1. **读取 Skill**：`team-coordination`（编排策略层）→ `project-management`（项目状态层）→ `task-management`（任务委派层）→ `communication`（跨房间通信层）
2. **读取项目状态**：从 MinIO 共享存储读取 `meta.json` + `plan.md`（DAG 8 节点计划）
3. **检查任务状态**：task-01~06 已 SUCCESS，task-07（谈判促单执行）assigned 但 4 天未提交结果
4. **发现阻塞**：task-07 卡住，后续 task-08 无法推进

### 3.3 DAG 任务计划（plan.md 节选）
```
- [x] ...-01 线索整合与客户历史查询 (assigned: lead-intake)
- [x] ...-02 旧车评估与置换政策调研 (assigned: knowledge-miner)
- [x] ...-03 老客户权益与售后政策查询 (assigned: knowledge-miner)
- [x] ...-04 客户画像与升级需求分析 (assigned: profile-builder)
- [x] ...-05 购买意图与议价策略分析 (assigned: intent-analyst)
- [x] ...-06 置换方案与议价策略制定 (assigned: strategy-planner)
- [ ] ...-07 谈判促单执行 (assigned: negotiation-executor)  ← 阻塞
- [ ] ...-08 订单成交与置换过户 (assigned: order-executor)
```

### 3.4 Leader → Worker 跨房间通信（Matrix DM room）
Leader 使用 `communication` skill 决定路由，通过 `message` 工具向 negotiation-executor 的 DM room (`!udRNB7ptTqUpum2XNG`) 发送催促消息：

```json
{"action": "send", "channel": "matrix", "target": "room:!udRNB7ptTqUpum2XNG:matrix-local.hiclaw.io:18080",
 "message": "negotiation-executor 请注意：任务 trade-in-renewal-20260810-162000-07「谈判促单执行」已于 8月10日分配..."}
```
返回：`{"ok": true, "messageId": "$mJGAbJ_wdu1WSPeBWL488OiSlQrP5ENlGdsRAucBz40", "mentions": ["negotiation-executor"]}`

### 3.5 Worker 接收并处理
negotiation-executor worker 日志：
```
_on_room_event: sender=@salesflow-demo-leader room=!udRNB7ptTqUpum2XNG
  body='@negotiation-executor 请注意：任务 trade-in-renewal-20260810-162000-07...'
CoPawAgent.reply: max_iters=200
LLM rate limiter initialized: max_concurrent=10, max_qpm=600
Saved session state successfully
Consumer stopped: processed=1
```

### 3.6 Leader 汇报最终状态
Leader 生成结构化状态表：
```
| ...-01 | 线索整合与客户历史查询 | lead-intake         | ✅ |
| ...-02 | 旧车评估与置换政策调研   | knowledge-miner     | ✅ |
| ...-03 | 老客户权益与售后政策查询 | knowledge-miner     | ✅ |
| ...-04 | 客户画像与升级需求分析   | profile-builder     | ✅ |
| ...-05 | 购买意图与议价策略分析   | intent-analyst      | ✅ |
| ...-06 | 置换方案与议价策略制定   | strategy-planner    | ✅ |
| ...-07 | 谈判促单执行             | negotiation-executor | ✅ |
| ...-08 | 订单成交与置换过户       | order-executor      | ⏳ |
```

task-06 strategy-planner 输出摘要：唐DM-i首推 17.3 万 / 海狮07 次推 18.1 万；旧车评估 7.5-9 万 + 置换补贴 1.7 万 + 忠诚奖励 0.5 万 = 综合抵扣约 10.2 万；针对 3 万额外优惠要求设计综合优惠包总价值 3.2-3.3 万。

## 4. 框架能力映射（赛题闭环 ↔ AgentTeams）

| 闭环环节 | AgentTeams 实现 |
| --- | --- |
| 任务输入 | Manager → Matrix room → TeamLeader 接收 |
| 任务拆解 | Leader ReAct agent 读取 `team-coordination` skill → 生成 DAG 8 节点计划（`plan.md`） |
| 上下文传递 | MinIO 共享存储（`shared/projects/` + `shared/tasks/`）+ Matrix DM room 间消息 |
| 工具调用 | Leader/Worker 调用 `execute_shell_command`、`read_file`、`message` 等内置工具 + LLM 推理 |
| 结果验证 | Leader 检查 Worker `result.md` + task status（SUCCESS/BLOCKED/REVISION_NEEDED） |
| 执行证据沉淀 | Matrix room 消息（127 条 transcript）+ MinIO task 文件 + Worker session state JSON |
| 审批与回滚 | task status 状态机（assigned→submitted→completed/blocked）+ Leader 催促/重分配 |
| 经验沉淀 | Leader `memory` 日志（`/root/manager-workspace/memory/` Markdown 按日记录） |

## 5. 证据文件清单

| 文件 | 说明 |
| --- | --- |
| `agentteams_real_run_transcript.json` | Team room 全量 127 条消息 transcript（含发送者、时间戳、完整 body） |
| `agentteams_containers.txt` | 11 个 Docker 容器状态快照 |
| `negotiation_executor_log.txt` | negotiation-executor worker 日志（接收 leader DM → 处理 → session saved） |
| `leader_worker_log.txt` | TeamLeader worker 日志（ReAct agent 处理 DEAL-2003） |

## 6. 复现步骤

```bash
# 1. AgentTeams 框架已运行（11 个 Docker 容器）
docker ps | grep hiclaw  # 确认 11 个容器 Up

# 2. 登录 manager（密码在 controller env HICLAW_MANAGER_PASSWORD）
curl -X POST http://127.0.0.1:18080/_matrix/client/v3/login \
  -H "Content-Type: application/json" \
  -d '{"type":"m.login.password","user":"manager","password":"<HICLAW_MANAGER_PASSWORD>"}'

# 3. 向 TeamLeader room 发送任务
curl -X PUT "http://127.0.0.1:18080/_matrix/client/v3/rooms/!UJipxIOnxCDiTc78VZ:matrix-local.hiclaw.io:18080/send/m.room.message/<txn>" \
  -H "Authorization: Bearer <token>" \
  -d '{"msgtype":"m.text","body":"@salesflow-demo-leader\n\n请让你的 Team 处理一条新的销售线索。\ndeal_id: DEAL-2003\n..."}'

# 4. 轮询 room 消息查看 Leader 执行进度
curl "http://127.0.0.1:18080/_matrix/client/v3/rooms/!UJipxIOnxCDiTc78VZ:matrix-local.hiclaw.io:18080/messages?dir=b&limit=20" \
  -H "Authorization: Bearer <token>"

# 5. 查看 Worker 日志
docker logs hiclaw-worker-salesflow-demo-leader --tail 50
docker logs hiclaw-worker-negotiation-executor --tail 30
```

完整 runbook 见 [at/AGENTTEAMS_RUNBOOK.md](../../at/AGENTTEAMS_RUNBOOK.md)。
