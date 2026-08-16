#!/bin/bash
# 检查 PPT 现状：目录内容、生成脚本、python-pptx 可用性、PPT 文本提取
OUT=/Users/chery-not-23982/Learn/competation/Agent-infra/ppt_check_tmp.txt
DIR="/Users/chery-not-23982/Learn/competation/Agent-infra/SalesFlow/ppt和作品简介"
PPTX="$DIR/基于多Agent的汽车销售自主成交智能助手-初赛方案.pptx"

{
echo "=== 目录内容 ==="
ls -la "$DIR"
echo ""
echo "=== 查找 ppt 生成脚本 ==="
find /Users/chery-not-23982/Learn/competation/Agent-infra -maxdepth 4 -iname "*ppt*" -not -path "*/node_modules/*" -not -path "*/.git/*" 2>/dev/null
echo ""
echo "=== python-pptx 可用性 ==="
python3 -c "import pptx; print('pptx-ok', pptx.__version__)" 2>&1 | tail -1
echo ""
echo "=== PPT 文本提取 ==="
python3 - "$PPTX" 2>&1 << 'PYEOF'
import sys
try:
    from pptx import Presentation
    prs = Presentation(sys.argv[1])
    for i, slide in enumerate(prs.slides, 1):
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                t = shape.text_frame.text.strip()
                if t:
                    texts.append(t)
            if shape.has_table:
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells]
                    texts.append(' | '.join(cells))
        print(f"--- SLIDE {i} ---")
        print('\n'.join(texts)[:1500])
except Exception as e:
    print('EXTRACT_FAIL:', e)
PYEOF
} > "$OUT" 2>&1
echo SCRIPT_DONE
