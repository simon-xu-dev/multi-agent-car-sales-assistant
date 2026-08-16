#!/bin/bash
# 安装 python-pptx 并提取 PPT 全文本
OUT=/Users/chery-not-23982/Learn/competation/Agent-infra/ppt_text_dump.txt
PPTX="/Users/chery-not-23982/Learn/competation/Agent-infra/SalesFlow/ppt和作品简介/基于多Agent的汽车销售自主成交智能助手-初赛方案.pptx"

python3 -m pip install python-pptx --quiet > /tmp/pip_install.log 2>&1
echo "PIP_EXIT=$?" >> "$OUT.header"

python3 - "$PPTX" > "$OUT" 2>&1 << 'PYEOF'
import sys
try:
    from pptx import Presentation
    prs = Presentation(sys.argv[1])
    print(f"TOTAL_SLIDES={len(prs.slides)}")
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
        print(f"\n===== SLIDE {i} =====")
        print('\n'.join(texts))
except Exception as e:
    print('EXTRACT_FAIL:', e)
PYEOF
echo EXTRACT_EXIT=$? >> "$OUT.header"
echo SCRIPT_DONE
