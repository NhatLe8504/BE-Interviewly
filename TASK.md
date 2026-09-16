# NHIỆM VỤ DÀNH CHO: LÊ MINH HIẾU (1) (Frontend & Voice Interaction Lead)

> **Lưu ý:** Nhiệm vụ của bạn tập trung chủ yếu ở **Frontend** (`Interview_Coach_SRC_CODE/FE-xeniellq1`).  
> Chi tiết toàn bộ nhiệm vụ, component, hooks và luồng xử lý đã được ghi đầy đủ tại file:  
> 👉 [`Interview_Coach_SRC_CODE/FE-xeniellq1/TASK.md`](../FE-xeniellq1/TASK.md)

### Tóm tắt công việc chính của bạn:
1. **Thiết lập phỏng vấn (`/practice`):** Gọi API nạp danh mục Domain/Role động, kiểm tra hạn mức gói cước trước khi bắt đầu.
2. **Phòng phỏng vấn ảo AI (`/practice/[sessionId]`):** Thay thế mock script bằng kết nối API Backend thực tế qua JWT.
3. **SSE Streaming:** Nhận câu hỏi AI trực tiếp dạng stream ký tự mượt mà.
4. **Voice-to-Text & Sóng âm Canvas:** Thu âm qua micro, vẽ sóng âm thanh thời gian thực, bóc băng giọng nói và cho phép sửa lỗi trước khi nộp.
5. **STAR Guidance Drawer:** Bảng trượt hướng dẫn cấu trúc câu trả lời STAR cho ứng viên.

---

### 🛑 QUY TẮC COMMIT & HỎI Ý KIẾN USER (BẮT BUỘC):
- Khi hoàn thành xong bất kỳ task nhỏ hay bước nào:
  - **TUYỆT ĐỐI KHÔNG TỰ Ý COMMIT NGAY.**
  - Chạy test / build kiểm tra trước (`npm run build`).
  - Báo cáo ngắn gọn cho User: đã làm được gì, thay đổi những file nào, kết quả ra sao.
  - **Hỏi ý kiến User:** *"Tôi đã hoàn thành task nhỏ này và kiểm tra không có lỗi. Bạn có đồng ý để tôi commit không?"*
  - **CHỈ KHI USER XÁC NHẬN ĐỒNG Ý** mới được thực hiện `git add`, `git commit` và tạo PR!
