# 三场景运行问题总结与解决方案

> 运行环境：本地 macOS Docker + AgentTeams（HiClaw）+ copaw Worker + Matrix 通信 + MinIO 共享存储
> 运行日期：2026-08-16，三个场景全部闭环（DEAL-2001 / DEAL-2002 / DEAL-2003）

## 一、运行结果总览

| 场景 | 项目 ID | 结果 | 关键风控验证点 |
|---|---|---|---|
| DEAL-2001 家庭SUV新客成交 | family-suv-deal-20260816-094000 | ✅ 8节点全部完成 | 超授权让利触发 L2 审批单（APR-B949CC，不阻塞流程） |
| DEAL-2002 首购金融方案 | first-car-finance-20260816-140500 | ✅ 8节点全部完成 | 金融方案与审批路径设计；订单 pending_approval（L2 审批） |
| DEAL-2003 老客置换升级 | trade-in-renewal-20260816-162000 | ✅ 8节点全部完成 | 客户索要 3 万优惠超出授权上限（max 1.0%），系统停止让利并转人工审批 |

## 二、问题清单（按根因分类）

### P1. mention 过滤导致完成报告被静默忽略【框架级，已代码根治】
- **现象**：Worker 完成任务后发送 TASK_COMPLETED，Leader 无任何响应，DAG 停在当前节点；三个场景各出现 1+ 次
- **根因**：copaw `channel.py` 的 `_was_mentioned()` 只认结构化 mention（`m.mentions` 元数据 / HTML mention pill）；且过滤调用处传入的文本参数为空字符串，纯文本 @ 兜底匹配永远失效。Worker 由 LLM 生成的完成报告只带纯文本 @，必然被过滤
- **解决方案**：补丁 `tools/patch_mention_filter.py` —— 在 `_was_mentioned` 开头加入协议消息豁免：消息体含 `TASK_COMPLETED/TASK_RECEIVED/TASK_FAILED` 直接放行。已应用到 Leader 与全部 8 个 Worker
- **验证**：DEAL-2003 后半程 intent-analyst→strategy-planner→negotiation-executor→…→complete_project 全程无人工干预自动流转
- **注意**：Team/Leader 被 manager 重建后容器为全新镜像，补丁丢失，需重新执行 `tools/apply_mention_patch.sh`

### P2. Leader"假派发"——delegate_task 后不发任务消息【协议认知，已指令固化】
- **现象**：taskflow `delegate_task` 返回 ok，Leader 宣布"已派发"即结束回合，Worker 5 小时收不到任务
- **根因**：`delegate_task` 只记录任务状态与推送 spec 文件，**不会发送房间消息**；任务消息必须由 Leader 另行发出
- **解决方案**：向 Leader 发送带标准 mention 的纠正指令，固化"两步派发"规则（delegate_task → 紧跟发送 "New task [task_id]" 消息）；此后三个场景未再复发
- **脚本**：`tools/nudge_leader4.sh`

### P3. LLM 推理超时（MODEL_TIMEOUT 900s）【模型服务，已有恢复范式】
- **现象**：Worker 回合报 `[422] MODEL_TIMEOUT: qwen3.6-plus, timeout limit: 900 seconds` 后静默，不重试不汇报
- **根因**：两类——①模型服务偶发抖动（lead-intake，重启后 45 秒完成）；②Worker 试图单次推理生成超长文档（strategy-planner 连续超时 3 次）
- **解决方案**：重启容器 + 重发任务；对长文档类任务在指令中强制**小步执行**（每条消息 ≤200 字、分章节多次 write_file、每章节 ≤500 字、禁止一次生成长文档），验证后数分钟完成且不再超时
- **脚本**：`tools/recover_lead_intake.sh`、`tools/recover_strategy_planner.sh`

### P4. Worker NO_REPLY 空回合【模型行为，恢复范式】
- **现象**：Worker 执行了工具调用和分析，但回合以 `suppressing NO_REPLY` 结束——无文件产出、无完成报告（DEAL-2003 intent-analyst）
- **解决方案**：重启容器 + 重发任务，指令中明确"必须写 result.md、必须以 TASK_COMPLETED 回复、不允许静默结束"

### P5. MinIO 双路径不一致【框架 bug，补丁规避】
- **现象**：Leader 在 `teams/{team}/shared/` 找文件，Worker 写在全局 `shared/`，互相找不到（多次发生，每次 Team 重建复发）
- **根因**：`sync.py` 的 `_get_team_id()` 从 worker 元数据解析 team——TeamLeader 元数据带 team 字段，普通 Worker 不带
- **解决方案**：`tools/patch_force_global.py` 给 `_get_team_id` 加 override 文件检查（`/root/hiclaw-fs/team_force_global` 存在则强制全局路径）+ `mc mirror` 镜像存量文件 + 重启容器
- **脚本**：`tools/fix_leader_path.sh`（可重复执行）

### P6. 环境类问题【一次性修复】
- admin 无法重入私有 Manager 房间（M_FORBIDDEN）→ 通过 DM 让 manager 发邀请再接受
- manager 收到重建请求只回复文字不执行 → 发送明确强制指令（"Execute the tool call immediately"）
- Element Web IndexedDB 缓存残留 → Cmd+Shift+R / 重新登录
- macOS 容器访问宿主机 → 统一使用 `host.docker.internal`

## 三、通用规律与运维范式

1. **"看似卡住"的两种本质**：正常的流水线等待（Worker 干活期间房间安静）vs 真实故障（静默失败）。判断标准：检查当事 Worker 日志最近 5 分钟是否有活动、MinIO 任务目录是否有新产物
2. **三类静默失败**（框架共性缺陷）：LLM 超时不重试、NO_REPLY 空回合、完成消息被 mention 过滤——均不产生任何错误广播，必须靠日志巡检发现
3. **恢复三板斧**：①重启当事容器（会话状态持久化，重启安全）②重发带标准 mention 格式的任务/提醒消息 ③指令中附加防复发约束（小步执行、必须汇报）
4. **所有与 Agent 的消息交互必须使用标准 Matrix mention**（`m.mentions` + `formatted_body` mention pill），纯文本 @ 一律无效

## 四、脚本清单（tools/ 目录）

| 脚本 | 用途 |
|---|---|
| `patch_mention_filter.py` + `apply_mention_patch.sh` | P1 根治补丁（Leader，含重启） |
| `apply_mention_patch_all.sh` | P1 批量应用到全部 Worker |
| `patch_force_global.py` + `fix_leader_path.sh` | P5 MinIO 路径统一（可重复执行） |
| `recover_lead_intake.sh` / `recover_strategy_planner.sh` / `recover_intent_analyst.sh` | P3/P4 恢复范式模板 |
| `nudge_leader*.sh` | 带标准 mention 的 Leader 提醒模板 |
| `check_*.sh` / `verify_nudge4.sh` | 状态巡检（日志、MinIO 产物、房间消息） |

## 五、对方案文档的价值

上述问题与修复正好构成评审要求的**"异常分支处理与人工介入机制"**实证：
- 高风险动作人工确认：DEAL-2001/2002/2003 均触发 L2 审批（超授权让利、金融征信审批、置换议价底线），系统正确停止自动放行并生成审批单
- 异常检测与恢复：三类静默失败的诊断路径与恢复脚本可复现、可审计
- 框架级加固：mention 豁免补丁使 DAG 从"需人工转发"升级为"全自动流转"，DEAL-2003 后半程零人工干预闭环
