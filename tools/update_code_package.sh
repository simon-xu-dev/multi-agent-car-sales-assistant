#!/bin/bash
# 代码包更新：脱敏敏感脚本 → gitignore 备份文件 → 全量提交 → 推送
cd /Users/chery-not-23982/Learn/competation/Agent-infra/SalesFlow || exit 1

echo "=== 1. 脱敏：替换真实 token/密码为占位符 ==="
SENSITIVE_FILES=$(grep -rl "<MATRIX_ADMIN_TOKEN>\|<MANAGER_PASSWORD>\|<MATRIX_ADMIN_TOKEN>" tools/ at/ docs/ 2>/dev/null)
for f in $SENSITIVE_FILES; do
  sed -i '' \
    -e 's/<MATRIX_ADMIN_TOKEN>/<MATRIX_ADMIN_TOKEN>/g' \
    -e 's/<MATRIX_ADMIN_TOKEN>/<MATRIX_ADMIN_TOKEN>/g' \
    -e 's/<MANAGER_PASSWORD>/<MANAGER_PASSWORD>/g' \
    "$f"
  echo "  sanitized: $f"
done
echo "残留检查（应为 0）: $(grep -rl '<MATRIX_ADMIN_TOKEN>\|<MANAGER_PASSWORD>' tools/ at/ docs/ scenarios/ skills/ demo/src/ 2>/dev/null | wc -l | tr -d ' ')"

echo ""
echo "=== 2. gitignore 补充（备份/临时文件不入库） ==="
grep -q '\.pptx\.bak' .gitignore || printf '\n# 本地备份与临时文件\n*.pptx.bak\nppt_*_tmp.txt\nppt_text_dump.txt\n' >> .gitignore

echo ""
echo "=== 3. git add 全量 ==="
git add -A
git status --short | wc -l | xargs echo "暂存文件数:"

echo ""
echo "=== 4. commit ==="
git commit -m "feat: 2026-08-16 三场景真 AgentTeams 全闭环证据链 + 异常自愈工程

- 三场景一天内全闭环（24 DAG 节点全绿，116 次工具调用 100% 成功，3 份 complete_project 报告）
- 新增 E26 异常分支与自愈工程：mention 过滤代码级根治（patch_mention_filter.py）+ 超时/空回合恢复范式
- 新增运行证据：8/16 全量 transcript、网关 metrics/logs/audit、三场景 trace、最终报告
- 文档刷新：EVIDENCE.md（E22/E26）、README、方案详述、ARCHITECTURE、作品简介
- PPT 刷新：运行数据更新为 8/16 全闭环、修正与现状矛盾表述
- 工具链：MCP server/client、LLM 决策客户端、评估 harness、OTel exporter、OSS REST 归档
- 安全：运维脚本中的临时 token/密码已脱敏为占位符"

echo ""
echo "=== 5. push（待用户提供私有仓库地址后手动执行） ==="
# git remote add myrepo <私有仓库URL> && git push myrepo main
echo "SKIP_PUSH（等待目标仓库确认）"
echo ""
echo "=== 最终状态 ==="
git --no-pager log --oneline -3
git status --short | head -5
