# AGENTS INSTRUCTIONS - AI INTERVIEW COACH (INTERVIEWLY)

## 1. Multi-Account & Branch Assignment Rules (4 Members)
This project strictly involves **4 developers** with distinct branches and Git commit identities:
1. **Lê Văn Nhật**: Branch: `nhatle08052004n` | Name: `nhatle08052004n` | Email: `nhatle08052004n@gmail.com`
2. **Lê Anh Vũ**: Branch: `vule556677` | Name: `vule556677` | Email: `vule556677@gmail.com`
3. **Lê Minh Hiếu 1**: Branch: `xeniellq1` | Name: `xeniellq1` | Email: `xeniellq1@gmail.com`
4. **Lê Minh Hiếu 2**: Branch: `lhieu20231` | Name: `lhieu20231` | Email: `lhieu20231@gmail.com`

> 🚫 **REMOVED MEMBER:**
> Member Huỳnh Thanh Sơn (`thanhson240624`) has been **completely removed** from the team. Never create branches, commit code, or assign tasks under `thanhson240624`.

---

## 2. Single-Folder Directory Rule (Token & Context Optimization)
- **Work only in the two primary directories:**
  - Frontend: `Interview_Coach_SRC_CODE/FE`
  - Backend: `Interview_Coach_SRC_CODE/BE`
- **DO NOT create extra git worktrees or clone duplicate folders** (`FE-*`, `BE-*`).
- All worktree folders have been removed to prevent duplicate codebase indexing, drastically saving AI token consumption and preventing context fragmentation.
- To switch between team members, simply change the active branch and Git configuration directly inside `FE` and `BE`:
  ```bash
  git -C Interview_Coach_SRC_CODE/FE checkout <branch> && git -C Interview_Coach_SRC_CODE/FE config user.name "..." && git -C Interview_Coach_SRC_CODE/FE config user.email "..."
  git -C Interview_Coach_SRC_CODE/BE checkout <branch> && git -C Interview_Coach_SRC_CODE/BE config user.name "..." && git -C Interview_Coach_SRC_CODE/BE config user.email "..."
  ```

---

## 3. Mandatory Git Flow & Synchronization Rules (CRITICAL)
Whenever finishing a task or switching between team members:
1. **Never switch branches blindly without syncing to `main` first.**
2. When a member finishes their subtask:
   - Commit code on their branch under their identity.
   - Push the branch to remote: `git push origin <branch>`.
   - Merge the branch into `main` and push `main`:
     ```bash
     git checkout main && git merge <branch> && git push origin main
     ```
3. When the next member takes over:
   - Pull latest `main`: `git checkout main && git pull origin main`.
   - Checkout their branch and merge `main` into it: `git checkout <next_branch> && git merge main`.
   - Configure their Git identity locally: `git config user.name "..." && git config user.email "..."`.
Refer to `TEAM_GIT_RULES.md` for exact PowerShell one-liners.

---

## 4. Atomic & Frequent Commits Rule (BẮT BUỘC COMMIT NHỎ)
- **TUYỆT ĐỐI KHÔNG gom nhiều trang/tính năng lớn vào 1 commit duy nhất** (không dồn hàng chục files vào một commit khổng lồ).
- Phải chia nhỏ công việc thành từng subtask nguyên tử (Atomic subtasks). Ví dụ:
  - Xong một component UI -> Commit ngay: `feat(practice): add star technique drawer component`
  - Xong một API endpoint -> Commit ngay: `feat(interviews): add session creation endpoint`
  - Sửa một bug logic/style -> Commit ngay: `fix(auth): fix redirect loop after login`
- **Ngay khi code xong và xác nhận chạy tốt một subtask, PHẢI COMMIT NGAY LẬP TỨC** rồi mới chuyển sang làm subtask tiếp theo.
- Lịch sử commit phải thể hiện từng bước làm việc tuần tự, rõ ràng, minh bạch cho từng thành viên.

---

## 5. Token Saving & Agent Constraints
- **Không tự ý build, test và mở headless UI**:
  - Không tự ý chạy `npm run build`, `next build` nếu không được yêu cầu.
  - Không tự ý mở headless browser, chụp ảnh màn hình preview liên tục gây tiêu tốn lượng token lớn.
  - Sau khi code xong một phần, thông báo ngắn gọn để người dùng tự kiểm tra trên trình duyệt và phản hồi.
- Luôn giữ phản hồi ngắn gọn, súc tích, đi thẳng vào trọng tâm hành động.

---

## 6. Architecture & Implementation Guidelines
- **Backend (`Interview_Coach_SRC_CODE/BE`)**:
  - Clean Architecture (N-layer): `presentation -> application -> domain`, `infrastructure implements application ports`.
  - Tuân thủ quy tắc phụ thuộc, không import ngược từ domain/application ra ngoài.
- **Frontend (`Interview_Coach_SRC_CODE/FE`)**:
  - Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS, Lucide Icons, RTK Query.

---

## 7. Strict Local Fix & CI/CD Deployment Rule (BẮT BUỘC FIX LOCAL)
- **Mọi sửa đổi Logic Code, API, UI, Bug Fixes**:
  - **BẮT BUỘC phải sửa và kiểm tra tại Local trước**.
  - Sau đó Commit theo quy tắc nguyên tử (Atomic commit), Push nhánh, Merge vào `main` và Push GitHub để hệ thống **CI/CD GitHub Actions** tự động deploy lên VPS.
  - **TUYỆT ĐỐI KHÔNG sửa code trực tiếp trên VPS qua SSH**: Vì mỗi lần CI/CD chạy lại sẽ pull code từ GitHub và ghi đè (`git reset --hard origin/main`), làm mất sạch thay đổi nóng trên VPS và gây lỗi hồi quy (regression)!
- **Phạm vi DUY NHẤT được phép SSH vào VPS**:
  - Cấu hình hạ tầng mạng, Reverse Proxy Nginx, chứng chỉ SSL Certbot, Firewall/Port, Docker daemon, PM2 system service.
  - Kiểm tra logs hệ thống (`pm2 logs`, `docker logs`).
- **Quản lý tệp Audio tạm thời (Audio Retention & Cleanup)**:
  - Các file audio TTS (`.mp3`) và thu âm (`.webm`) sinh ra trong quá trình phỏng vấn **KHÔNG lưu trữ vĩnh viễn**.
  - Khi cuộc phỏng vấn kết thúc (hoặc kết thúc phiên), Backend phải đưa vào background task/job để tự động xóa sạch toàn bộ thư mục audio của session đó, giải phóng triệt để dung lượng ổ đĩa VPS.

