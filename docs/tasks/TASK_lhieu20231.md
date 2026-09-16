# NHIỆM VỤ DÀNH CHO: LÊ TRUNG HIẾU (2) (Admin Portal, Question Catalog & Profile Lead)

> **Lưu ý:** Phần lớn nghiệp vụ Backend của bạn đã được triển khai và merge vào `main` tại Pull Request #7.  
> Trọng tâm tiếp theo của bạn tập trung ở **Frontend** (`Interview_Coach_SRC_CODE/FE-lhieu20231`).  
> Chi tiết toàn bộ nhiệm vụ Frontend đã được ghi đầy đủ tại file:  
> 👉 [`Interview_Coach_SRC_CODE/FE-lhieu20231/TASK.md`](../FE-lhieu20231/TASK.md)

### Tóm tắt công việc của bạn:
1. **Backend (Đã hoàn thành - PR #7):**
   - Xây dựng Catalog API (`domains`, `roles`, `questions`, `star-templates`).
   - Xây dựng Admin Management API (`users`, `roles`, `moderation`, `audit-logs`).
   - Xây dựng Profile API (`get_profile`, `update_profile`, `change_password`).
2. **Frontend (`FE-lhieu20231`):**
   - Xây dựng Cổng quản trị Admin hoàn chỉnh (`/admin/*`: Dashboard, Domains, Roles, Questions, Star-templates, Users, Moderation, Audit-logs, Settings).
   - Xây dựng Trang Hồ sơ cá nhân (`/profile`) và Cài đặt đổi mật khẩu (`/settings`).
   - Xây dựng Thư viện câu hỏi cho ứng viên (`/questions`, `/questions/[id]`).
   - Xây dựng API clients (`profileApi.ts`, `catalogApi.ts`, `adminApi.ts`).

---

### 🛑 QUY TẮC COMMIT & HỎI Ý KIẾN USER (BẮT BUỘC):
- Khi hoàn thành xong bất kỳ task nhỏ hay bước nào:
  - **TUYỆT ĐỐI KHÔNG TỰ Ý COMMIT NGAY.**
  - Chạy test / build kiểm tra trước (`npm run build` hoặc `pytest -q`).
  - Báo cáo kết quả công việc đã làm cho User (file nào tạo/sửa, kết quả ra sao).
  - **Hỏi ý kiến User:** *"Tôi đã hoàn thành task nhỏ này và kiểm tra không có lỗi. Bạn có đồng ý để tôi commit không?"*
  - **CHỈ KHI USER XÁC NHẬN ĐỒNG Ý** mới được thực hiện `git add`, `git commit` và tạo PR!