# BÁO CÁO DISCOVERY: CƠ CHẾ TRACKING KỸ NĂNG NGƯỜI DÙNG THỰC TẾ TRONG HỆ THỐNG INTERVIEWLY

---

## 1. NƠI LƯU TRỮ CÂU TRẢ LỜI CỦA ỨNG VIÊN (CANDIDATE ANSWER PERSISTENCE)

Qua rà soát trực tiếp bảng dữ liệu PostgreSQL và mã nguồn kiến trúc:
- **Bảng `interview_turns`**:
  - `message_text`: Lưu nội dung câu hỏi do AI phỏng vấn viên đưa ra.
  - `transcribed_text`: Lưu nội dung câu trả lời của ứng viên (cả với Voice Interview sau khi qua STT và Text Interview khi người dùng gõ text).
  - `audio_url`: URL file âm thanh giọng nói của ứng viên (nếu bật voice mode).
  - `speaker`: Enum `TurnSpeaker` (`ai` hoặc `candidate`).
  - `question_id`: Khóa ngoại trỏ về `question_bank.question_id` (nếu lượt hỏi sử dụng câu hỏi từ ngân hàng câu hỏi).
- **Domain model `InterviewTurn`** (`reference_app/app/domain/interview.py`):
  - `question_text`: Tương ứng `message_text`.
  - `answer_text`: Tương ứng `transcribed_text`.
  - Phương thức `with_answer(...)` ghi nhận câu trả lời vào turn và repository update vào `row.transcribed_text`.

---

## 2. VÌ SAO USER 27 VÀ CÁC USER TEST CŨ CÓ TURN RỖNG HOẶC CHƯA CÓ ANSWER_EVALUATIONS?

- Khi tạo session mới (`POST /api/v1/interviews/sessions`), hệ thống tự động sinh ra turn 1 (lời chào và câu hỏi mở đầu từ AI). Turn này có `speaker = 'ai'`, `transcribed_text = NULL`.
- Nếu người dùng thoát giữa chừng hoặc test mock mà chưa bấm gửi câu trả lời (`POST /api/v1/interviews/sessions/{id}/turns`), turn của ứng viên chưa được tạo và `answer_evaluations` chưa được kích hoạt.
- Khi người dùng gửi câu trả lời qua `submit_turn(...)`, hệ thống sẽ gọi `EvaluateTurnCommand`, chấm điểm qua `EvaluationService` và lưu bản ghi vào `answer_evaluations`.
- **Kết luận**: Tracking chỉ được ghi nhận khi:
  1. Turn có `transcribed_text` (hoặc `answer_text`) không rỗng.
  2. Đã có bản ghi chấm điểm tương ứng trong `answer_evaluations` (hoặc kết quả chấm bài từ module tương ứng).
  3. Turn có `question_id` trỏ tới câu hỏi ngân hàng có `skill_ids` (xem mục 5).

---

## 3. THANG ĐIỂM CHUẨN CỦA CÁC MODULE (EXACT SCORE SCALES)

1. **Module Phỏng vấn Mock (`answer_evaluations` & `session_progress_summary`)**:
   - `clarity_score`, `logic_score`, `example_score`, `overall_score`: Lưu kiểu `NUMERIC(4,2)` với giá trị trong đoạn **0.00 đến 10.00** (ràng buộc bởi CHECK constraint `ck_score_* >= 0 AND <= 10`).
   - Công thức chuẩn hóa về thang `[0.0, 1.0]`:
     $$\text{score}_{\text{norm}} = \frac{\text{overall\_score}}{10.0}$$
2. **Module Luyện tập theo bộ đề (`practice_history`)**:
   - `average_score`: Lưu kiểu `NUMERIC(5,2)` trong đoạn **0.00 đến 100.00**.
   - `questions_summary`: mảng JSON các object:
     `{"question_id": int, "question_text": str, "score": float, "passed": bool, "evaluation_ids": [int]}`
     Trường `score` là điểm hiển thị phía client, thang **0.0 đến 100.0**.
   - **Chỉ dùng bằng chứng đã xác minh (P1-3)**: `score` trong `questions_summary` KHÔNG được dùng để ghi `user_skill_evidence`. Evidence chỉ lấy từ bảng `practice_evaluations` — nơi server (LLM evaluator) tự lưu đánh giá kèm câu trả lời thật — thông qua `evaluation_ids`, sau khi kiểm tra đúng `user_id` và đúng `question_id`.
   - Công thức chuẩn hóa bằng chứng:
     $$\text{score}_{\text{norm}} = \frac{\sum \text{part\_score}}{\sum \text{part\_max}} \quad \text{(clamp } [0.0, 1.0] \text{)}$$
     Không còn nhánh "nếu score ≤ 1.0 thì giữ nguyên": mọi điểm practice theo thang 0–100, điểm 1/100 = 1% (trước đây bị hiểu thành 100%).
3. **Module Phỏng vấn theo JD (`interview_scripts`)**:
   - `interview_scripts.items`: Chứa JSON mảng các câu hỏi phỏng vấn được sinh theo JD.
   - Mỗi item chứa tiêu chí đánh giá, độ khó và danh sách kỹ năng mục tiêu.

---

## 4. ĐIỂM KÍCH HOẠT HOÀN TẤT PHIÊN (LIFECYCLE TRIGGERS)

