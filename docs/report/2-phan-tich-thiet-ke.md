# 2. Phân tích và thiết kế

Mục này trình bày quy trình thiết kế hệ thống và các sản phẩm thiết kế cốt lõi: sơ đồ chức năng tổng quát, các biểu đồ UML (use case, hoạt động, trình tự, lớp), thiết kế cơ sở dữ liệu, biểu đồ thực thể - mối quan hệ, thiết kế giao diện, thiết kế giải thuật học máy, và thiết kế bộ test. Các biểu đồ chi tiết được lưu trong thư mục `docs/uml/` dưới định dạng PlantUML, cho phép phiên bản hoá cùng với mã nguồn và dễ dàng cập nhật khi thiết kế thay đổi.

## 2.0. Quy trình thiết kế

Nhóm áp dụng quy trình thiết kế theo năm bước lặp, tương ứng với các sản phẩm bàn giao sau mỗi giai đoạn:

1. **Phân tích yêu cầu**: xác định các tác nhân (actor), các chức năng chính và các ràng buộc phi chức năng (độ trễ, độ khả dụng, bảo mật). Kết quả: danh sách use case và tiêu chí chấp nhận (acceptance criteria).
2. **Thiết kế kiến trúc tổng thể**: xác định các module lớn, giao thức truyền dữ liệu giữa chúng, lựa chọn công nghệ cho từng tầng. Kết quả: sơ đồ chức năng tổng quát.
3. **Thiết kế hành vi**: mô hình hoá luồng xử lý chính bằng biểu đồ hoạt động và biểu đồ trình tự. Kết quả: tài liệu mô tả luồng phát hiện sepsis, luồng xác nhận cảnh báo, luồng huấn luyện lại mô hình.
4. **Thiết kế cấu trúc dữ liệu**: xác định các entity, quan hệ giữa chúng, lựa chọn loại lưu trữ phù hợp. Kết quả: biểu đồ lớp, database schema, ERD.
5. **Thiết kế chi tiết**: giải thuật học máy, thiết kế giao diện, chiến lược kiểm thử. Kết quả: tài liệu thuật toán, wireframe UI, kế hoạch test.

Các biểu đồ được dựng bằng PlantUML để đảm bảo nguồn là mã văn bản có thể review qua pull request, và có thể render thành hình ảnh PNG/SVG khi lắp vào báo cáo PDF.

## 2.1. Sơ đồ chức năng tổng quát

Sơ đồ chức năng tổng quát (xem Hình 2.1, file `docs/uml/01-functional-overview.puml`) phân rã hệ thống thành năm module chính theo vai trò:

1. **Ingest** — Thu nhận: tiếp nhận dữ liệu sinh hiệu theo thời gian thực. Gồm bộ mô phỏng (simulator) đọc dữ liệu PhysioNet và phát vào luồng Kinesis của LocalStack.
2. **Processing** — Xử lý: gồm Lambda Consumer xác thực và chuẩn hoá dữ liệu, cùng thành phần Feature Engineering tính toán các đặc trưng rolling statistics và các điểm số lâm sàng (qSOFA, SIRS).
3. **Storage** — Lưu trữ: DynamoDB lưu đặc trưng mới nhất cho tra cứu độ trễ thấp, S3 (Parquet) lưu lịch sử cho huấn luyện mô hình, PostgreSQL lưu dữ liệu nghiệp vụ (người dùng, cảnh báo, audit log).
4. **ML** — Học máy: dịch vụ FastAPI tải mô hình từ MLflow Registry và thực hiện suy luận; thành phần Evidently AI chạy định kỳ để phát hiện trôi dữ liệu.
5. **Serving** — Phục vụ: WebSocket server đẩy kết quả đến bảng điều khiển React của bác sĩ, Alert Manager gửi Slack webhook khi xác suất vượt ngưỡng nghiêm trọng.

Kiến trúc này tách biệt rõ trách nhiệm (single responsibility) giữa các module, giúp mỗi thành viên nhóm có thể phát triển module của mình một cách độc lập và tích hợp qua các giao diện đã định. Mọi giao tiếp giữa các module đều bất đồng bộ hoặc qua API rõ ràng, tránh phụ thuộc chặt.

## 2.2. Biểu đồ Use Case

Biểu đồ Use Case (Hình 2.2, file `docs/uml/02-usecase.puml`) xác định năm tác nhân và mười ba chức năng chính.

**Tác nhân:**

