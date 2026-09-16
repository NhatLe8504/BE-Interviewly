# NHIỆM VỤ CHI TIẾT DÀNH CHO: LÊ VĂN NHẬT (Project Manager / Backend Lead / AI Dev)

- **Mã sinh viên:** 28218044202
- **Email:** `nhatle08052004n@gmail.com`
- **Git Branch:** `nhatle08052004n`
- **Worktree BE:** `D:\DOANNHATLE\Interview_Coach_SRC_CODE\BE`
- **Worktree FE:** `D:\DOANNHATLE\Interview_Coach_SRC_CODE\FE`

---

## ⚠️ QUY TẮC BẮT BUỘC TRƯỚC KHI BẮT ĐẦU (GIT IDENTITY & WORKTREE)

1. Mở đúng thư mục worktree được phân công:
   - Backend: `D:\DOANNHATLE\Interview_Coach_SRC_CODE\BE`
   - Frontend: `D:\DOANNHATLE\Interview_Coach_SRC_CODE\FE`
2. Kiểm tra branch hiện tại:
   ```bash
   git branch --show-current
   ```
   *Kết quả phải đúng là: `nhatle08052004n`*
3. Cấu hình danh tính Git chính xác:
   ```bash
   git config user.name "nhatle08052004n"
   git config user.email "nhatle08052004n@gmail.com"
   ```
4. **Tuyệt đối KHÔNG commit trực tiếp lên nhánh `main`.** Chỉ push lên `nhatle08052004n` và tạo PR sang `main`.
5. 🛑 **QUY TẮC COMMIT & HỎI Ý KIẾN USER (BẮT BUỘC):**
   - Mỗi khi hoàn thành xong bất kỳ một task nhỏ hay bước nào (ví dụ: tạo xong entity, viết xong 1 service, pass 1 bộ test):
     - **TUYỆT ĐỐI KHÔNG TỰ Ý COMMIT NGAY.**
     - Chạy test kiểm tra trước (`pytest -q`).
     - Báo cáo ngắn gọn cho User: đã làm được gì, thay đổi những file nào, kết quả test ra sao.
     - **Hỏi ý kiến User:** *"Tôi đã hoàn thành task nhỏ này và test đã pass. Bạn có đồng ý để tôi commit không?"*
     - **CHỈ KHI USER XÁC NHẬN ĐỒNG Ý** mới được thực hiện `git add`, `git commit` và tạo PR!

---

## 🎯 PHẠM VI NHIỆM VỤ CỦA BẠN

Bạn chịu trách nhiệm về **Kiến trúc Backend, Động cơ Phỏng vấn AI Đa lượt (Multi-turn SSE), Động cơ Chấm điểm Rubric, và Thuật toán Phân tích Giọng nói**.

### Danh mục File cần triển khai trong `reference_app/app/`:

```text
reference_app/app/
├── domain/
│   ├── interview.py             # Entity: InterviewSession, InterviewTurn, enums trạng thái, validation rules
│   ├── evaluation.py            # Value Object: RubricScore (0-100), StarAnalysis, ActionableFeedback
│   └── speech.py                # Value Object: SpeechQualityMetrics, WpmCalculation, FillerWordRecord
├── application/
│   ├── interview/
│   │   ├── commands.py          # StartSessionCommand, SubmitTurnCommand, CompleteSessionCommand
│   │   ├── ports.py             # InterviewSessionRepoPort, InterviewTurnRepoPort, LLMInterviewerPort
│   │   └── service.py           # InterviewService (quản lý lịch sử hội thoại, prompt injection, follow-up logic)
│   ├── evaluation/
│   │   ├── commands.py          # EvaluateTurnCommand, GenerateSessionSummaryCommand
│   │   ├── ports.py             # EvaluationRepoPort, RubricEvaluatorPort
│   │   └── service.py           # EvaluationService (gọi LLM chấm điểm theo JSON Schema cố định)
│   └── speech/
│       ├── ports.py             # SpeechQualityPort
│       └── service.py           # SpeechQualityService (thuật toán WPM, regex đếm từ đệm đa ngữ)
├── infrastructure/
│   ├── llm/
│   │   ├── prompt_templates.py  # System prompts chuẩn hóa: Người phỏng vấn AI & Giám khảo chấm Rubric
│   │   ├── openai_adapter.py    # Adapter gọi OpenAI API (hỗ trợ async streaming generator SSE)
│   │   └── claude_adapter.py    # Adapter Anthropic Claude SDK (fallback)
│   ├── speech/
│   │   └── text_analyzer.py     # Parser bóc tách từ đệm tiếng Việt ("à", "ừm", "kiểu là") & tiếng Anh ("um", "like")
│   └── persistence/
│       ├── session_repository.py     # SqlAlchemySessionRepository (CRUD interview_sessions, turns)
│       └── evaluation_repository.py  # SqlAlchemyEvaluationRepository (CRUD answer_evaluations, summary)
└── presentation/api/
    ├── routers/
    │   ├── interview.py         # POST /sessions, POST /sessions/{id}/turns, GET /sessions/{id}/stream
    │   └── evaluation.py        # GET /sessions/{id}/turns/{turn_id}/evaluation, GET /sessions/{id}/result
    └── schemas/
        ├── interview.py         # StartSessionIn, TurnSubmitIn, SessionOut, TurnOut (Pydantic v2)
        └── evaluation.py        # RubricEvaluationOut, SessionResultOut, SpeechMetricsOut
```

