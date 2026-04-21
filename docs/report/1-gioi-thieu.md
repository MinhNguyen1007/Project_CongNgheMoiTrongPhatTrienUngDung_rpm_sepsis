# 1. Giới thiệu và mô tả bài toán

Mục này trình bày bối cảnh thực tế dẫn đến đề tài, phát biểu bài toán cần giải quyết, mục tiêu và phạm vi của đồ án, đối tượng sử dụng hệ thống, cùng cấu trúc tổng thể của báo cáo.

## 1.1. Bối cảnh

Nhiễm trùng huyết (sepsis) là tình trạng rối loạn chức năng tạng nguy hiểm do phản ứng mất kiểm soát của cơ thể đối với tác nhân nhiễm trùng, và hiện là một trong những nguyên nhân tử vong hàng đầu tại các khoa Hồi sức tích cực (Intensive Care Unit - ICU) trên toàn thế giới. Theo nghiên cứu dịch tễ học toàn cầu của Rudd và cộng sự (2020), mỗi năm có khoảng 48,9 triệu ca sepsis được ghi nhận, trong đó khoảng 11 triệu ca tử vong, chiếm gần 20% tổng số ca tử vong toàn cầu. Tỷ lệ tử vong của bệnh nhân sepsis tại ICU dao động 25-30%, và con số này có thể lên đến 40-50% khi tiến triển thành sốc nhiễm khuẩn (septic shock).

Yếu tố then chốt quyết định khả năng sống sót của bệnh nhân sepsis là **thời gian phát hiện và điều trị**. Nghiên cứu của Kumar và cộng sự (2006) cho thấy mỗi giờ trì hoãn việc sử dụng kháng sinh phù hợp làm tăng khoảng 7,6% nguy cơ tử vong ở bệnh nhân sốc nhiễm khuẩn. Hướng dẫn Surviving Sepsis Campaign 2021 khuyến nghị khởi động điều trị kháng sinh và hồi sức dịch trong vòng một giờ kể từ khi nghi ngờ sepsis (Evans và cộng sự, 2021). Tuy nhiên, thực tế lâm sàng cho thấy sepsis thường được chẩn đoán muộn do triệu chứng giai đoạn sớm không đặc hiệu, dễ bị nhầm lẫn với các tình trạng khác.

Sự phát triển của các hệ thống giám sát sinh hiệu liên tục (continuous vital sign monitoring) và lưu trữ hồ sơ bệnh án điện tử (electronic health record) đã mở ra khả năng ứng dụng trí tuệ nhân tạo để phát hiện sớm sepsis. Các mô hình học máy và học sâu có khả năng nhận diện được những mẫu biến thiên tinh vi trong chuỗi thời gian của các chỉ số sinh tồn mà mắt thường khó phát hiện, từ đó đưa ra cảnh báo sớm nhiều giờ trước khi sepsis được chẩn đoán lâm sàng (Reyna và cộng sự, 2020). Song song đó, các kiến trúc truyền phát dữ liệu thời gian thực (streaming) và quy trình vận hành học máy (MLOps) đã trở thành tiêu chuẩn công nghiệp cho việc triển khai và bảo trì các mô hình học máy trong môi trường sản xuất có yêu cầu cao về độ tin cậy.

Đề tài "Hệ thống giám sát bệnh nhân từ xa bằng Streaming và MLOps" đặt trong bối cảnh này, hướng đến xây dựng một nguyên mẫu (prototype) kết hợp giữa công nghệ truyền phát dữ liệu, học máy lâm sàng và quy trình MLOps, với mục đích minh họa khả năng ứng dụng công nghệ mới vào bài toán y tế có ý nghĩa xã hội.

## 1.2. Phát biểu bài toán

Cho trước dòng dữ liệu sinh hiệu của một bệnh nhân được theo dõi tại ICU, bao gồm các chỉ số như nhịp tim (HR), độ bão hòa oxy (SpO2), nhiệt độ cơ thể (Temp), huyết áp tâm thu (SBP), huyết áp trung bình (MAP), nhịp thở (Resp), cùng các giá trị xét nghiệm định kỳ (lactate, creatinine, BUN, v.v.), hệ thống cần:

