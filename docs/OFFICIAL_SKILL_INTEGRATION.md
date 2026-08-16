# 官方用云 Skill 集成设计（OSS 证据归档 + 短信审批告警）

> 对应赛题："合理使用阿里云官方用云 Skills，重点说明使用 Skills 过程中在鉴权、编排、端到端体验方面的处理和应对。"

## 1. 选用的官方用云 Skill（2 个）

**① 阿里云 OSS（对象存储）—— evidence-archive Skill**：用于"执行证据沉淀"。成交闭环的 Trace/Log/Metrics 快照需持久化、可审计、可回溯，OSS 是天然承载。本方案以 `evidence-archive` Skill 封装该能力（`skills/evidence-archive/SKILL.md`，第 2-7 节）。

**② 阿里云短信服务（Dysmsapi）—— sms-approval-alert Skill**：用于"审批与回滚"环节的人工触达。L2 风险动作（超授权优惠、征信授权等）触发 `needs_approval` 时，把审批任务短信触达门店经理，缩短"挂起 → 人工决策"时延，避免审批超时按未批准处理。本方案以 `sms-approval-alert` Skill 封装该能力（`skills/sms-approval-alert/SKILL.md`，第 8 节）。

## 2. 鉴权设计
| 层 | 职责 | 实现 |
|---|---|---|
| Worker | 不持有任何云密钥，仅通过工具网关调用 | AgentSpec 中无 AK/SK |
| 网关 | 统一注入租户/门店上下文，按场景路由 | Higress 统一鉴权（API Key）+ 限流 |
| OSS | 最小权限写入 | RAM STS 临时凭证，仅授 `oss:PutObject/GetObject`，按门店 bucket 前缀隔离 |
| 短信 | 最小权限发送 | RAM STS 临时凭证，仅授 `dysmsapi:SendSms`；签名（SignName）与模板（TemplateCode）须先在阿里云短信控制台报备审批通过 |
| 密钥管理 | 凭证隔离原则 | STS 临时凭证短时效，不落盘；网关侧保管 |

## 3. 编排设计
- **能力抽象层**：`evidence-archive` 是 Skill（不是一次性脚本），输入输出契约固定，可被任意 Agent 调用。
- **触发时机**：闭环验收 `check_deal` 完成后，由 TeamLeader 异步扇出，不阻塞主链（与 customer-ops/knowledge-miner 并行）。
- **状态追踪**：归档动作写入 Log（event=evidence_archived，含 object_key/etag），通过 trace_id 与闭环 Trace 关联。

## 4. 端到端体验
```
Worker 执行闭环 → check_deal 验收 → TeamLeader 扇出 archive → OSS put_object(key=.../trace_id/...)
   → deal-memory 检索归档证据 → knowledge-miner 复盘沉淀
```
归档 key 含 trace_id，使"执行→归档→检索→复盘"全链路可串。归档失败不影响成交结果（只追加、可补归）。

## 5. 可替换性 / 迁移成本（P3.2 升级：OSS 真 REST 调用）
当前 demo 用 `make_store()` 工厂自动选择：有 `OSS_ACCESS_KEY_ID/SECRET` 凭证 → `OssObjectStore`（真阿里云 OSS REST，OSS v1 HMAC-SHA1 签名，stdlib hmac/hashlib/base64，**零 oss2 SDK 依赖**）；无凭证 → `LocalObjectStore`（本地目录，接口与 OSS 一致）。
- `store_type` 字段诚实标注 `oss_rest`/`local`，`/archive` 返回 `backend` 描述，不伪装；
- `put_object`/`get_object`/`list_objects` 三方法签名在两实现间一致，Agent/Skill/网关业务代码零改动；
- 迁移 MCP：REST→MCP tool schema（`oss_put`/`oss_get`/`oss_list`）适配，`store_type` 契约不变；
- 配置入口：`.env` 的 `OSS_ACCESS_KEY_ID`/`OSS_ACCESS_KEY_SECRET`/`OSS_ENDPOINT`/`OSS_BUCKET`（见 `.env.example`）。

## 6. 降级与审计
- 降级：无 OSS 凭证时自动回落本地目录归档（`store_type=local`）+ 告警，证据不丢；
- 审计：归档写 Log（含 `store_type`），object_key 可被 `/archives` 端点列出回溯，配合 OTel trace 形成完整审计链。

