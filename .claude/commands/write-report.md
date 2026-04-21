---
description: Gọi subagent vietnamese-report-writer soạn/sửa một mục báo cáo
argument-hint: "<mã-mục vd 2.4 | tên-mục | file-path>"
allowed-tools: Task, Read, Write, Edit, Glob
---

# Write Report Section

Delegate viết báo cáo cho subagent `vietnamese-report-writer`. Mục: `$ARGUMENTS`.

## Quy trình

1. Parse `$ARGUMENTS`:
   - Nếu là mã (vd "2.4") → tra bảng mapping trong `.claude/skills/report-section/SKILL.md` để biết mục "Biểu đồ trình tự".
   - Nếu là tên mục → tìm file tương ứng trong `docs/report/`.
   - Nếu là file path → dùng trực tiếp.
2. Kiểm tra context cần thiết:
   - Biểu đồ có trong `docs/uml/` chưa? (cho mục 2.x)
   - Kết quả experiment có trong MLflow chưa? (cho mục 3.4)
3. Spawn `vietnamese-report-writer` với prompt:
   > "Viết/chỉnh sửa mục [X] của báo cáo đồ án. Context:
   >
   > - Kiến trúc hệ thống: xem CLAUDE.md.
   > - Biểu đồ liên quan: [liệt kê từ docs/uml/].
   > - Kết quả: [từ MLflow hoặc docs/experiments.md].
   >   Tuân thủ glossary và checklist trong skill `report-section`."
4. Lưu output vào `docs/report/<section>.md`.
5. Báo cáo diff (số dòng thêm/sửa) cho user.

## Lưu ý

- Nếu thiếu context (vd chưa có UML), báo user và chỉ viết skeleton.
- Không fabricate số liệu. Nếu kết quả chưa có, dùng placeholder `[TBD: AUROC sau run experiment v3]`.