- **Tiếp nhận dữ liệu liên tục** theo mô hình streaming, mô phỏng tình huống bệnh viện thu thập sinh hiệu theo thời gian thực.
- **Dự đoán nguy cơ nhiễm trùng huyết** của bệnh nhân trong cửa sổ 6 giờ sắp tới. Đầu ra là xác suất (probability) trong khoảng [0, 1], kèm cơ chế cảnh báo khi xác suất vượt ngưỡng định sẵn.
- **Đảm bảo độ trễ thấp**: thời gian từ lúc nhận được một quan sát mới đến khi hiển thị kết quả trên bảng điều khiển không vượt quá 500 ms (phần trăm thứ 95).
- **Hỗ trợ bác sĩ ra quyết định** thông qua bảng điều khiển (dashboard) trực quan, gồm biểu đồ chuỗi thời gian của các sinh hiệu, mức độ nguy cơ theo thời gian, và danh sách cảnh báo đang hoạt động.
- **Vận hành đầy đủ quy trình MLOps**: quản lý thí nghiệm, đăng ký mô hình, triển khai liên tục (CI/CD), cũng như giám sát trôi dữ liệu (drift) và hiệu năng mô hình sau khi đưa vào vận hành.

Một cách hình thức, bài toán có thể phát biểu như sau: với chuỗi quan sát $x_1, x_2, ..., x_t$ của một bệnh nhân đến thời điểm $t$, mô hình cần học hàm $f$ sao cho $f(x_1, ..., x_t) = P(y_{t+6} = 1 \mid x_{1:t})$, trong đó $y_{t+6} = 1$ nếu bệnh nhân được chẩn đoán sepsis trong vòng 6 giờ kế tiếp (theo định nghĩa Sepsis-3 của Singer và cộng sự, 2016).

Chỉ tiêu đánh giá chính là điểm lợi ích chuẩn hóa (Normalized Utility Score) do ban tổ chức PhysioNet Challenge 2019 đề xuất, kết hợp với các chỉ số bổ trợ: diện tích dưới đường ROC (AUROC), diện tích dưới đường Precision-Recall (AUPRC), và độ nhạy tại độ đặc hiệu 95%.

## 1.3. Mục tiêu và phạm vi

### Mục tiêu tổng quát

Xây dựng một hệ thống giám sát bệnh nhân từ xa có khả năng dự đoán sớm sepsis trong điều kiện mô phỏng ICU, đồng thời thể hiện đầy đủ các thành phần của một pipeline học máy hiện đại từ thu thập dữ liệu đến giám sát mô hình sau triển khai.

### Mục tiêu cụ thể

1. Thiết kế kiến trúc hệ thống phân tán theo mô hình streaming, sử dụng các dịch vụ AWS (giả lập bằng LocalStack trong giai đoạn phát triển).
2. Huấn luyện và đánh giá ít nhất hai mô hình học máy khác nhau (một mô hình baseline và một mô hình học sâu) cho bài toán dự đoán sepsis, đạt chỉ số AUROC tối thiểu 0,80 trên tập kiểm tra.
3. Xây dựng bảng điều khiển web thời gian thực cho phép bác sĩ theo dõi danh sách bệnh nhân, xem chi tiết diễn biến sinh hiệu và nhận cảnh báo ngay khi xác suất sepsis vượt ngưỡng.
4. Tích hợp quy trình MLOps hoàn chỉnh: quản lý thí nghiệm với MLflow, tích hợp và triển khai liên tục với GitHub Actions, phát hiện trôi dữ liệu với Evidently AI, và giám sát hạ tầng với Prometheus và Grafana.
5. Triển khai thực trên môi trường AWS Free Tier ở giai đoạn bảo vệ cuối kỳ, chứng minh khả năng vận hành trên hạ tầng đám mây thật.

### Phạm vi

**Bao gồm trong đồ án:**

