---
description: Gọi subagent medical-reviewer để review clinical validity của code ML/alert
argument-hint: "<file-path-hoặc-module>"
allowed-tools: Task, Read, Grep, Glob
---

# Medical Review

Delegate review lâm sàng cho subagent `medical-reviewer` trên file/module `$ARGUMENTS`.

## Quy trình

1. Xác định scope:
   - Nếu `$ARGUMENTS` là file → review file đó.
   - Nếu là folder → review tất cả `.py` trong folder.
   - Nếu trống → hỏi user chỉ định hoặc mặc định review `ml/src/features.py` + `app/backend/src/services/ml_inference.py` + `app/backend/src/services/alerts.py`.
2. Spawn `medical-reviewer` agent với prompt:
   > "Review clinical validity của [files]. Đặc biệt check:
   > - Data leak (feature dùng giá trị tương lai).
   > - Threshold alert hợp lý với sepsis.
   > - Missing handling an toàn (không fill 0 cho vital signs).
   > - Clinical scores (qSOFA/SIRS/SOFA) đúng công thức.
   > Format output theo checklist trong agent config."
3. Nhận kết quả, tổng hợp, suggest fix cho user theo priority BLOCKER > WARNING > INFO.
4. Nếu có BLOCKER, không đề xuất merge PR — gợi ý fix trước.

## Lưu ý

- Không auto-fix. Luôn show findings cho user quyết định.
- Nếu reviewer không tìm thấy vấn đề clinical (vd file pure infra), báo nhẹ nhàng "không có vấn đề lâm sàng".
