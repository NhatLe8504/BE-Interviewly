# KẾ HOẠCH TRIỂN KHAI: HỆ THỐNG THEO DÕI KỸ NĂNG VÀ ĐÁNH GIÁ ĐỘ SẴN SÀNG ỨNG TUYỂN (USER SKILL TRACKING & JOB READINESS)

---

## 1. TỔNG QUAN & NGUYÊN TẮC CỐT LÕI

Hệ thống theo dõi kỹ năng (Skill Tracking System) là trục xương sống dữ liệu của Interviewly, cho phép:
1. Nhận diện và ước lượng chính xác năng lực thực tế của người dùng theo từng kỹ năng kỹ thuật và mềm.
2. Xác định career track (Backend, Frontend, Fullstack, DevOps, Mobile, Data...) và seniority level (Intern, Fresher, Junior, Middle, Senior, Lead).
3. Đề xuất câu hỏi, bộ đề luyện tập và tin tuyển dụng (Job) phù hợp nhất với năng lực.
4. Đánh giá độ sẵn sàng ứng tuyển (Job Readiness Assessment) với tỷ lệ phần trăm % và giải thích minh bạch dựa trên bằng chứng đã thể hiện.

### NGUYÊN TẮC BẤT DI BẤT DỊCH:
- **KHÔNG ĐOÁN MÒ (ZERO GUESSWORK / NO KEYWORD REGEX GUESSING)**: Tuyệt đối không dùng regex tìm từ khóa trong tiêu đề câu hỏi để gán skill evidence cho ứng viên khi chưa có câu trả lời hoặc câu hỏi chưa được định danh chuẩn.
- **BẰNG CHỨNG DỰA TRÊN THỰC HÀNH (DEMONSTRATED ABILITY EVIDENCE)**: Kỹ năng chỉ được ghi nhận khi người dùng thực sự trả lời câu hỏi và qua bước chấm điểm/đánh giá (từ Voice Interview, Text Interview, Practice Set, hoặc JD Interview).
- **TAXONOMY CHUẨN HÓA**: Mọi kỹ năng được map về ID chuẩn trong hệ thống taxonomy (ví dụ: `postgresql`, `docker`, `react`, `spring-boot`), không phân mảnh ID tự do.
- **ĐỘ TIN CẬY THEO SỐ LƯỢNG BẰNG CHỨNG (BAYESIAN / IRT ESTIMATION)**: Ít bằng chứng -> Confidence thấp -> Không vội vàng kết luận trình độ cao; nhiều bằng chứng nhất quán -> Confidence cao.

---

## 2. KIẾN TRÚC DỮ LIỆU (DATABASE SCHEMA)

Hệ thống lưu trữ trên 4 bảng PostgreSQL:

### 2.1 `user_skill_evidence` (Bằng chứng nguyên tử)
- `id` (BigSerial, PK)
- `user_id` (BigInt, FK -> users)
- `skill_id` (Varchar 64, e.g. 'java', 'docker', 'react')
- `source_type` (Varchar 32: 'interview_session', 'practice_history', 'jd_interview')
- `source_id` (Varchar 100: ID của phiên / lượt)
- `question_difficulty` (Int: 1-5)
- `score` (Numeric(4,2): 0.00 - 1.00 chuẩn hóa)
- `grader_confidence` (Numeric(4,2): 0.00 - 1.00)
- `evidence_quote` (Text: trích dẫn câu trả lời hoặc tóm tắt)
- `input_mode` (Varchar 16: 'voice', 'text', 'quiz')
- `rubric_scores` (JSON: breakdown clarity, logic, example, relevance)
- `flags` (JSON: has_answer, is_pretagged, duration_sec, etc.)
- `created_at` (Timestamp with timezone)

