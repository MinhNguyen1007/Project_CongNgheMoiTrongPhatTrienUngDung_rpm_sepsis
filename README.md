# Remote Patient Monitoring — Sepsis Early Warning

> Hệ thống giám sát bệnh nhân ICU + dự đoán sepsis sớm 6 giờ bằng ML. Đồ án môn Emerging Technologies.

## TL;DR

```bash
# 1. Clone + cài đặt
git clone <repo-url> && cd remote-patient-monitoring
python -m venv .venv && .venv\Scripts\activate  # Windows
pip install -r requirements.txt
cd app/frontend && npm install && cd ../..

# 2. Cài pre-commit
pre-commit install

# 3. Tải dataset (cần account PhysioNet)
# https://physionet.org/content/challenge-2019/ → lưu vào data/raw/

# 4. Khởi động stack local
docker-compose up -d

# 5. Init LocalStack resources
bash infra/localstack/init.sh

# 6. Chạy simulator + mở dashboard
python data-pipeline/simulator/run.py --patients 10 --speed 1s
# → http://localhost:5173
```

## Cấu trúc repo

Xem [CLAUDE.md](./CLAUDE.md) mục 4.

## Vibe Coding với Claude Code

Dự án setup đầy đủ để cả nhóm dùng Claude Code hiệu quả. **Mọi thành viên nên đọc mục này trước khi code.**

### Files quan trọng trong `.claude/`

```
.claude/
├── settings.json           # Hooks + permissions chung (commit)
├── settings.local.json     # Cá nhân (KHÔNG commit)
├── mcp.example.json        # Template MCP (copy → mcp.json, KHÔNG commit)
├── skills/                 # Scaffolding templates (commit)
│   ├── new-uml/
│   ├── new-ml-experiment/
│   ├── new-endpoint/
│   ├── new-component/
│   ├── new-feature-function/
│   └── report-section/
├── agents/                 # Subagents chuyên môn (commit)
│   ├── data-explorer.md
│   ├── ml-researcher.md
│   ├── medical-reviewer.md
│   └── vietnamese-report-writer.md
└── commands/               # Slash commands workflow (commit)
    ├── standup.md
    ├── train.md
    ├── deploy-local.md
    ├── review-medical.md
    ├── write-report.md
    ├── eda.md
    └── check-quality.md
```

### Cách dùng

**Skills** — gọi trong session Claude Code:
> "Tạo component mới PatientVitalCard" → Claude tự invoke skill `new-component`.

**Subagents** — gọi để chuyên sâu:
> "Spawn medical-reviewer để check file ml/src/features.py" → tạo subagent với context riêng.

**Slash commands** — gõ trong chat:
- `/standup nguyen-a` — tạo báo cáo tuần cho thành viên A
- `/train ml/configs/lgbm-v3.yaml` — chạy training
- `/deploy-local` — khởi động toàn bộ stack + health check
- `/review-medical ml/src/` — spawn medical reviewer
- `/write-report 2.4` — draft mục 2.4 (Biểu đồ trình tự)
- `/eda "missing rate theo feature"` — spawn data-explorer
- `/check-quality` — chạy full lint+test trước PR

**Hooks** — tự chạy (đã cấu hình):
- Sau mỗi Edit/Write file `.py/.ts/.tsx` → tự format bằng ruff/prettier.
- Cuối session → nhắc update docs nếu kiến trúc đổi.

### Setup MCP (optional)

Xem [docs/mcp-setup.md](./docs/mcp-setup.md). Bổ sung GitHub/Postgres MCP cho Claude để truy vấn trực tiếp.

### Quy tắc vàng

1. **Đọc CLAUDE.md trước khi ask Claude làm gì lớn.** Đó là context chung.
2. **Mô tả intent, không dictate code.** Ví dụ: "thêm endpoint acknowledge alert, cần auth" — tốt hơn "viết hàm tên này, params này".
3. **Review diff kỹ.** Claude có thể scaffold sai nếu context thiếu.
4. **Update CLAUDE.md** khi đổi kiến trúc/convention lớn.
5. **Không commit** `.env`, `mcp.json`, `settings.local.json`.

## Team roles

Xem [CLAUDE.md](./CLAUDE.md) mục 6.

## Roadmap

Chi tiết theo tuần: [C:/Users/ASUS/.claude/plans/peppy-launching-porcupine.md](C:/Users/ASUS/.claude/plans/peppy-launching-porcupine.md).

## Dataset

PhysioNet Computing in Cardiology Challenge 2019:
https://physionet.org/content/challenge-2019/

## License

Academic project — MIT for code, PhysioNet data license cho dataset.
