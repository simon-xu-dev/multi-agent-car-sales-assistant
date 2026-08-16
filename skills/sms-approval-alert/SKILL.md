# sms-approval-alert（审批告警短信 Skill）

> 类型：**官方用云 Skill 封装**（阿里云短信服务 Dysmsapi）。封装赛题"审批与回滚"环节的人工触达能力：L2 风险动作（超授权优惠、征信授权等）触发 `needs_approval` 时，把审批任务短信触达人工审批者，缩短"挂起 → 人工决策"时延。

## 使用场景
negotiation-executor / order-executor 的审批门禁返回 `needs_approval`（或 `submit_approval` 创建 L2 审批任务）后，异步向门店经理发送审批告警短信（附审批单号与摘要），避免审批超时按未批准处理（闭环第 7 环"审批与回滚"的人工触达前置）。

## 输入参数
| 参数 | 说明 |
|---|---|
| scenario_id | 场景标识（网关路由注入） |
| approval_id | 审批单号（同时作为幂等键 alert_key） |
| deal_id | 成交/任务标识（短信模板变量，可回执对账） |
| risk_type | 审批类型（如 discount_override / credit_authorization） |
| summary | 审批摘要（模板变量，超 20 字自动截断并标注） |
| approver | 审批者角色（store_manager / finance_manager，通讯录解析手机号） |

## 输出结果
```json
{"status":"sent","skill":"sms-approval-alert","approval_id":"APR-XXX","alert_key":"APR-XXX","approver":"store_manager","channel_type":"aliyun_sms_rest|local_mock","backend":"...","biz_id":"SMS-...","risk_level":"L1"}
```
重复告警返回 `{"status":"already_sent","deduplicated":true,...}`（不二次外呼）；channel_type 诚实区分真发 / 本地降级，不伪装。

## 调用条件
审批门禁产生 `needs_approval` / L2 审批任务后触发；每次审批单只告警一次（幂等），不阻塞审批主链（旁路通知）。

## 依赖工具/系统
阿里云短信服务（Dysmsapi SendSms，需控制台报备签名与模板）。当前 demo 用 `LocalSmsSender`（外呼记录 JSONL 落盘，接口与阿里云一致）作为等价实现，生产环境有 `SMS_ACCESS_KEY_ID/SECRET` 凭证自动切 `AliyunSmsSender` 真调 REST（见 `tools/sms_alert.py` 的 `make_sender()`），Agent/Skill/网关代码零改动。

## 失败处理
- 发送失败重试 1 次后告警，本地保留外呼草稿记录供人工补发；告警失败不阻塞审批主链（审批任务本身仍可经网关 /audit 查询）；
- 审批人无绑定手机号：显式报错转人工处理，不猜测号码；
- 模板变量超长：截断并标注 `summary_truncated`，不静默丢弃。

## 权限与安全
- 鉴权：网关侧统一注入租户/门店上下文，Worker 不持有任何云密钥；生产由 Higress 统一鉴权 + RAM STS 临时凭证（最小权限：`dysmsapi:SendSms`）；
- 签名与模板须先经阿里云短信平台审批通过，内容固定模板变量（不含自由文本），防钓鱼滥用；
- 审批人手机号在日志/结果中脱敏展示（`138****0001`），外呼记录 append-only 落盘可审计；
- 风险边界：L1 可逆通知动作，只触达不决策（approve/reject 仍必须人工在系统内操作留痕）。

## 复用价值
"高风险动作审批触达"是所有企业级 Agent 闭环（运维变更审批、财务付款审批、安全事件处置确认）的通用需求。本 Skill 的 alert_key 幂等规范与本地/阿里云短信等价适配可独立开源复用。

## 与多 Agent 协同流程的关系
由 negotiation-executor / order-executor 在审批门禁挂起时调用（AgentTeams Worker 经工具网关触发）；外呼记录含 trace_id/approval_id，可被 evidence-archive 归档、deal-memory 检索，形成"门禁 → 触达 → 决策 → 归档"完整链路。
