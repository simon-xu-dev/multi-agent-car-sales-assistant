# 运行证据索引（EVIDENCE）

> 面向评审：本文件汇总 CarSales agentteams-demo 的可复现运行证据。所有证据均可在本地 3 步内复现。

## 1. 运行环境

- 操作系统：macOS（Darwin）/ Linux 均可（纯 Python 3 标准库，无第三方依赖）。
- 运行入口：`python3 tools/mock_tool_server.py --host 0.0.0.0 --port 18089`（HTTP mock 工具网关）。
- 自检入口：`python3 tools/selfcheck.py`（离线自检，无需启动网关）。
- AgentTeams 完整运行手册：见 `at/AGENTTEAMS_RUNBOOK.md`（含 Docker/Element Web 逐步指引）。

## 2. 核心证据清单

| # | 证据 | 文件 / 复现命令 | 结论 |
|---|---|---|---|
| E1 | 工程自检报告（3 场景 × 36 项断言） | `docs/selfcheck_report.txt`（`python3 tools/selfcheck.py` 生成） | **36/36 通过（36 passed, 0 failed）** |
| E2 | 多渠道会话归并 | selfcheck 断言：官网+企微+电话 3 条会话归并为 1 条线索 | 通过 |
| E3 | 报价计算正确性 | selfcheck 断言：`round(329800 - 329800*0.008 - 8000, 2)` 与政策一致 | 通过 |
| E4 | 低风险自动执行（L1） | selfcheck 断言：试驾预约自动成功、标准报价自动输出 | 通过 |
| E5 | 高风险审批门禁（L2） | selfcheck 断言：超授权优惠生成 discount_override 审批任务，订单仅草稿 | 通过 |
| E6 | 订单幂等与回滚 | selfcheck 断言：order_key 幂等、审批驳回回滚到 draft | 通过 |
| E7 | 议价底线守护 | selfcheck 断言：触底停止让步、输出转人工交接单、重复大额让步不放行 | 通过 |
| E8 | RAG 案例沉淀与检索 | selfcheck 断言：成交案例脱敏入库并可检索召回 | 通过 |
| E9 | 全链路 Trace 留痕 | selfcheck 断言：单场景 Trace ≥ 10 条；运行期可用 `curl http://127.0.0.1:18089/tools/family_suv_deal/tools/trace` 查看 | 通过 |
| E10 | AgentTeams 编排材料 | `at/team_spec.json`（8 Worker + TeamLeader + 10 步 workflow + 风险策略）、`at/create_agents_messages.md`、`at/run_demo_task_message.md` | 齐备 |
| E11 | 治理材料 | `at/nacos_registry_mock.json`（Prompt/Skill/AgentSpec/Team 注册 + FORMAL 门禁 + 审计策略） | 齐备 |

## 3. 复现步骤（3 步）

```bash
# 1. 离线自检（无需任何外部依赖）
python3 tools/selfcheck.py

# 2. 启动工具网关并探活
python3 tools/mock_tool_server.py --host 0.0.0.0 --port 18089 &
curl http://127.0.0.1:18089/health

# 3. 查看场景全量 Trace（网关运行时）
curl http://127.0.0.1:18089/tools/family_suv_deal/tools/trace
```

## 4. 三个 Demo 场景与期望信号

| 场景 | deal_id | 核心验证点 |
|---|---|---|
| `scenarios/family_suv_deal.json` | DEAL-2001 | 3 渠道归并 → 二胎家庭画像 → 车型对比 → 试驾 L1 + 报价 L1 → 超授权优惠 L2 审批 → 订单草稿 → check_deal |
| `scenarios/first_car_finance.json` | DEAL-2002 | 首购画像 → 月供敏感 → 2 组金融方案对比 → 征信授权 L2 审批门禁 → 合规边界说明 |
| `scenarios/trade_in_renewal.json` | DEAL-2003 | 3 年车主记忆召回 → 置换方案 → 议价触底转人工交接单 → 售后模板触达 → 案例脱敏入库 |

期望信号明细见 `at/AGENTTEAMS_RUNBOOK.md` 第 7 节「判断是否跑通」。

## 5. AgentTeams 真实运行证据（3 场景全链路闭环）

> 以下证据来自 AgentTeams 平台实际调度 8 个 Worker + TeamLeader 的完整运行记录。
> Mock 工具网关容器 IP 172.18.0.4:18089，Worker 通过容器网络访问。

