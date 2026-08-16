#!/usr/bin/env python3
# 提取参赛手册 PDF 全文，按页输出
from pypdf import PdfReader

PDF = "/Users/chery-not-23982/Learn/competation/Agent-infra/material/参赛手册.pdf"
OUT = "/tmp/handbook_text.txt"

reader = PdfReader(PDF)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(f"TOTAL_PAGES={len(reader.pages)}\n")
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        f.write(f"\n===== PAGE {i} =====\n")
        f.write(text)
print("DONE pages=", len(reader.pages))