- Giả lập streaming từ bộ dữ liệu công khai PhysioNet Computing in Cardiology Challenge 2019, thay cho thiết bị y tế thật.
- Triển khai kiến trúc trên hai môi trường: LocalStack (phát triển) và AWS Free Tier (demo cuối kỳ).
- Hỗ trợ hai loại người dùng: bác sĩ ICU và quản trị viên hệ thống.
- Các chức năng cốt lõi: đăng nhập, xem danh sách bệnh nhân, xem chi tiết, nhận và xác nhận cảnh báo, cấu hình ngưỡng, xem báo cáo drift.

**Không bao gồm:**

- Tích hợp với thiết bị y tế thực tế hoặc hệ thống hồ sơ bệnh án điện tử của bệnh viện (HL7/FHIR).
- Các ứng dụng trên thiết bị di động.
- Các tính năng hành chính bệnh viện (lập lịch, thanh toán, quản lý thuốc).
- Chứng nhận y tế (FDA, CE-Mark) — đồ án mang tính học thuật, không phục vụ triển khai lâm sàng thực tế.

## 1.4. Đối tượng sử dụng

Hệ thống phục vụ ba nhóm tác nhân (actor) chính:

- **Bác sĩ và điều dưỡng ICU**: người trực tiếp theo dõi bệnh nhân, nhận cảnh báo sớm, xác nhận hoặc hủy cảnh báo, và ghi chú quyết định lâm sàng. Đây là nhóm người dùng chính và là đối tượng tối ưu hóa trải nghiệm.
- **Quản trị viên hệ thống**: thiết lập ngưỡng cảnh báo, quản lý tài khoản người dùng, theo dõi báo cáo drift và hiệu năng mô hình, quyết định thời điểm huấn luyện lại mô hình.
- **Hệ thống cảm biến (giả lập)**: trong phạm vi đồ án, đóng vai trò bởi bộ mô phỏng đẩy dữ liệu PhysioNet vào luồng xử lý. Ở môi trường thực tế, vai trò này thuộc về các thiết bị theo dõi sinh hiệu (patient monitor).

## 1.5. Ý nghĩa của đồ án

Về mặt học thuật, đồ án cung cấp một trường hợp nghiên cứu tích hợp nhiều công nghệ đang nổi: streaming data, học máy trên chuỗi thời gian lâm sàng, kiến trúc dịch vụ đám mây, và quy trình MLOps. Thông qua quá trình thực hiện, các thành viên nhóm có cơ hội vận dụng kiến thức lý thuyết từ nhiều môn học vào một bài toán có yêu cầu kỹ thuật cao.

Về mặt thực tiễn, mặc dù không đủ điều kiện để triển khai lâm sàng trực tiếp, kiến trúc và mã nguồn của đồ án có thể đóng vai trò tham khảo cho các nghiên cứu mở rộng trong tương lai, đặc biệt với các bệnh viện hoặc đơn vị y tế mong muốn tự xây dựng hệ thống cảnh báo sớm trên hạ tầng mã nguồn mở.

## 1.6. Cấu trúc báo cáo

Báo cáo được tổ chức thành năm chương chính:

- **Chương 1 — Giới thiệu và mô tả bài toán**: bối cảnh thực tế, phát biểu bài toán, mục tiêu, phạm vi, đối tượng sử dụng.
- **Chương 2 — Phân tích và thiết kế**: quy trình thiết kế, sơ đồ chức năng, các biểu đồ UML (use case, hoạt động, trình tự, lớp), thiết kế cơ sở dữ liệu, thiết kế giao diện, thiết kế thuật toán học máy, và thiết kế bộ test.
- **Chương 3 — Hiện thực**: công nghệ sử dụng, dữ liệu, quy trình triển khai, kết quả từng module, và đánh giá kết quả.
- **Chương 4 — Kết luận**: tổng kết kết quả đạt được và đề xuất hướng phát triển.
- **Chương 5 — Tài liệu tham khảo**: danh mục tài liệu học thuật và kỹ thuật đã trích dẫn.

Các phụ lục đi kèm gồm hướng dẫn cài đặt, cấu hình môi trường và biên bản làm việc nhóm.

---

*[TBD: sau khi vẽ xong các biểu đồ ở Chương 2, cập nhật lại Mục 1.6 nếu cấu trúc thay đổi.]*
