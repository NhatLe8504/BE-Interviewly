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
  1. Turn có `transcribed_text` (hoặc `answer_text`) không rỗng và độ dài tối thiểu (> 10 ký tự).
  2. Đã có bản ghi chấm điểm tương ứng trong `answer_evaluations` (hoặc kết quả chấm bài từ module tương ứng).

---

## 3. THANG ĐIỂM CHUẨN CỦA CÁC MODULE (EXACT SCORE SCALES)

1. **Module Phỏng vấn Mock (`answer_evaluations` & `session_progress_summary`)**:
   - `clarity_score`, `logic_score`, `example_score`, `overall_score`: Lưu kiểu `NUMERIC(4,2)` với giá trị trong đoạn **0.00 đến 10.00** (ràng buộc bởi CHECK constraint `ck_score_* >= 0 AND <= 10`).
   - Công thức chuẩn hóa về thang `[0.0, 1.0]`:
     $$\text{score}_{\text{norm}} = \frac{\text{overall\_score}}{10.0}$$
2. **Module Luyện tập theo bộ đề (`practice_history`)**:
   - `average_score`: Lưu kiểu `NUMERIC(5,2)` trong đoạn **0.00 đến 100.00**.
   - `questions_summary`: Lưu mảng JSON các object:
     `{"question_id": int, "question_text": str, "score": float, "passed": bool}`
     Trường `score` ở đây nằm trong thang **0.0 đến 100.0** (hoặc 0..1 nếu normalized).
   - Công thức chuẩn hóa về thang `[0.0, 1.0]`:
     $$\text{score}_{\text{norm}} = \begin{cases} \frac{\text{score}}{100.0} & \text{nếu score} > 1.0 \\ \text{score} & \text{nếu score} \le 1.0 \end{cases}$$
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