### 2.2 `user_skill_levels` (Mức độ kỹ năng tổng hợp)
- `id` (BigSerial, PK)
- `user_id` (BigInt, FK -> users)
- `skill_id` (Varchar 64)
- `ability_score` (Numeric(4,2): 0.00 - 5.00, thang Elo θ)
- `confidence` (Numeric(4,2): 0.00 - 1.00)
- `level` (Varchar 20: 'none', 'beginner', 'junior', 'middle', 'senior', 'lead')
- `evidence_count` (Int)
- `max_difficulty_passed` (Int: 0-5)
- `last_evidence_at` (Timestamp with timezone)
- `updated_at` (Timestamp with timezone)

### 2.3 `user_career_profiles` (Hồ sơ hướng nghiệp & Seniority)
- `user_id` (BigInt, PK, FK -> users)
- `primary_role_track` (Varchar 50, Nullable: None khi chưa đủ dữ liệu)
- `secondary_role_track` (Varchar 50, Nullable)
- `role_confidence` (Numeric(4,2))
- `overall_level` (Varchar 20: 'none', 'fresher', 'junior', 'middle', 'senior', 'lead')
- `top_skills` (JSON: danh sách kỹ năng mạnh nhất)
- `weak_skills` (JSON: danh sách kỹ năng cần cải thiện)
- `updated_at` (Timestamp with timezone)

### 2.4 `job_readiness_checks` (Cache đánh giá phù hợp Job)
- `id` (BigSerial, PK)
- `user_id` (BigInt, FK -> users)
- `job_id` (Varchar 64, FK -> job_postings)
- `match_percent` (Int: 0 - 100)
- `verdict` (Varchar 32: 'ready', 'almost', 'not_ready', 'insufficient_data')
- `data_coverage` (Numeric(4,2): tỷ lệ kỹ năng có bằng chứng, gồm cả unknown trong mẫu số)
- `requirements_breakdown` (JSON)
- `explanation` (Text)
- `recommended_skills` (JSON)
- `analysis_engine` (Varchar 16: 'heuristic' | 'jev')
- `computed_at` (Timestamp with timezone)

---

## 3. CÁC NGUỒN THEO DÕI KỸ NĂNG THỰC TẾ (TRACKING ENTRY POINTS)

### Nguồn A: Buổi phỏng vấn tương tác (Text & Voice Interview Sessions)
- **Bảng nguồn**: `interview_sessions`, `interview_turns`, `answer_evaluations`, `session_question_selections`.
- **Luồng dữ liệu**:
  1. Khi phiên kết thúc (`interview_sessions.status = 'completed'`).
  2. Lấy danh sách câu hỏi đã được chọn (`session_question_selections`) kết nối `question_bank`.
  3. Lấy lượt trả lời của ứng viên (`interview_turns` với `speaker = 'candidate'`).
  4. Lấy kết quả chấm từ AI Grader (`answer_evaluations`).
  5. Đọc `skill_ids` đã được pre-tagged từ `question_bank`.
  6. Nếu câu hỏi có `skill_ids` hợp lệ và ứng viên có câu trả lời thực tế -> sinh `SkillEvidenceEvent`.

### Nguồn B: Luyện tập theo bộ đề (Practice Question Sets & History)
- **Bảng nguồn**: `practice_history`, `question_sets`, `question_set_items`, `question_bank`.
- **Luồng dữ liệu**:
  1. Khi người dùng hoàn thành một set đề ôn tập (`practice_history` được ghi nhận).
  2. Phân tích `questions_summary` JSON lấy `question_id` và `score`.
  3. Tra cứu `question_bank` theo `question_id` để lấy `skill_ids` đã được gán nhãn chuẩn.
  4. Ghi nhận evidence với `source_type = 'practice_history'`.

### Nguồn C: Phỏng vấn giả lập theo JD (JD Interview Workspace)
- **Bảng nguồn**: `jd_generation_jobs`, `interview_scripts`, `interview_sessions`.
- **Luồng dữ liệu**:
  1. Script tạo từ JD có các tiêu chí đánh giá và kỹ năng mục tiêu theo từng câu hỏi trong `interview_scripts.items`.
  2. Lượt đánh giá tương ứng chuyển thành evidence có `source_type = 'jd_interview'`.

---

