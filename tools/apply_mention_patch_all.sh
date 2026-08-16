#!/bin/bash
# 批量应用 mention 补丁到所有 Worker（不重启，仅写入文件；下次重启自然生效）
PATCH=/Users/chery-not-23982/Learn/competation/Agent-infra/SalesFlow/tools/patch_mention_filter.py
for w in lead-intake intent-analyst profile-builder knowledge-miner strategy-planner negotiation-executor order-executor customer-ops; do
  c=hiclaw-worker-$w
  docker cp $PATCH $c:/tmp/patch_mention_filter.py 2>/dev/null
  r=$(docker exec $c python3 /tmp/patch_mention_filter.py 2>&1)
  echo "$w => $r"
done
