# tools/ops/ —— 一次性运维脚本归档

本目录存放 AgentTeams（hiclaw/copaw）联调与 Demo 运行期间产生的**一次性运维脚本**，
不参与运行时链路，不被 tools/ 根目录核心脚本、Skill、CI 或 Agent 引用。
保留目的是留存当时的故障处置过程，作为异常分支与自愈工程的执行证据
（详见 `docs/RUN_ISSUES_AND_SOLUTIONS.md`、`docs/EVIDENCE.md` E26）。

## 脚本性质

- **check_*.sh / view_mention_code.sh / dig_intent03.sh / find_mention_filter.sh / print_msgs.py / parse_rooms.py**：
  排障探针——查看 Matrix 房间消息、网关状态、容器内代码等，只读不改。
- **nudge_*.sh / recreate_team_msg.sh / restart_all_workers.sh / recover_*.sh**：
  故障恢复——超时催办、空回合重发、假派发修复、Worker 重启与恢复范式。
- **patch_*.py / patch_*.sh / apply_*.sh / fix_*.sh / update_*.sh**：
  框架级热修——mention 过滤补丁、team_id 强制全局路径、Leader/Worker 配置修正（均幂等、可重复执行）。
- **cleanup_*.sh / logout_admin_devices.sh / create_wrapper.sh / debug_team_file.sh / test_team_id.sh**：
  环境治理——Matrix 房间清理、管理员设备登出、包装器与 team 文件调试。
- **collect_run_evidence.sh / dump_gateway_evidence.sh / fetch_gateway_traces.sh**：
  证据采集——从网关/容器拉取 metrics、logs、audit、trace 快照（历史证据已归档至 docs/RUN_EVIDENCE/）。
- **extract_handbook.py / dump_ppt_text.sh / fix_ppt.py / fix_ppt_v2.py / check_ppt.sh**：
  文档工具——参赛手册/PPT 文本抽取与修正，一次性使用。
- **update_code_package.sh / verify_*.sh**：代码包脱敏检查与修复验证。

## 使用说明

- 这些脚本针对当时运行的 Docker 容器与本地绝对路径（`/Users/chery-not-23982/...`）编写，
  环境变化后**不保证直接可用**，仅作参考与证据留存。
- 脚本间的相互引用已同步更新为本目录路径（如 `tools/ops/patch_mention_filter.py`）。
- 运行时核心脚本（mock_tools、mcp_server、selfcheck、eval 等）位于 `tools/` 根目录，勿混淆。
