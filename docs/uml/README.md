# UML Diagrams

Mỗi file `.puml` là một biểu đồ PlantUML tương ứng với một mục trong Chương 2 của báo cáo.

## Danh sách biểu đồ

| File                                | Mục báo cáo | Loại                        |
| ----------------------------------- | ----------- | --------------------------- |
| `01-functional-overview.puml`       | 2.1         | Sơ đồ chức năng tổng quát   |
| `02-usecase.puml`                   | 2.2         | Biểu đồ Use Case            |
| `03-activity-sepsis-detection.puml` | 2.3         | Biểu đồ hoạt động           |
| `04-sequence-sepsis-detection.puml` | 2.4         | Biểu đồ trình tự            |
| `05-class-domain.puml`              | 2.5         | Biểu đồ lớp                 |
| `06-database-schema.puml`           | 2.6         | Database diagram            |
| `07-erd.puml`                       | 2.7         | ERD                         |
| `08-ui-wireframe.md`                | 2.8         | Wireframe giao diện (ASCII) |

## Render ra PNG

### Cách 1 — Docker (khuyến nghị)

```bash
docker run --rm -v "$(pwd)":/work -w /work plantuml/plantuml *.puml
```

### Cách 2 — Local PlantUML

Cần Java + file `plantuml.jar`:

```bash
java -jar plantuml.jar docs/uml/*.puml
```

### Cách 3 — VSCode extension

Cài extension `jebbs.plantuml`, mở file `.puml`, bấm `Alt+D` để preview live. Export PNG qua `Ctrl+Shift+P > PlantUML: Export Current Diagram`.

### Cách 4 — Online

Paste nội dung `.puml` vào https://www.plantuml.com/plantuml/uml/

## Theme

Tất cả biểu đồ dùng `!theme plain` để giữ nhẹ, dễ in trắng đen cho báo cáo.

## Quy ước đặt tên

- File: `NN-<loại>-<chủ-đề>.puml`, NN là số thứ tự khớp mục báo cáo.
- Tiêu đề biểu đồ (dòng `@startuml <tên>`): `kebab-case` tiếng Anh.
- Ghi chú trong biểu đồ: tiếng Việt cho báo cáo.

## Caption trong báo cáo

Khi embed vào báo cáo, caption theo format:

> _Hình 2.N. Tên biểu đồ_

và reference trong văn bản dưới dạng "Hình 2.1 thể hiện...".
