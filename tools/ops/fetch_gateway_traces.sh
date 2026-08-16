#!/bin/bash
# 抓取今日 mock 工具网关三场景 trace
OUT=/Users/chery-not-23982/Learn/competation/Agent-infra/SalesFlow/docs/RUN_EVIDENCE
curl -s -m 5 http://127.0.0.1:18089/health | head -c 200
echo ""
for sid in family_suv_deal first_car_finance trade_in_renewal; do
  curl -s -m 10 "http://127.0.0.1:18089/tools/$sid/tools/trace" > $OUT/trace_${sid}_20260816.json 2>/dev/null
  n=$(python3 -c "
import json
try:
    d = json.load(open('$OUT/trace_${sid}_20260816.json'))
    t = d if isinstance(d, list) else d.get('traces', d.get('trace', []))
    print(len(t) if isinstance(t, list) else 'not-list:' + type(t).__name__)
except Exception as e:
    print('parse-fail:' + str(e)[:50])
" 2>/dev/null)
  echo "$sid => $n 条"
done
echo ""
echo "=== 今日时间戳样本（确认是 2026-08-16 的调用）==="
python3 -c "
import json
try:
    d = json.load(open('$OUT/trace_family_suv_deal_20260816.json'))
    t = d if isinstance(d, list) else d.get('traces', d.get('trace', []))
    if isinstance(t, list) and t:
        print('first:', json.dumps(t[0], ensure_ascii=False)[:200])
        print('last:', json.dumps(t[-1], ensure_ascii=False)[:200])
except Exception as e:
    print('fail:', e)
"
