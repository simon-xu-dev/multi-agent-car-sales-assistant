#!/bin/bash
# 落盘今日三场景网关证据：metrics + logs + audit
OUT=/Users/chery-not-23982/Learn/competation/Agent-infra/SalesFlow/docs/RUN_EVIDENCE
for sid in family_suv_deal first_car_finance trade_in_renewal; do
  curl -s -m 10 "http://127.0.0.1:18089/tools/$sid/metrics" > $OUT/gateway_metrics_${sid}_20260816.json
  curl -s -m 10 "http://127.0.0.1:18089/tools/$sid/logs" > $OUT/gateway_logs_${sid}_20260816.json
  curl -s -m 10 "http://127.0.0.1:18089/tools/$sid/audit" > $OUT/gateway_audit_${sid}_20260816.json
  mc=$(python3 -c "import json; d=json.load(open('$OUT/gateway_metrics_${sid}_20260816.json')); print(d.get('result',{}).get('tool_calls','?'))" 2>/dev/null)
  lc=$(python3 -c "import json; d=json.load(open('$OUT/gateway_logs_${sid}_20260816.json')); r=d.get('result',[]); print(len(r) if isinstance(r,list) else '?')" 2>/dev/null)
  ac=$(python3 -c "import json; d=json.load(open('$OUT/gateway_audit_${sid}_20260816.json')); r=d.get('result',[]); print(len(r) if isinstance(r,list) else '?')" 2>/dev/null)
  echo "$sid => tool_calls=$mc logs=$lc audit=$ac"
done
echo ""
echo "=== run_evidence_live 目录（审计 JSONL）==="
ls -la /Users/chery-not-23982/Learn/competation/Agent-infra/SalesFlow/run_evidence_live/ | head -12
