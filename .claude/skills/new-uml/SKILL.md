---
name: new-uml
description: Scaffold một biểu đồ UML mới (use case, sequence, class, activity, ER, component) bằng PlantUML, lưu vào docs/uml/. Dùng khi cần tạo biểu đồ cho mục 2.x của báo cáo.
---

# Skill: New UML Diagram

Tạo file PlantUML (`.puml`) mới trong `docs/uml/` theo loại biểu đồ user yêu cầu. Luôn kèm ví dụ tham khảo từ bối cảnh đồ án (sepsis, ICU, streaming).

## Quy trình

1. Hỏi user loại biểu đồ (nếu chưa rõ): use case / sequence / class / activity / ER / component / data-flow.
2. Hỏi scope (nếu chưa rõ): module nào? Actor nào?
3. Tạo file `docs/uml/NN-<tên>.puml` (NN = số thứ tự theo báo cáo, vd `04-sequence-sepsis-detection.puml`).
4. Viết PlantUML code đúng syntax. Dùng skinparam tối thiểu cho đẹp.
5. Thêm comment đầu file: mục đích biểu đồ, thuộc mục nào của báo cáo (2.1-2.8).
6. Nếu project chưa có `docs/uml/README.md`, tạo luôn với hướng dẫn render (`plantuml -tpng *.puml`).

## Template tham khảo

### Use case
```plantuml
@startuml usecase-sepsis-system
!theme plain
left to right direction
actor "Bác sĩ ICU" as doctor
actor "Admin" as admin
actor "Simulator" as sim

rectangle "Hệ thống giám sát sepsis" {
  usecase "Đăng nhập" as UC1
  usecase "Xem danh sách BN" as UC2
  usecase "Xem chi tiết BN" as UC3
  usecase "Nhận cảnh báo sepsis" as UC4
  usecase "Xác nhận/huỷ cảnh báo" as UC5
  usecase "Cấu hình ngưỡng" as UC6
  usecase "Gửi vital signs" as UC7
}

doctor --> UC1
doctor --> UC2
doctor --> UC3
doctor --> UC4
doctor --> UC5
admin --> UC6
sim --> UC7
@enduml
```

### Sequence
```plantuml
@startuml sequence-sepsis-detection
!theme plain
actor Simulator
participant "Kinesis\n(LocalStack)" as Kinesis
participant "Lambda\nConsumer" as Lambda
database "Feature Store\n(DynamoDB)" as FS
participant "FastAPI\nInference" as API
participant "React\nDashboard" as UI
actor "Bác sĩ"

Simulator -> Kinesis : emit vital_sign event
Kinesis -> Lambda : trigger
Lambda -> FS : update rolling features
Lambda -> API : POST /predict
API -> API : load model (MLflow)\ninference
API -> FS : save prediction
API -->> UI : WebSocket push (prob, alert)
UI -> "Bác sĩ" : hiển thị cảnh báo đỏ
@enduml
```

### Class
```plantuml
@startuml class-domain
!theme plain
class Patient {
  +patient_id: str
  +age: int
  +gender: str
  +admission_time: datetime
}
class VitalSign {
  +timestamp: datetime
  +hr: float
  +spo2: float
  +temp: float
}
class Prediction {
  +timestamp: datetime
  +probability: float
  +model_version: str
}
class Alert {
  +triggered_at: datetime
  +acknowledged: bool
}
Patient "1" -- "*" VitalSign
Patient "1" -- "*" Prediction
Prediction "1" -- "0..1" Alert
@enduml
```

## Lưu ý

- Đặt tên file rõ ràng: số thứ tự + loại + chủ đề (`02-usecase-doctor.puml`).
- Mỗi file = 1 biểu đồ. Không gộp nhiều biểu đồ vào 1 file.
- Sau khi tạo, nhắc user cách render: `plantuml docs/uml/*.puml` hoặc dùng VSCode extension PlantUML.