- **Bác sĩ ICU**: người dùng chính, có quyền xem chi tiết bệnh nhân, xác nhận cảnh báo, ghi chú lâm sàng.
- **Điều dưỡng**: có quyền xem danh sách và sinh hiệu, nhận cảnh báo, nhưng không ghi chú quyết định điều trị.
- **Quản trị viên**: cấu hình ngưỡng, quản lý người dùng, xem báo cáo drift.
- **Hệ thống cảm biến (Simulator)**: tác nhân không phải người, đẩy dữ liệu sinh hiệu vào hệ thống.
- **Pipeline ML nội bộ**: tác nhân thực hiện suy luận và huấn luyện lại theo lịch định kỳ.

**Nhóm chức năng:**

- **Truy cập & theo dõi** (UC01–UC04): đăng nhập, xem danh sách, xem chi tiết, xem biểu đồ real-time.
- **Cảnh báo & phản hồi** (UC05–UC07): nhận, xác nhận, ghi chú cảnh báo.
- **Quản trị hệ thống** (UC08–UC10): cấu hình ngưỡng, quản lý tài khoản, xem báo cáo drift.
- **Backend tự động** (UC11–UC13): gửi sự kiện streaming, suy luận, huấn luyện lại mô hình.

Quan hệ `<<include>>` giữa UC05 và UC12 biểu diễn việc tạo cảnh báo luôn gọi đến module suy luận. Quan hệ `<<extend>>` giữa UC06 và UC07 cho thấy việc ghi chú là bước tuỳ chọn nhưng được khuyến khích sau mỗi xác nhận cảnh báo.

## 2.3. Biểu đồ hoạt động

Biểu đồ hoạt động (Hình 2.3, file `docs/uml/03-activity-sepsis-detection.puml`) mô tả luồng xử lý từ khi nhận một quan sát sinh hiệu mới đến khi hiển thị cảnh báo hoặc cập nhật bảng điều khiển.

Luồng bắt đầu bằng việc xác thực dữ liệu. Nếu giá trị rơi ngoài khoảng sinh lý hợp lệ (ví dụ `HR = 0` hoặc `Temp > 45°C`), quan sát bị loại bỏ và ghi log cho việc debug về sau. Dữ liệu hợp lệ được ghi vào S3 dưới dạng Parquet (cho huấn luyện sau này) và cập nhật vào DynamoDB để làm đặc trưng real-time.

Chỉ khi bệnh nhân đã tích luỹ đủ sáu giờ dữ liệu, hệ thống mới gọi suy luận. Điều này tránh việc đưa ra dự đoán không tin cậy cho những bệnh nhân mới nhập ICU có quá ít dữ liệu. Khi xác suất vượt ngưỡng cảnh báo (mặc định 0,5), hệ thống kiểm tra xem đã có cảnh báo nào cho cùng bệnh nhân trong một giờ qua chưa: nếu có thì chỉ cập nhật, nếu chưa thì tạo cảnh báo mới và đẩy thông báo WebSocket. Cơ chế này (gọi là _alert hysteresis_) giúp tránh gửi nhiều cảnh báo trùng lặp khi xác suất dao động quanh ngưỡng, là vấn đề kinh điển gây "mệt mỏi cảnh báo" (alert fatigue) cho bác sĩ.

Với các trường hợp xác suất ở mức nghiêm trọng (≥ 0,7), ngoài WebSocket, hệ thống còn gửi Slack webhook để nhắn tin cho nhóm trực, đảm bảo không ai bỏ sót cảnh báo quan trọng ngay cả khi không đang nhìn màn hình.

## 2.4. Biểu đồ trình tự

Biểu đồ trình tự (Hình 2.4, file `docs/uml/04-sequence-sepsis-detection.puml`) chi tiết hoá tình huống "phát hiện sepsis và đẩy cảnh báo real-time" ở cấp độ thông điệp giữa các thành phần.

Quy trình gồm ba pha:

- **Pha khởi tạo (một lần)**: FastAPI tải mô hình từ MLflow Registry tại stage `Production`, bác sĩ mở trình duyệt và đăng ký WebSocket channel `/ws/patients/P001`.
- **Pha chu kỳ mỗi giờ (streaming)**: Simulator gửi bản ghi sinh hiệu vào Kinesis, Lambda consumer xác thực và ghi vào S3 + DynamoDB, sau đó gọi endpoint `/predict` của FastAPI. FastAPI xây dựng vector đặc trưng, gọi model dự đoán, lưu kết quả vào DynamoDB. Nếu xác suất ≥ 0,5, hệ thống truy vấn cảnh báo gần nhất cho bệnh nhân; nếu không có cảnh báo nào trong một giờ qua, tạo cảnh báo mới trong PostgreSQL, đẩy WebSocket frame đến dashboard, và gửi Slack nếu xác suất ≥ 0,7.
- **Pha phản hồi của bác sĩ**: Bác sĩ nhấn "Xác nhận", dashboard gọi `POST /alerts/:id/ack`, FastAPI cập nhật trạng thái cảnh báo trong PostgreSQL và broadcast cập nhật để các dashboard khác cũng thấy.

