---
name: report-section
description: Draft một mục báo cáo đồ án bằng tiếng Việt học thuật (theo frame 1-5 của giảng viên). Dùng khi cần viết mục Giới thiệu, Phân tích-Thiết kế, Hiện thực, Kết luận.
---

# Skill: Report Section (Vietnamese academic)

Viết draft một mục trong báo cáo đồ án (file `docs/report/*.md`). Văn phong học thuật tiếng Việt, có cite nguồn, nhất quán thuật ngữ.

## Quy trình

1. Hỏi user (nếu chưa rõ):
   - Mục nào (theo frame giảng viên): 1, 2.1-2.10, 3.1-3.5, 4.1-4.2, 5.
   - Độ dài dự kiến (ngắn ~1 trang / vừa ~2-3 trang / dài ~4-5 trang)
2. Tạo file `docs/report/<section>.md` (vd `docs/report/2-phan-tich-thiet-ke.md`).
3. Cấu trúc chuẩn:
   - Tiêu đề mục (heading cấp 1)
   - Đoạn mở đầu (1-2 câu nêu mục đích mục)
   - Nội dung chi tiết (sub-heading cấp 2, 3)
   - Bảng/biểu đồ nếu cần (reference file trong `docs/uml/`)
   - Đoạn chốt mục (1-2 câu tóm tắt)
4. Tham chiếu thuật ngữ nhất quán (xem glossary dưới).
5. Cite theo format APA tóm tắt: `(Reyna et al., 2020)`. Danh sách đầy đủ ở mục 5.

## Frame báo cáo (giảng viên)

| Mục | Nội dung                                      | Length |
|-----|-----------------------------------------------|--------|
| 1   | Giới thiệu và mô tả bài toán                  | 2-3 tr |
| 2.1 | Sơ đồ chức năng tổng quát                     | 1 tr   |
| 2.2 | Biểu đồ Use Case                              | 1-2 tr |
| 2.3 | Biểu đồ hoạt động                             | 1-2 tr |
| 2.4 | Biểu đồ trình tự                              | 1-2 tr |
| 2.5 | Biểu đồ lớp                                   | 1-2 tr |
| 2.6 | Database diagram                              | 1 tr   |
| 2.7 | ERD                                           | 1 tr   |
| 2.8 | Thiết kế giao diện                            | 2-3 tr |
| 2.9 | Thiết kế giải thuật (ML/DL)                   | 3-4 tr |
| 2.10| Thiết kế bộ test                              | 1-2 tr |
| 3.1 | Công nghệ sử dụng                             | 1-2 tr |
| 3.2 | Dữ liệu                                       | 1-2 tr |
| 3.3 | Triển khai hệ thống                           | 2-3 tr |
| 3.4 | Kết quả các module                            | 3-4 tr |
| 3.5 | Đánh giá, thảo luận                           | 2-3 tr |
| 4.1 | Kết luận                                      | 1 tr   |
| 4.2 | Hướng phát triển                              | 1 tr   |
| 5   | Tài liệu tham khảo                            | 1-2 tr |

## Glossary thuật ngữ (nhất quán trong báo cáo)

| EN                          | VN                                         |
|-----------------------------|--------------------------------------------|
| Sepsis                      | Nhiễm trùng huyết                          |
| ICU (Intensive Care Unit)   | Khoa Hồi sức tích cực                      |
| Vital signs                 | Dấu hiệu sinh tồn / chỉ số sinh tồn        |
| Streaming                   | Truyền phát dữ liệu thời gian thực         |
| Feature engineering         | Trích xuất đặc trưng                       |
| Model drift                 | Trôi mô hình / sai lệch phân phối          |
| Inference                   | Suy luận (của mô hình)                     |
| Pipeline                    | Quy trình xử lý                            |
| Dashboard                   | Bảng điều khiển                            |
| Alert                       | Cảnh báo                                   |
| Early warning               | Cảnh báo sớm                               |
| Ground truth                | Nhãn thật / giá trị chuẩn                  |
| Training / test set         | Tập huấn luyện / tập kiểm tra              |

## Template mở đầu mục 1

```markdown
# 1. Giới thiệu và mô tả bài toán

## 1.1. Bối cảnh

Nhiễm trùng huyết (sepsis) là nguyên nhân tử vong hàng đầu tại các khoa Hồi sức tích cực (ICU) trên toàn thế giới, với tỷ lệ tử vong lên đến 25-30% và mỗi giờ trì hoãn điều trị làm tăng nguy cơ tử vong khoảng 7% (Kumar et al., 2006). Việc phát hiện sớm sepsis—trước khi các triệu chứng rõ ràng xuất hiện—có ý nghĩa sống còn với người bệnh...

## 1.2. Phát biểu bài toán

Xây dựng hệ thống giám sát bệnh nhân ICU từ xa, có khả năng:
- Thu nhận liên tục các dấu hiệu sinh tồn từ thiết bị theo dõi (giả lập streaming từ bộ dữ liệu PhysioNet 2019);
- Dự đoán nguy cơ sepsis sớm ít nhất 6 giờ trước khi bệnh phát;
- Hiển thị thông tin trực quan qua bảng điều khiển cho bác sĩ, kèm cảnh báo thời gian thực;
- Áp dụng quy trình MLOps đầy đủ (quản lý thí nghiệm, CI/CD, giám sát trôi mô hình).

## 1.3. Mục tiêu và phạm vi

**Mục tiêu chính:**
1. ...
2. ...

**Phạm vi:** Do hạn chế về hạ tầng và ngân sách, nhóm sử dụng LocalStack để mô phỏng dịch vụ AWS trong giai đoạn phát triển, và triển khai thực trên AWS Free Tier cho buổi bảo vệ cuối kỳ.

## 1.4. Đối tượng sử dụng

- **Bác sĩ ICU:** theo dõi bệnh nhân, xác nhận cảnh báo, ghi chú.
- **Quản trị viên:** cấu hình ngưỡng cảnh báo, xem drift report.

## 1.5. Cấu trúc báo cáo

Báo cáo gồm 5 chương chính: ...
```

## Lưu ý văn phong

- Tránh đại từ ngôi thứ nhất ("tôi", "chúng tôi" dùng hạn chế).
- Câu chủ động > bị động khi nói về thiết kế của nhóm.
- Số liệu phải có nguồn hoặc link experiment trong MLflow.
- Code block chỉ khi cần minh hoạ cấu trúc/thuật toán, không paste toàn bộ implementation.
- Biểu đồ: luôn có caption dạng "Hình 2.1. Sơ đồ use case..." và reference trong văn bản.