## 4. LỘ TRÌNH TRIỂN KHAI THEO TỪNG GIAI ĐOẠN (ROADMAP)

### PHASE 0: KHẮC PHỤC HỒI QUY & LÀM SẠCH DỮ LIỆU GIẢ LẬP
1. **Sửa lỗi import**: Import `JobRequirementItem` vào `service.py` để ngăn chặn lỗi 500 khi đọc cache job readiness.
2. **Cấu trúc trường Nullable**: Đổi `UserCareerProfileRecord.primary_role_track` thành nullable (mặc định `None` khi chưa có dữ liệu).
3. **Phục hồi endpoint jobs**: Khôi phục `get_sync_status` và loại bỏ naive override `sort_by == "match"` làm mất filter gốc.
4. **Xóa sạch dữ liệu đoán mò**: Xóa các record trong `user_skill_evidence` bị tạo do regex matching tiêu đề.

### PHASE 1: KHÁM PHÁ VÀ XÂY DỰNG TÀI LIỆU DISCOVERY & CONTRACTS
1. Tạo tài liệu `docs/skill-tracking-discovery.md` ghi nhận chi tiết:
   - Cơ chế lưu trữ nội dung trả lời của ứng viên trong Text/Voice sessions.
   - Thang điểm chuẩn của từng bộ chấm (`answer_evaluations`: 0..10, `practice_history`: 0..100).
   - Điểm kích hoạt trạng thái session completed.
2. Định nghĩa cấu trúc chuẩn `SkillEvidenceEvent` trong domain layer.
3. Viết unit test xác thực model và contracts.

### PHASE 2: TAXONOMY & TIỆN ÍCH GÁN NHÃN CÂU HỎI (PRE-TAGGING QUESTION BANK)
1. Rà soát `skill_taxonomy.json`: loại bỏ các alias quá ngắn dễ gây nhầm lẫn (`go`, `ts`, `py`, `rest`).
2. Cập nhật `question_bank` với `skill_ids` được xác minh chính xác cho 15 câu hỏi hiện có và các bộ đề mẫu.
3. Tạo utility/script hỗ trợ phân tích và gán nhãn kỹ năng cho câu hỏi mới tự động qua LLM.

### PHASE 3: DỊCH VỤ THEO DÕI KỸ NĂNG XUYÊN MODULE (SKILL TRACKING SERVICE)
1. Hiện thực `SkillTrackingService` với các handlers:
   - `handle_interview_session_completed(session_id: int)`
   - `handle_practice_history_recorded(history_id: int)`
   - `handle_jd_interview_completed(job_id: str)`
2. Tích hợp hook vào luồng hoàn tất phỏng vấn và hoàn tất bài ôn tập.
3. Kiểm tra tính lũy tiến và hội tụ của thuật toán Elo/Bayesian estimation.

### PHASE 4: ĐÁNH GIÁ ĐỘ SẴN SÀNG ỨNG TUYỂN (JOB READINESS ENGINE)
1. Đối chiếu yêu cầu kỹ năng của JD với bộ kỹ năng đã có bằng chứng của ứng viên.
2. Trả về verdict minh bạch (`ready`, `almost_ready`, `needs_practice`, `insufficient_data`) kèm explanation cụ thể.
3. Cung cấp API audit: `GET /api/v1/profile/skills/{skill_id}/evidence` để ứng viên xem lại các câu trả lời đã tạo nên điểm kỹ năng.

### PHASE 5: HOÀN THIỆN GIAO DIỆN & TỐI ƯU TRẢI NGHIỆM NGƯỜI DÙNG
1. Giao diện Job Detail: Nút "Kiểm tra độ sẵn sàng với AI" tương tác mượt mà, hiển thị radar/breakdown tinh tế theo tone màu trang chủ (warm-neutral, không lạm dụng badge AI rực rỡ).
2. Giao diện Profile: Thẻ hồ sơ kỹ năng và biểu đồ năng lực đồng bộ.
3. Kiểm thử toàn diện BE & FE.