Biểu đồ này đóng vai trò đặc tả giao tiếp giữa các thành viên nhóm: role A (Data/Stream) chịu trách nhiệm phần Simulator → Lambda, role B (ML) chịu trách nhiệm model và inference, role D (Full-stack) chịu trách nhiệm FastAPI → WebSocket → UI.

## 2.5. Biểu đồ lớp

Biểu đồ lớp (Hình 2.5, file `docs/uml/05-class-domain.puml`) mô hình hoá các entity nghiệp vụ chính. Các lớp được nhóm thành bốn gói theo chủ đề:

- **Users & Auth**: `User` với enum `Role` (DOCTOR, NURSE, ADMIN).
- **Patients & Clinical**: `Patient`, `VitalSign`, `LabResult`. Một bệnh nhân có nhiều bản ghi sinh hiệu và kết quả xét nghiệm theo thời gian (quan hệ `1 --*`).
- **ML & Prediction**: `ModelVersion`, `Prediction`, `FeatureVector`. Một mô hình tạo ra nhiều dự đoán; mỗi dự đoán gắn với một vector đặc trưng được tổng hợp từ chuỗi sinh hiệu.
- **Alerts & Audit**: `Alert` với enum `Severity` (WARNING, CRITICAL), `AuditLog` ghi nhận mọi hành động có giá trị pháp lý.

Một số phương thức đáng chú ý: `Alert.acknowledge(user_id, note)` đóng vai trò use case UC06; `Patient.current_iculos()` tính số giờ bệnh nhân đã nằm ICU, là đặc trưng quan trọng cho mô hình; `Prediction.is_high_risk(threshold)` dùng trong logic tạo cảnh báo.

Các lớp được thiết kế không phụ thuộc framework cụ thể (không có annotation SQLAlchemy, Pydantic trong class diagram). Khi hiện thực, chúng sẽ được ánh xạ sang lớp ORM (SQLAlchemy cho PostgreSQL) và schema Pydantic (cho FastAPI).

## 2.6. Thiết kế cơ sở dữ liệu

Biểu đồ database schema (Hình 2.6, file `docs/uml/06-database-schema.puml`) thể hiện việc sử dụng ba loại lưu trữ khác nhau cho các mục đích khác nhau:

**PostgreSQL** lưu dữ liệu nghiệp vụ có cấu trúc: bảng `users`, `patients`, `alerts`, `audit_log`, `alert_threshold_config`. PostgreSQL được chọn vì hỗ trợ ràng buộc toàn vẹn (foreign key), giao dịch ACID, và kiểu JSONB linh hoạt cho `audit_log.payload`. Các chỉ mục quan trọng gồm `(patient_id, triggered_at DESC)` trên bảng `alerts` phục vụ truy vấn cảnh báo gần nhất, và chỉ mục bộ phận (partial index) `WHERE acknowledged=false` để dashboard nhanh chóng lấy danh sách cảnh báo chưa xử lý.

**DynamoDB** lưu đặc trưng real-time trong hai bảng: `patient_latest_features` (partition key = `patient_id`, mỗi bệnh nhân một bản ghi, ghi đè liên tục) và `patient_recent_predictions` (partition key = `patient_id`, sort key = `timestamp`, TTL 48 giờ tự động dọn). DynamoDB được chọn vì độ trễ đọc rất thấp (< 10 ms), schema linh hoạt cho tập đặc trưng thay đổi theo phiên bản mô hình, và cơ chế TTL giảm chi phí lưu trữ. Trong môi trường phát triển, DynamoDB chạy trong LocalStack.

**S3 (Parquet)** lưu dữ liệu lịch sử theo hai bộ phân vùng (partition) theo ngày: `vitals_partitioned` chứa tất cả sinh hiệu và nhãn sepsis; `predictions_archive` chứa tất cả dự đoán đã đưa ra. Định dạng Parquet được chọn vì khả năng nén cột tốt (giảm ~10 lần so với CSV), tốc độ đọc cao cho workload analytics, và tương thích native với Pandas, PyArrow, Spark. Phân vùng theo ngày giúp các truy vấn huấn luyện chỉ đọc phần dữ liệu cần thiết.

