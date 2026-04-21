---
description: Gọi subagent data-explorer phân tích một khía cạnh dataset PhysioNet
argument-hint: "<câu-hỏi-phân-tích>"
allowed-tools: Task, Read, Grep, Glob, Bash(python:*), Bash(ls:*)
---

# Dataset EDA

Delegate phân tích dataset cho subagent `data-explorer`. Câu hỏi: `$ARGUMENTS`.

## Quy trình

1. Nếu `$ARGUMENTS` trống, gợi ý 5 câu hỏi EDA hay hỏi:
   - Phân phối missing rate theo feature?
   - Trajectory HR/SpO2 khác biệt sepsis vs non-sepsis như nào?
   - ICULOS distribution của group positive?
   - Correlation giữa vital signs trong 6h trước onset?
   - Có bệnh viện/unit nào prevalence cao bất thường?
2. Check dataset đã tải chưa: `ls data/raw/training/` (nếu trống, hướng dẫn tải).
3. Spawn `data-explorer` với prompt gồm câu hỏi + path dataset.
4. Nhận kết quả, save notebook/plot vào `docs/eda/` nếu có.
5. Gợi ý implication cho modeling.

## Lưu ý

- Luôn subsample trước (vd 2000 BN) để chạy nhanh.
- Nếu cần compare sepsis vs non-sepsis, balance sample size.
- Plot save ra `docs/eda/<tên>.png`, không chỉ show inline.
