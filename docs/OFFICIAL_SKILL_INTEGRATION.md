# 官方用云 Skill 集成设计（OSS 证据归档）

> 对应赛题："合理使用阿里云官方用云 Skills，重点说明使用 Skills 过程中在鉴权、编排、端到端体验方面的处理和应对。"

## 1. 选用的官方用云 Skill
**阿里云 OSS（对象存储）** —— 用于"执行证据沉淀"。成交闭环的 Trace/Log/Metrics 快照需持久化、可审计、可回溯，OSS 是天然承载。本方案以 `evidence-archive` Skill 封装该能力（`skills/evidence-archive/SKILL.md`）。

## 2. 鉴权设计
| 层 | 职责 | 实现 |
|---|---|---|
| Worker | 不持有任何云密钥，仅通过工具网关调用 | AgentSpec 中无 AK/SK |
| 网关 | 统一注入租户/门店上下文，按场景路由 | Higress 统一鉴权（API Key）+ 限流 |
| OSS | 最小权限写入 | RAM STS 临时凭证，仅授 `oss:PutObject/GetObject`，按门店 bucket 前缀隔离 |
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