---

## 📋 CÁC BƯỚC THỰC HIỆN CHI TIẾT THEO THỨ TỰ ƯU TIÊN

### Bước 1: Domain Entities & Invariants (Thuần Python, không framework)
1. Tạo `app/domain/interview.py`:
   - Định nghĩa dataclass `InterviewSession`: `session_id`, `user_id`, `domain_id`, `role_id`, `level`, `language`, `status` (`in_progress`, `completed`, `abandoned`).
   - Định nghĩa `InterviewTurn`: `turn_id`, `session_id`, `turn_number`, `question_text`, `answer_text`, `duration_seconds`.
2. Tạo `app/domain/evaluation.py`:
   - Định nghĩa `RubricScores`: `clarity` (0-100), `structure` (0-100), `evidence` (0-100).
   - Invariant: kiểm tra điểm số bắt buộc từ 0 đến 100 trong `__post_init__`.
3. Tạo `app/domain/speech.py`:
   - Định nghĩa `WpmMetrics`: `wpm` (float), `pause_duration` (float), `filler_count` (int), `filler_words` (list[str]).

### Bước 2: Infrastructure LLM Adapter & Prompts
1. Tạo `app/infrastructure/llm/prompt_templates.py`:
   - Prompt cho AI Interviewer: Đóng vai người phỏng vấn chuyên nghiệp theo Role/Level, hỏi sâu vào câu trả lời trước, không trả lời thay ứng viên.
   - Prompt cho Rubric Evaluator: Bắt buộc trả về đúng định dạng JSON:
     ```json
     {
       "clarity_score": 85,
       "structure_score": 75,
       "evidence_score": 80,
       "star_analysis": {"situation": true, "task": true, "action": false, "result": false},
       "feedback": "...",
       "sample_better_answer": "..."
     }
     ```
2. Tạo `app/infrastructure/llm/openai_adapter.py`:
   - Hàm `stream_question()`: Trả về async generator từng token chữ để phục vụ SSE.
   - Hàm `evaluate_answer()`: Sử dụng OpenAI Structured Outputs / JSON mode để parse ra `RubricScores`.

### Bước 3: Application Services & Ports
1. Tạo `app/application/interview/service.py`:
   - `start_session(cmd)`: Tạo bản ghi phiên phỏng vấn mới, sinh câu hỏi mở đầu.
   - `submit_turn(cmd)`: Lưu câu trả lời, kích hoạt chấm điểm ngầm, quyết định sinh câu hỏi follow-up hoặc kết thúc phiên.
2. Tạo `app/application/evaluation/service.py`:
   - `evaluate_turn()`: Gọi LLM adapter chấm điểm rubric và lưu vào bảng `answer_evaluations`.
   - `generate_session_summary()`: Tính điểm trung bình toàn phiên và xếp loại.
3. Tạo `app/application/speech/service.py`:
   - Thuật toán tính Effective WPM: `(tổng số từ / (thời gian nói - thời gian ngập ngừng)) * 60`.
   - Bóc tách từ đệm tiếng Việt (`à`, `ừm`, `kiểu là`, `thì là mà`) và tiếng Anh (`uh`, `um`, `like`, `you know`).

### Bước 4: Presentation Routers & SSE Streaming
1. Tạo `app/presentation/api/routers/interview.py`:
   - `POST /api/v1/interviews/sessions` -> Khởi tạo phiên, trả về `session_id`.
   - `GET /api/v1/interviews/sessions/{id}/stream` -> Trả về Server-Sent Events (`text/event-stream`) streaming câu hỏi AI.
   - `POST /api/v1/interviews/sessions/{id}/turns` -> Gửi câu trả lời của ứng viên, nhận lượt tiếp theo.
2. Tạo `app/presentation/api/routers/evaluation.py`:
   - `GET /api/v1/interviews/sessions/{id}/result` -> Trả về bảng điểm tổng kết toàn phiên cho Frontend hiển thị.
3. Cập nhật `app/bootstrap.py` để wire toàn bộ services vào `ServiceContainer`.

### Bước 5: Viết Test & Đảm bảo kiến trúc
1. Chạy test kiến trúc:
   ```bash
   pytest tests/architecture/test_dependency_rule.py
   ```
2. Viết unit test cho `InterviewService` và `EvaluationService` trong `tests/unit/`.
3. Viết acceptance test cho luồng phỏng vấn trong `tests/acceptance/test_interview_api.py`.
4. Chạy toàn bộ test đảm bảo xanh 100%:
   ```bash
   pytest -q
   ```

---

## 🚀 QUY TRÌNH ĐẨY CODE (PULL REQUEST)
```bash
git status
git add .
git commit -m "feat(ai-engine): implement multi-turn interview sse and rubric evaluation"
git push -u origin nhatle08052004n
gh pr create --base main --head nhatle08052004n --title "feat(ai-engine): Multi-turn SSE and Rubric Evaluator" --body "Implement core interview sessions, SSE streaming endpoint, rubric scoring and speech analyzer."
```
