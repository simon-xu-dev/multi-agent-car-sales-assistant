# evidence-archive（证据归档 Skill）

> 类型：**官方用云 Skill 封装**（阿里云 OSS 对象存储）。封装赛题"执行证据沉淀"能力，作为 Skill 能力抽象层。

## 使用场景
任意 Agent 闭环完成 `check_deal` / 结果验证后，异步把本次运行的 Trace+Log+Metrics 快照归档到对象存储，形成可审计、可回放、可被 deal-memory 检索的执行证据（闭环第 6-8 环）。

## 输入参数
| 参数 | 说明 |
|---|---|
| scenario_id | 场景标识 |
| deal_id | 成交/任务标识 |
| trace_id | 全链路 trace_id（贯穿 Agent→Skill→Tool） |
| trace | OTel-GenAI 风格 span 列表 |
| logs | 结构化 Log 列表（决策/审批/失败） |
| metrics | Metrics 字典（调用数/成功率/时延） |

## 输出结果
```json
{"status":"archived","skill":"evidence-archive","object_key":"evidence/<sid>/<deal>/<trace_id>/<ts>.json","etag":"<md5>","size_bytes":N}
```
object_key 含 trace_id，可被审计/回溯/检索。

## 调用条件
闭环验收（check_deal）完成后、由 TeamLeader 异步扇出；不阻塞主链。

## 依赖工具/系统
阿里云 OSS（对象存储）。当前 demo 用 `LocalObjectStore`（本地目录，接口与 oss2 一致）作为等价实现，生产环境切 `OssObjectStore`（见 `tools/evidence_archive.py` 末注释），Agent/Skill/网关代码零改动。

## 失败处理
- 归档失败重试 1 次后告警，证据保留本地草稿供人工补归；
- 归档为只追加（append-only）动作，失败不影响已完成的成交闭环。

## 权限与安全
- 鉴权：网关侧统一注入租户/门店上下文，密钥不暴露给 Worker；生产由 Higress 统一鉴权 + RAM STS 临时凭证（最小权限：oss:PutObject/GetObject）；
- 归档内容含敏感决策日志需按门店隔离 bucket 前缀，访问留痕审计；
- 风险边界：L0 只追加写入，不修改/删除既有证据。

## 复用价值
"执行证据沉淀"是所有企业级 Agent 闭环（运维/客服/金融/研发）的通用需求。本 Skill 的 object_key 规范（含 trace_id）与本地/OSS 等价适配可独立开源复用。

## 与多 Agent 协同流程的关系
由 TeamLeader 在主链完成后异步扇出；knowledge-miner 可检索归档证据用于案例复盘（闭环第 8 环经验沉淀）。