## 7. 复现命令
```bash
python3 tools/mock_tool_server.py --port 18089 &
# 跑一轮闭环后归档
curl -X POST http://127.0.0.1:18089/tools/family_suv_deal/archive -d '{"deal_id":"DEAL-2001"}'
# 列出归档证据
curl http://127.0.0.1:18089/tools/family_suv_deal/archives
```

## 8. 官方用云 Skill 2：sms-approval-alert（阿里云短信 Dysmsapi）

### 8.1 真集成路径
- **API**：Dysmsapi `SendSms`（2017-05-25）REST，**RPC V1 签名**（AccessKeySecret HMAC-SHA1，stdlib hmac/hashlib/base64，**零 SDK 依赖**），实现见 `tools/sms_alert.py` 的 `AliyunSmsSender`（与 OSS 的 `OssObjectStore` 同构模式）；
- **鉴权**：AK 鉴权（`.env` 的 `SMS_ACCESS_KEY_ID/SECRET/SIGN_NAME/TEMPLATE_CODE`）→ 生产建议 RAM STS 临时凭证（网关侧注入，最小权限 `dysmsapi:SendSms`），Worker 不持有任何云密钥；
- **签名与模板报备**（生产前置条件）：SignName 与 TemplateCode 须先在阿里云短信控制台报备审批通过；模板只含固定变量（approval_id/deal_id/risk_type/summary），不含自由文本，防钓鱼滥用；summary 超长自动截断并标注 `summary_truncated`，不静默丢弃。

### 8.2 降级与诚实标注
- 无短信凭证时 `make_sender()` 工厂自动降级 `LocalSmsSender`：不真发短信，而是把"应发送的短信"结构化落盘为 JSONL 外呼记录（含 approval_id/trace_id/模板参数/回执 Code/BizId），返回与阿里云一致的回执结构，可回放审计；
- `channel_type` 字段诚实区分 `aliyun_sms_rest` / `local_mock`，不伪装（与 OSS `store_type` 同一诚实标注风格）；
- 两实现 `send_sms(phone_numbers, sign_name, template_code, template_param)` 签名一致，Agent/Skill/网关业务代码零改动。

### 8.3 编排与幂等
- **触发时机**：审批门禁产生 `needs_approval` / L2 审批任务后，由 negotiation-executor / order-executor 旁路触发；L1 可逆通知动作，**只触达不决策**（approve/reject 仍必须人工在系统内操作留痕），不阻塞审批主链；
- **幂等**：`alert_key = approval_id`，同一审批单只告警一次，重复调用返回 `{"status":"already_sent","deduplicated":true}`，不二次外呼；
- **审计**：外呼记录 append-only JSONL（`run_evidence_live/*_sms.jsonl`），手机号脱敏展示（`138****0001`），trace_id 关联，可被 evidence-archive 归档、deal-memory 检索，形成"门禁 → 触达 → 决策 → 归档"完整链路。

### 8.4 自测证据与工具口径
- 自测证据：`run_evidence_live/family_suv_deal_sms.jsonl` —— APR-SMS01 → store_manager，`channel_type=local_mock`（无凭证降级，诚实标注），Code=OK / BizId=SMS-…，summary 超长截断标注，trace_id 关联；
- 工具口径：HTTP `mock_sms.send_approval_alert` + MCP `sms_approval_alert`（工具总数 **22→23**，`docs/INTERFACE_CONTRACT.md` 同步 23 函数）；
- Skill 注册：`skills/skill_registry.json` 现为 **13 Skill**（其中 official-cloud-skill 2 个：evidence-archive + sms-approval-alert）。

```bash
python3 tools/mock_tool_server.py --port 18089 &
# L2 审批挂起后触发短信告警（有 SMS 凭证真调 Dysmsapi，无凭证降级本地外呼记录）
curl -X POST http://127.0.0.1:18089/tools/family_suv_deal/mock_sms.send_approval_alert \
  -H 'Content-Type: application/json' \
  -d '{"approval_id":"APR-xxx","deal_id":"DEAL-2001","risk_type":"discount_override","summary":"优惠超授权等待审批","approver":"store_manager"}'
```

### 8.5 可替换性 / 迁移成本
- 迁移 MCP：REST → MCP tool schema（`sms.approval.alert`）适配，`channel_type` 契约不变；
- 替换其他触达通道（企微/钉钉/电话）：仅替换 Sender 实现（`SmsSender` Protocol 接口），Skill 契约与幂等规范不变；
- 复用价值："高风险动作审批触达"是运维变更、财务付款、安全处置等企业级 Agent 闭环的通用需求，alert_key 幂等规范 + 本地/阿里云等价适配可独立开源复用。