### 5.1 运行汇总

| DEAL | 场景 | 工具调用数 | 覆盖工具数 | Trace 文件 |
|------|------|-----------|-----------|-----------|
| DEAL-2001 | family_suv_deal（二胎家庭 SUV 全链路成交） | **33** | 12 | `RUN_EVIDENCE/DEAL-2001_trace.json` |
| DEAL-2002 | first_car_finance（首购客户金融方案） | **24** | 11 | `RUN_EVIDENCE/DEAL-2002_trace_full.json` |
| DEAL-2003 | trade_in_renewal（老客户置换与售后运营） | **22** | 11 | `RUN_EVIDENCE/DEAL-2003_trace.json` |
| **合计** | — | **79** | **12** | — |

### 5.2 各场景工具调用明细

**DEAL-2001（family_suv_deal）— 33 次调用**
```
mock_crm.get_lead: 6          mock_knowledge.search_product: 3
mock_knowledge.search_sop: 5  mock_knowledge.search_case: 3
mock_price.calc_quote: 5      mock_inventory.check_stock: 3
mock_price.get_policy: 2      mock_finance.calc_plan: 2
mock_crm.list_sessions: 1     mock_crm.get_customer_history: 1
mock_inventory.list_models: 1 mock_testdrive.list_slots: 1
```
覆盖全链路：线索归并 → 画像构建 → 意图分析 → 策略规划 → 报价 → 金融方案 → 试驾预约

**DEAL-2002（first_car_finance）— 24 次调用**
```
mock_price.calc_quote: 6      mock_knowledge.search_case: 2
mock_crm.get_lead: 5          mock_price.get_policy: 2
mock_inventory.check_stock: 3 mock_crm.list_sessions: 1
mock_knowledge.search_product: 1 mock_crm.get_customer_history: 1
mock_knowledge.search_sop: 1  mock_inventory.list_models: 1
mock_finance.calc_plan: 1
```
覆盖：首购画像 → 金融方案对比（6 次报价计算）→ 征信授权 → 合规边界

**DEAL-2003（trade_in_renewal）— 22 次调用**
```
mock_crm.get_lead: 5          mock_price.calc_quote: 3
mock_knowledge.search_case: 3 mock_price.get_policy: 2
mock_inventory.check_stock: 2 mock_crm.list_sessions: 1
mock_wechat.get_session: 1    mock_knowledge.search_sop: 1
mock_knowledge.search_product: 1 mock_crm.get_customer_history: 1
mock_inventory.list_models: 1 mock_finance.calc_plan: 1
```
覆盖：老客户记忆召回 → 置换评估 → 议价触底 → 售后触达 → 案例入库

### 5.3 关键验证点达成

| 验证点 | DEAL | 证据 |
|--------|------|------|
| 多渠道会话归并（3 渠道 → 1 线索） | DEAL-2001 | `mock_crm.list_sessions` + `mock_crm.get_lead` 调用链 |
| 结构化画像 + 置信度 | DEAL-2001/2002/2003 | 各场景 `mock_crm.get_customer_history` + `mock_knowledge.search_case` |
| 意向评分与分级 | DEAL-2002 | intent-analyst 输出 P1 评分 7，BANT 3.5/4 |
| 金融方案对比 | DEAL-2002 | `mock_price.calc_quote` × 6 + `mock_finance.calc_plan` |
| 报价政策合规 | DEAL-2001/2002/2003 | `mock_price.get_policy` + `mock_price.calc_quote` 调用链 |
| 置换评估与议价底线 | DEAL-2003 | `mock_wechat.get_session`（老客户回访）+ 触底转人工 |
| 全链路 Trace ≥ 10 条 | 3 场景均满足 | 33 / 24 / 22 条 |

## 6. 边界声明（诚实披露）

- 初赛交付为 **mock 环境下的任务级自主闭环**：工具网关为 HTTP mock 适配器（MCP 等价契约见 `tools/MCP_MAPPING.md`），非真实 CRM/DMS/金融系统。
- 复赛计划按 `docs/方案详述.md` 附录 F 推进真实系统接入与 AgentTeams 实际部署演示。
- 本次运行中 DEAL-2002 曾遇到 Leader 队列 idle 清理导致 Wave 3 未自动派发，通过手动唤醒消息恢复，说明 Leader 的 LLM 推理超时（900s）仍需优化。
