---
description: Chạy full quality check trước khi PR (lint, type-check, test, security)
allowed-tools: Bash(pre-commit:*), Bash(ruff:*), Bash(mypy:*), Bash(pytest:*), Bash(npm:*), Bash(bandit:*)
---

# Pre-PR Quality Check

Chạy đầy đủ quality gate trước khi commit/PR.

## Quy trình

Chạy lần lượt (parallel khi có thể), dừng nếu có step fail:

1. **Format + lint Python:**
   ```bash
   pre-commit run --all-files
   ```
2. **Type check:**
   ```bash
   mypy ml/ app/backend/ data-pipeline/ --ignore-missing-imports
   ```
3. **Security scan:**
   ```bash
   bandit -r ml/ app/backend/ data-pipeline/ -ll
   ```
4. **Test Python:**
   ```bash
   pytest tests/unit/ -v --tb=short
   ```
5. **Frontend lint + test:**
   ```bash
   cd app/frontend && npm run lint && npm test -- --run
   ```

## Output format

```
Quality Gate:
  [✓] Lint         (0 issue)
  [✓] Type check   (0 error)
  [✗] Security     (2 HIGH - bandit: B301 pickle in ml/src/inference.py:45)
  [✓] Test Python  (42 passed)
  [✓] Test React   (18 passed)

2 blocker trước khi PR. Xem chi tiết bên trên.
```

## Lưu ý

- Nếu user muốn fix tự động, nhắc: `ruff format . && ruff check --fix .`
- Không bỏ qua security warning. Nếu là false positive, thêm `# nosec B301` kèm comment giải thích.
