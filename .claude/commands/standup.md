---
description: Tạo template standup tuần cho nhóm, dựa trên commit log + todo hiện tại
argument-hint: "[ten-thanh-vien]"
allowed-tools: Bash(git log:*), Bash(git diff:*), Bash(git status), Read, Glob
---

# Standup Report

Tạo báo cáo standup hàng tuần cho thành viên `$ARGUMENTS` (hoặc toàn nhóm nếu không có arg).

## Quy trình

1. Chạy `git log --since="7 days ago" --all --author="$ARGUMENTS" --pretty=format:'%h %s (%ar)'` để lấy commit tuần qua. Nếu không có `$ARGUMENTS`, lấy tất cả.
2. Chạy `git status` để xem work in progress.
3. Đọc `docs/report/` để check tiến độ báo cáo.
4. Đọc plan file `C:/Users/ASUS/.claude/plans/peppy-launching-porcupine.md` để đối chiếu roadmap theo tuần.
5. Xuất báo cáo theo template dưới.

## Template output

```markdown
# Standup tuần [ngày bắt đầu] - [ngày kết thúc]

## Người: [tên hoặc "cả nhóm"]

### Đã xong tuần trước

- [commit + ý nghĩa]
- ...

### Đang làm

- [WIP branch + tiến độ %]
- ...

### Kế hoạch tuần tới

- [task theo roadmap]
- ...

### Blocker

- [nếu có, kèm người giúp]

### Ghi chú cho nhóm

- [PR cần review, quyết định cần vote, v.v.]
```

## Lưu ý

- Commit không có ý nghĩa (vd "fix", "wip") phải suy luận từ diff. Không copy-paste subject thô.
- Nếu không có commit nào trong tuần, flag "không active tuần qua" nhưng vẫn xuất template.
- Đề xuất 1-2 task cho tuần tới dựa trên roadmap Week X trong plan file.