Việc phân chia ba nguồn lưu trữ tuân theo nguyên tắc CQRS (Command Query Responsibility Segregation): PostgreSQL cho write-path nghiệp vụ, DynamoDB cho read-path độ trễ thấp, S3 cho batch analytics và huấn luyện mô hình.

## 2.7. Biểu đồ ERD

Biểu đồ thực thể - mối quan hệ (Hình 2.7, file `docs/uml/07-erd.puml`) chuẩn hoá các entity theo dạng chuẩn thứ ba (3NF) trên PostgreSQL.

Các entity chính cùng khóa chính gồm: `User` (user_id), `Patient` (patient_id), `VitalSign` (vital_id), `LabResult` (lab_id), `ModelVersion` (model_id), `Prediction` (prediction_id), `Alert` (alert_id), `AuditLog` (audit_id), và `ThresholdConfig` (config_id).

Các mối quan hệ chính:

- Một `Patient` có nhiều `VitalSign`, `LabResult`, `Prediction`, `Alert` (quan hệ một - nhiều).
- Một `ModelVersion` tạo ra nhiều `Prediction`.
- Một `Prediction` có thể dẫn đến tối đa một `Alert` (quan hệ một - không hoặc một).
- Một `User` có thể xác nhận nhiều `Alert` (vai trò của `acknowledged_by`).
- Mọi hành động của `User` trên các entity đều ghi lại trong `AuditLog`.

Ràng buộc duy nhất (unique key) trên `ModelVersion(name, version)` đảm bảo không tồn tại hai phiên bản mô hình trùng tên và số. Các khoá ngoại được cấu hình `ON DELETE RESTRICT` để tránh việc xoá nhầm bệnh nhân hoặc người dùng đang được tham chiếu.

## 2.8. Thiết kế giao diện

Thiết kế giao diện chi tiết được mô tả trong file `docs/uml/08-ui-wireframe.md` dưới dạng các bản phác thảo ASCII. Bản chính thức trên Figma sẽ được hoàn thiện sau khi thống nhất wireframe trong nhóm.

Năm màn hình chính được thiết kế:

1. **Trang đăng nhập**: form email + mật khẩu, tích hợp JWT.
2. **Dashboard tổng quan**: danh sách bệnh nhân dưới dạng thẻ (card), mỗi thẻ hiển thị xác suất hiện tại, sinh hiệu nổi bật, và biểu đồ mini. Có bộ lọc theo mức độ nguy cơ và tìm kiếm theo ID bệnh nhân.
3. **Chi tiết bệnh nhân**: biểu đồ xác suất sepsis 24 giờ qua, biểu đồ từng sinh hiệu (HR, SpO2, Temp, MAP) với đường ngưỡng, cùng các đặc trưng đóng góp lớn nhất (top SHAP features) để giải thích quyết định của mô hình.
4. **Dialog xác nhận cảnh báo**: ghi lại quyết định lâm sàng theo bốn lựa chọn chính (khởi điều trị, theo dõi thêm, báo động giả, khác), kèm ghi chú tự do.
5. **Trang cấu hình ngưỡng (Admin)**: điều chỉnh ngưỡng warning và critical, xem thông tin mô hình đang vận hành, xem báo cáo drift gần đây.

Nguyên tắc thiết kế quan trọng:

- **Màu sắc có ngữ nghĩa**: đỏ cho nguy cơ nghiêm trọng, vàng cho cảnh báo, xanh cho trạng thái bình thường. Không sử dụng các màu này cho mục đích khác để tránh nhầm lẫn trong môi trường căng thẳng.
- **Giải thích được (explainability)**: hiển thị top features đóng góp vào xác suất dự đoán, tránh tạo cảm giác "hộp đen".
- **Tương thích máy tính bảng**: giao diện responsive tối thiểu hỗ trợ chiều rộng 768px, vì trên thực tế ICU thường sử dụng iPad.
- **Tuân thủ WCAG 2.1 AA**: độ tương phản tối thiểu 4,5:1, hỗ trợ điều hướng bằng bàn phím, nhãn ARIA cho các nút có biểu tượng đơn thuần.

---

Thiết kế giải thuật học máy (Mục 2.9) và thiết kế bộ test (Mục 2.10) được trình bày trong các file riêng biệt do khối lượng nội dung: [2.9-thiet-ke-giai-thuat.md](./2.9-thiet-ke-giai-thuat.md) và [2.10-thiet-ke-test.md](./2.10-thiet-ke-test.md).