1. **Phỏng vấn trực tiếp (Mock Interview Sessions)**:
   - Trong `submit_turn`: Khi `command.turn_number >= total_configured_turns`, biến `is_completed` trả về `True`.
   - Kết thúc phiên gọi `complete_session(session, command, total_score)`. Trạng thái session chuyển sang `status = 'completed'` và lưu `completed_at`.
   - **Entry point lý tưởng để track kỹ năng**: Hook ngay khi `complete_session` được gọi, hoặc khi turn cuối cùng được chấm điểm thành công.
2. **Luyện tập câu hỏi (`practice_history`)**:
   - Frontend kích hoạt `catalogApi.savePracticeHistory` khi hoàn tất set câu hỏi, gửi payload tới `POST /api/v1/catalog/practice-history`.
   - **Entry point lý tưởng để track kỹ năng**: Ngay trong handler `save_practice_history` sau khi commit bản ghi history.
3. **Liên kết câu hỏi với kỹ năng**:
   - Bảng `question_bank` có cột `skill_ids` (JSON mảng các chuỗi chuẩn hóa, ví dụ `["postgresql", "sql"]`).
   - Tuyệt đối không dùng regex parse text để đoán kỹ năng khi tra cứu. Chỉ trích xuất từ `question_bank.skill_ids` của câu hỏi đã được gán nhãn hoặc tiêu chí cấu trúc sẵn có.

---

## 5. LIÊN KẾT LƯỢT PHỎNG VẤN VỚI NGÂN HÀNG CÂU HỎI (PHASE 2 — LOI #5)

- Mỗi lượt hỏi xuất phát từ ngân hàng câu hỏi phải được gắn `interview_turns.question_id` ngay khi câu hỏi được hỏi:
  - Luồng text: `InterviewService.start_session` (lượt 1) và `submit_turn` (các lượt sau, dùng `stage_configs` để xác định stage).
  - Luồng voice: `VoiceInterviewOrchestrator._persist_ai_turn` (đồng thời đánh dấu `session_question_selections.used_at_turn`).
- Không đoán câu hỏi theo `selection_order`/`turn_number`; khi không xác định được câu hỏi ngân hàng thì để `question_id = NULL` và KHÔNG ghi evidence.
- Câu hỏi sinh từ kịch bản JD (`interview_scripts.items`) không thuộc ngân hàng câu hỏi → `question_id = NULL`.
- Chuỗi voice realtime: câu trả lời được chấm điểm nền (`answer_evaluations`) rồi đồng bộ ngay bằng `UserSkillService.sync_interview_turn`; khi dừng phiên có thêm lượt quét đầy đủ `sync_from_interview_session` (idempotent theo `source_id`).
- Điểm evidence lượt phỏng vấn = `overall_score / 10.0` (thang DB 0–10 → 0–1), `grader_confidence = 0.90`, `input_mode = voice` nếu turn có `audio_url`.
- Test hồi quy: `tests/integration/test_interview_turn_linking.py`.

---

## 6. JEV SYSTEM ONE CHO JOB READINESS (PHASE 3 — LOI #2)

- Endpoint thật: `POST https://api.typesafe.ai/v1/systemone` với body `{model, state, questions}`; response `{model, answers, usage}`. Jev không có kiểu trả lời văn bản tự do — chỉ `score` / `choice` / `noul`.
- `JevSystemOneAdapter` dựng `state` giới hạn (tối đa 12 requirement, JD excerpt 700 ký tự, chỉ kỹ năng thuộc JD) và các câu hỏi:
  - `overall_match`: score 0–9 (API giới hạn tối đa 10 mức điểm) → `match_percent = score / 9 × 100`.
  - `verdict`: choice `ready | almost | not_ready | insufficient_data`.
  - `skill__<skill_id>`: score 0–5 (0 = không có bằng chứng, 3 = đạt yêu cầu) cho tối đa 6 kỹ năng must-have.
- Diễn giải tiếng Việt được soạn cục bộ từ dữ liệu cấu trúc (không thêm một LLM call thứ hai).
- Chỉ gọi khi người dùng bấm kiểm tra một job cụ thể (`POST/GET /api/v1/jobs/{job_id}/readiness`); kết quả cache 2 giờ trong `job_readiness_checks`, `force=true` mới gọi lại. KHÔNG quét toàn bộ user × JD.
- Kết quả Jev ghi đè `match_percent`, `verdict`, `explanation`, `recommended_skills`; trạng thái từng kỹ năng chỉ được HẠ xuống (không nâng) và chỉ với kỹ năng đã có bằng chứng kiểm chứng, để LLM không thể khẳng định một kỹ năng mà dữ liệu nền chưa xác nhận.
- `job_readiness_checks.analysis_engine` lưu `jev` hoặc `heuristic`; UI chỉ ghi "TypeSafe Jev System One" khi Jev thực sự chạy, còn lại hiển thị nhãn thuật toán nội bộ.
- Env: `JEV_API_KEY`, `JEV_API_URL`, `JEV_MODEL` (compose.yaml + .env.example). Key placeholder (`your_jev_api_key`) được coi như chưa cấu hình → fallback heuristic.
- Test: `tests/unit/test_jev_adapter.py`, `tests/unit/test_job_readiness_jev_service.py`, `tests/integration/test_jev_adapter_http.py`, `tests/integration/test_readiness_engine_persistence.py`.
