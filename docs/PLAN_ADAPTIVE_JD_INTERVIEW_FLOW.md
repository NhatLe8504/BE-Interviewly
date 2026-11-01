# Kế hoạch: Phỏng vấn JD thích ứng với Jev và xác nhận chuyển chặng

Trạng thái: **Đề xuất, chưa triển khai.** Phạm vi: luyện phỏng vấn AI theo kịch bản sinh từ JD, áp dụng cho cả giọng nói và văn bản. Tài liệu này không thay đổi logic hiện tại.

## 1. Mục tiêu và nguyên tắc

- Kịch bản JD là nguồn câu hỏi và các năng lực cần kiểm tra; cuộc phỏng vấn phải bám vào câu trả lời thực tế, không đọc máy móc hết danh sách.
- Trong mỗi câu hỏi: hỏi chính → nghe/nhận câu trả lời hoàn chỉnh → đánh giá → hỏi sâu vào điểm chưa rõ → đánh giá lại → chuyển câu khi đã đủ hoặc khi đào sâu thêm không còn hiệu quả.
- Chuyển **câu hỏi** khác với chuyển **chặng**. Đủ số lượt, hết giờ hoặc Jev báo sẵn sàng đều không cho phép tự chuyển chặng hay tự kết thúc.
- Không cắt lời ứng viên; không thay đổi chặng khi transcript chưa hoàn chỉnh, AI đang nói, âm thanh đang phát hoặc đang chờ người dùng xác nhận.
- Jev đưa ra đánh giá có cấu trúc; LLM sử dụng tín hiệu ấy để trò chuyện tự nhiên. Backend kiểm soát trạng thái và tính hợp lệ; ứng viên quyết định có chuyển chặng hoặc kết thúc hay không.
- Giữ tỷ lệ thời gian **1:4:1**. Phiên 60 phút tương ứng 10 phút khởi động, 40 phút chuyên môn, 10 phút chào kết. Mốc thời gian là ngưỡng điều phối mềm, không phải lệnh cắt ngang.

## 2. Hiện trạng cần thay đổi

- `app/application/voice/orchestrator.py`: `get_target_turns_for_current_stage()` và `handle_final_transcript()` đang ưu tiên đủ lượt để tự chuyển chặng; chặng cuối cũng có thể tự kết thúc. Chỉ nhánh quá mốc thời gian mới đề xuất để ứng viên xác nhận.
- `_resolve_next_intent()` so sánh trực tiếp `section_type` của kịch bản JD với `warmup|technical|closing`, trong khi script có `introduction|technical|scenario|system_design|role_specific|behavioral|closing`. Chọn câu bằng `turns_in_current_stage // 2` và fallback sang mục bất kỳ không đảm bảo bao phủ hoặc tránh lặp.
- Chấm điểm câu trả lời đang chạy nền, chưa cung cấp kịp kết quả cho quyết định hỏi sâu hay chuyển câu.
- `app/infrastructure/llm/jev_adapter.py` hiện phục vụ job readiness thông qua `app/application/skills/service.py`; không dùng rubric đánh giá độ phù hợp với job để chấm một lượt phỏng vấn.
- FE `src/app/(user)/practice/setup/[interviewId]/setupPlan.ts` mặc định 1/2/1 lượt, tổng tối đa 5 lượt. `src/hooks/useRealtimeVoiceInterview.ts` gửi thời lượng và cấu hình qua `client_ready`, còn metadata thời lượng lưu trong `sessionStorage`. Backend phải là nguồn dữ liệu chính để reconnect không đặt lại đồng hồ hoặc tiến độ.
- FE `src/app/(user)/practice/[sessionId]/page.tsx` chỉ hiện nút xác nhận khi nhận `stage_transition_proposed`; nhánh BE tự chuyển hiện không phát đề xuất đó.

## 3. Hợp đồng dữ liệu cho kế hoạch JD

- Tạo snapshot bất biến khi bắt đầu phiên: `stage_id`, `item_id`, `section_type`, `question_text`, `competency`, `required`, `order`, `expected_signals`. Không chỉnh script gốc giữa phiên.
- Ánh xạ `introduction` → `warmup`; `technical|scenario|system_design|role_specific|behavioral` → `technical`; `closing` → `closing`. Giới thiệu bản thân, kinh nghiệm, động lực, điểm mạnh/yếu thuộc khởi động nếu kế hoạch có các mục đó. Không kéo câu chuyên môn vào khởi động.
- Nếu script thiếu mục cho một chặng, dùng câu mở đầu/kết thúc phù hợp và đánh dấu `source=fallback`; không lấy ngẫu nhiên câu của chặng khác. Nếu chỉ chọn một số chặng, không tạo chặng ngoài plan.
- Tách `question_completion` (đã xử lý câu đến mức hợp lý) khỏi `competency_coverage` (chất lượng bằng chứng về năng lực). Một item có thể `completed_unresolved`: ứng viên chưa thể hiện tốt nhưng đã được hỏi sâu hợp lý. Vẫn cho phép hoàn thành buổi phỏng vấn.
- Theo dõi `not_asked|asked|probing|completed_covered|completed_unresolved|skipped_with_reason`, transcript/bằng chứng và số lần hỏi sâu. Lưu `accumulated_evidence` theo `item_id` và `expected_signal`: trạng thái `missing|partial|supported|strong|uncertain` (bốn mức đầu tương ứng score 0–3; `uncertain` do BE gán khi kết quả không đủ tin cậy), trích dẫn/ID các lượt trả lời tạo bằng chứng, thời điểm cập nhật. Không để lượt trả lời sau làm mất bằng chứng đã xác thực ở lượt trước; khi mâu thuẫn, đánh dấu cần làm rõ thay vì tự ghi đè. Câu hỏi phụ không tính là câu chính đã hỏi.
- Phân biệt mục bắt buộc với tùy chọn từ đầu. Kịch bản quá dài so với thời lượng phải được thu gọn và cho người dùng xem trước; không âm thầm bỏ qua giữa phiên. `max_turns`/giới hạn 5 lượt hiện tại không được dùng để tự chuyển chặng hoặc chặn follow-up hợp lý.

## 4. `InterviewTurnJudge` theo System One của TypeSafe AI

### 4.1. Ranh giới trách nhiệm và giao thức thật

- Jev là **System One model cho quyết định có cấu trúc**, không phải LLM sinh văn bản. Thêm port `InterviewTurnJudge` trong application và adapter tại infrastructure; tái sử dụng transport/xác thực System One hiện có, nhưng **không** tái sử dụng rubric `evaluate_readiness()` cho job. Không yêu cầu Jev sinh JSON tùy ý, lời nhận xét, trích dẫn, `probe_target` hoặc câu hỏi tiếp theo.
- Gọi `POST /v1/systemone` với `model`, `state` (string/object/array) và `questions` là object các câu hỏi có tên. Một request có thể trộn `choice`, `score`, `noul`; response chứa `model`, `answers` theo đúng tên câu hỏi và `usage`. Kiểm tra type và khóa câu hỏi trả về trước khi dùng.
- `Choice`: `criteria` là object tên lựa chọn → mô tả; đáp án có `choice`, `confidence`, `probabilities`. `Score`: `criteria` là **mảng mô tả mức có thứ tự**, tối đa 10 mức; các mức bắt đầu từ 0 (response `score` có thể là số thực), response có `score`, `confidence`, `legend`, `probabilities`. `Noul`: trả `noul` là xác suất đúng/có từ 0 đến 1; **không có trường `confidence` riêng**. Các ngưỡng hành động cần hiệu chỉnh bằng mẫu dữ liệu thật, không coi 0,5 là khẳng định hoặc gán một ngưỡng tùy tiện ngay trong plan.
- Tham khảo schema chính thức: `https://api.typesafe.ai/openapi.json` (`SystemOneRequest`, `SystemOneResponse`, `ChoiceQuestion`, `ScoreQuestion`, `NoulQuestion` và các Answer tương ứng). Hướng dẫn primitive: `https://docs.typesafe.ai/primitives/choice`, `https://docs.typesafe.ai/primitives/score`, `https://docs.typesafe.ai/primitives/noul`. Đây là thiết kế theo schema đã đối chiếu, không phải kết quả benchmark độ trễ.

### 4.2. Một request cho nhiều tiêu chí của một lượt trả lời

- Sau transcript final, tạo `state` nhỏ gồm `item_id`, câu hỏi chính, các `expected_signals`, `accumulated_evidence` theo signal, những lượt hỏi đáp liên quan và câu trả lời mới. Chỉ gửi thông tin cần cho item hiện tại; chặn kích thước và số signal theo cấu hình, không gửi toàn bộ JD/CV/transcript hoặc ghi log PII/khóa API.
- Tạo các named questions trong **cùng một request**: một `score` 0–3 cho mỗi signal cần kiểm tra (`missing`, `partial`, `supported`, `strong`); một `choice` cho trạng thái câu trả lời (`responsive`, `needs_clarification`, `cannot_answer`, `off_topic`); và `noul` chỉ cho mệnh đề nhị phân quan sát được, ví dụ “ứng viên **nói rõ** không còn gì để bổ sung cho câu này?”. Không dùng `noul` để khẳng định suy đoán rằng ứng viên thực sự hết ý.
- Payload minh họa đúng dạng API; tên/mô tả signal lấy từ snapshot plan, không để người dùng nhập trực tiếp thành tên khóa chưa kiểm tra:

```json
{
  "model": "jev-latest",
  "state": {
    "item_id": "jd-item-3",
    "question": "Bạn đã xử lý hiệu năng dịch vụ như thế nào?",
    "expected_signals": ["strategy", "measurement"],
    "accumulated_evidence": {"strategy": {"status": "supported", "turn_ids": [7]}},
    "latest_answer": "Tôi đo latency trước và sau khi thêm cache."
  },
  "questions": {
    "signal__measurement": {
      "type": "score",
      "instructions": "Đánh giá bằng chứng đo lường trong toàn bộ state, kể cả câu trả lời trước.",
      "criteria": ["Không có bằng chứng", "Chỉ nhắc tên", "Có phương pháp đo cụ thể", "Có phương pháp và kết quả kiểm chứng"]
    },
    "answer_disposition": {
      "type": "choice",
      "criteria": {
        "responsive": "Trả lời đúng chủ đề",
        "needs_clarification": "Có ý liên quan nhưng chưa rõ",
        "cannot_answer": "Nói rõ là không biết hoặc không thể trả lời",
        "off_topic": "Không liên quan câu hỏi"
      }
    },
    "explicitly_no_more_to_add": {
      "type": "noul",
      "instructions": "Ứng viên có nói rõ họ không còn điều gì để bổ sung cho câu hỏi này không?"
    }
  }
}
```

- Adapter parse `answers.signal__measurement.score/confidence/probabilities`, `answers.answer_disposition.choice/confidence/probabilities` và `answers.explicitly_no_more_to_add.noul`; không đọc `choices[0].message.content` hoặc `response.text`. Nếu thiếu khóa, sai type, ngoài miền hoặc mức tin cậy không đạt ngưỡng đã hiệu chỉnh, đánh dấu `uncertain` và áp dụng fallback; không tự suy diễn câu trả lời dạng văn bản từ Jev.
- Hợp nhất điểm mới với `accumulated_evidence` theo `item_id` và `expected_signal`; giữ tham chiếu `turn_id` cho bằng chứng đã xác thực, phát hiện mâu thuẫn để hỏi lại. Jev không cung cấp đoạn trích bằng chứng: backend chỉ gắn transcript/turn đã có, không tạo lời trích giả. Kết quả turn-level không phải điểm tổng của ứng viên.

### 4.3. Quyết định và đường đi nhanh

- Backend chuyển `Score`/`Choice`/`Noul` thành `next_action=probe|next_item|clarify|continue` bằng rule có thể kiểm thử. `probe_target` chọn từ signal bắt buộc còn thiếu theo thứ tự ưu tiên trong plan; Jev không phải sinh mục tiêu bằng free text. Nếu đã đủ bằng chứng, chuyển item không hỏi sâu. Nếu còn thiếu, LLM dùng signal, câu trả lời và lịch sử để **diễn đạt một follow-up ngắn, cụ thể**; không thêm một LLM call chỉ để “giải thích kết quả Jev”.
- Nếu câu hỏi tiếp theo đã có trong JD, dùng nguyên câu từ snapshot; lời dẫn/nối chặng có thể dùng template hoặc LLM khi thật sự cần ngữ cảnh tự nhiên. Jev và BE chọn hành động trước, LLM chỉ sinh lời nói khi cần. Không gọi Jev theo audio chunk, khi không có transcript mới, hoặc gọi lại cấp chặng chỉ để nhắc lại các quyết định đã có.
- Jev được gọi một lần sau mỗi câu trả lời final và có thể trả nhiều tiêu chí cùng lúc; giới hạn số câu hỏi trong payload theo ngân sách nội bộ, không tự nhận đây là giới hạn API. Dùng client bất đồng bộ hoặc đưa I/O đồng bộ ra thread để không chặn event loop; timeout/budget, retry giới hạn và theo dõi `usage`, độ trễ, tỉ lệ lỗi/fallback. Không khẳng định latency cụ thể trước khi đo trên dữ liệu thực.
- Khi Jev thiếu key, timeout hoặc trả schema không hợp lệ, BE giữ tiến độ/câu hiện tại, dùng giới hạn probe và trạng thái plan để tiếp tục; có thể hỏi rõ ứng viên hoặc chuyển item với `completed_unresolved` sau giới hạn, **không tự chuyển chặng**. Kết quả Jev đến muộn bị loại theo versioning mục 6. Chấm điểm báo cáo sau phiên là luồng riêng.

## 5. Điều kiện chuyển chặng và kết thúc

- Gate cấp chặng do **BE tổng hợp** từ `question_completion`: mọi item bắt buộc đã `completed_covered` hoặc `completed_unresolved` có lý do sau khi hỏi sâu; không bắt ứng viên phải trả lời giỏi hoặc có đủ mọi năng lực. `competency_coverage` dùng cho báo cáo và chọn điểm cần hỏi sâu, không phải điều kiện khóa chặng. Chưa cần một phán quyết Jev thứ hai ở cấp chặng.
- Chỉ xét gate tại ranh giới an toàn: transcript final đã xử lý, không còn item/câu trả lời đang mở, media ổn định và phiên còn active. Thời lượng 1:4:1 là mục tiêu mềm: đủ nội dung và đạt mốc → đề xuất; đủ nội dung trước mốc → trao đổi mở rộng có giá trị hoặc cho ứng viên **chủ động xin chuyển sớm** và xác nhận; đạt mốc mà còn mục bắt buộc → đề nghị tiếp tục quá giờ hoặc bỏ qua mục còn lại sau xác nhận, ghi lý do. Không hỏi lan man để câu giờ, không kéo dài vô hạn hoặc tự bỏ qua.
- Đến mốc thời gian khi ứng viên đang nói/AI đang phát: không ngắt. Hết tổng thời lượng: hiện lựa chọn tiếp tục quá giờ hoặc kết thúc sau khi khép lượt hiện tại. Mất kết nối và làm tròn mốc thời gian cần chính sách rõ ở mục 9.
- Khi đủ điều kiện hoặc có yêu cầu chuyển sớm hợp lệ, BE phát `stage_transition_proposed` với `proposal_id`, `stage_version`, `from_stage`, `to_stage`, `reason_codes`, tiến độ item và `source`. LLM tạo lời nối tự nhiên, hỏi ứng viên đã sẵn sàng chưa; state vẫn thuộc chặng cũ khi chờ xác nhận.
- Bấm/nói đồng ý → BE kiểm tra proposal còn hiệu lực, cập nhật stage đúng một lần, bắt đầu timer mới rồi mới sinh câu đầu chặng mới. “Nói thêm” → giữ chặng và tiếp tục chủ đề ứng viên chọn. Không gọi `handle_next_stage()` trực tiếp nếu không có proposal hợp lệ, trừ thao tác bỏ qua thủ công đã xác nhận rõ ràng.
- Khởi động → chuyên môn: hỏi sẵn sàng vào chuyên môn chưa. Chuyên môn → chào kết: tóm tắt ngắn và hỏi có muốn sang phần thắc mắc không. Ở chào kết, hỏi thắc mắc về công việc/phần tech; chỉ lưu `completed` sau khi ứng viên xác nhận đã xong hoặc bấm “Kết thúc”.

## 6. Trạng thái, sự kiện, lưu trữ và UI

- Tách hai lớp: **interview state** `asking|waiting_answer|judging|awaiting_confirmation|changing_stage|awaiting_end_confirmation|stopping|completed`; **media state** `idle|generating_audio|playing_audio|listening|finalizing_transcript`. `probe`/`next_item` là hành động được chọn sau judging, không tự thay thế trạng thái phiên. Voice và text cùng interview state; text bỏ qua những media state không áp dụng.
- Chỉ đánh giá khi transcript của lượt hiện tại đã final. Mặc định chỉ mở lượt nghe sau khi phát xong audio; barge-in nếu bật là nhánh có kiểm soát: dừng audio hiện tại, vô hiệu hóa generation cũ, nhận transcript mới rồi mới quyết định. Phải có ACK phát xong (`playback_completed`) với `generation_id`, timeout/recovery khi ACK mất; không suy ra người dùng đã nghe từ sự kiện BE sinh xong TTS.
- Backend lưu snapshot plan, `accumulated_evidence`, `question_completion`, `stage_id`, `stage_version`, thời gian đã hoạt động, mốc pause/resume, `pending_proposal_id`, `item_id`, số lần probe, `last_processed_turn_id`, trạng thái media có thể khôi phục và `source=jev|fallback`. Reconnect lấy snapshot từ BE; không tự khởi động lại warmup hoặc phát trùng câu cũ. Nếu mất kết nối lúc phát TTS, xác định câu đã phát tới đâu/cho phát lại có kiểm soát rồi mới mở nghe.
- Mỗi kết quả Jev, transcript, ACK media và proposal mang `session_id`, `stage_version`, `item_id`, `turn_id` cùng `generation_id` khi có media; proposal còn có `proposal_id`. Trước **mọi** thay đổi state, BE so sánh các giá trị đó với state hiện hành và thực hiện chuyển trạng thái idempotent. Kết quả đến muộn chỉ dùng cho telemetry, không tạo câu mới hay làm sống lại phiên đã kết thúc; proposal cũ bị từ chối sau chuyển chặng.
- FE hiển thị tiến độ chặng/kế hoạch, thời gian tham chiếu và proposal ở vị trí dễ thấy, không chỉ trong bubble cũ. Tách nút “Đồng ý”, “Nói thêm”, “Kết thúc”; khóa thao tác trùng khi judging/chuyển chặng. Sau reconnect, FE đồng bộ từ snapshot BE trước khi cho gửi transcript hoặc xác nhận proposal.
- LLM chỉ nhận hành động tiếp theo và `probe_target` do BE cấp; không được tự tuyên bố chuyển chặng, kết thúc hoặc hỏi chuyên môn trong warmup. Không để lời nói của LLM hoặc tín hiệu Jev trực tiếp sửa state.

## 7. Thứ tự triển khai thành các phần nhỏ

1. Tạo snapshot plan JD, ánh xạ section → chặng, required/optional; bỏ fallback lấy câu sai chặng. Commit BE riêng.
2. Tách `question_completion` và `competency_coverage`; lưu evidence tích lũy theo item/signal và tiến độ qua reconnect. Commit BE riêng.
3. Lưu duration, đồng hồ hoạt động/pause và stage version ở BE; giữ tỷ lệ 1:4:1. Commit BE riêng.
4. Định nghĩa interview/media state, giao thức ACK playback, barge-in và chống event cũ; kiểm chứng reconnect trước khi tích hợp Jev. Tách commit BE và FE theo phạm vi.
5. Tạo port/adapter Jev turn-level theo `state + named questions → answers`, hợp nhất evidence, timeout/fallback; kiểm chứng bằng System One stub, không thêm LLM call phân tích. Commit BE riêng.
6. Triển khai vòng hỏi sâu giới hạn và chọn `next_action`; tách tiến độ item khỏi đếm lượt. Commit BE riêng.
7. Triển khai gate deterministic cấp chặng, ngoại lệ chuyển sớm/overtime, proposal và xác nhận idempotent; bỏ auto-stage/auto-finish. Commit BE riêng.
8. Đồng bộ FE: tiến độ, proposal dễ thấy, xác nhận voice/text, kết thúc và reconnect UX; commit nhỏ theo component/luồng.
9. Kiểm tra local với JD và không JD; rollout bằng feature flag, quan sát độ trễ/chi phí/fallback. Chỉ sau đó merge/push theo quy tắc project; không sửa code trực tiếp trên VPS.

## 8. Tiêu chí nghiệm thu

- Phiên 60 phút có mốc 10/40/10; thời lượng khác theo 1:4:1. Reload không đặt lại đồng hồ hoặc tiến độ; thời gian mất kết nối được xử lý theo chính sách đã chốt.
- Câu trả lời đầy đủ ngay lượt đầu → không hỏi sâu thừa. Thiếu trade-off → hỏi đúng trade-off. Follow-up bổ sung đúng evidence → các signal đã đạt từ lượt trước vẫn được giữ, item hoàn tất và chuyển câu tiếp.
- Mock response System One đúng từng primitive: `Choice` có `choice/confidence/probabilities`, `Score` có `score/confidence/legend/probabilities`, `Noul` chỉ có `noul`; thiếu khóa, sai type hoặc không chắc chắn → `uncertain`/fallback. Một lượt trả lời chỉ tạo một request Jev chứa các tiêu chí cần thiết, không thêm LLM call để parse/phán quyết.
- Jev đánh giá thấp nhưng đã hết probe → `completed_unresolved`, không kẹt câu/chặng. Đủ lượt nhưng còn item bắt buộc chưa xử lý → không đề xuất. Ứng viên yếu vẫn có thể hoàn thành buổi phỏng vấn với báo cáo trung thực.
- Đủ plan trước mốc → trao đổi có giá trị hoặc chuyển sớm **khi ứng viên chủ động yêu cầu và xác nhận**. Hết mốc nhưng thiếu plan → lựa chọn overtime/bỏ qua có xác nhận và lý do. Đến mốc khi ứng viên nói hoặc TTS đang phát → không ngắt.
- Đủ điều kiện → chỉ hiện đề xuất, không đổi chặng trước khi đồng ý. “Nói thêm” giữ chặng; xác nhận lặp chỉ chuyển một lần. Chỉ chọn technical → không tạo warmup ngoài plan.
- Kết quả Jev đến sau khi người dùng kết thúc, proposal từ stage version cũ hoặc `playback_completed` cũ → không thay đổi state. Mất mạng khi TTS đang phát → không sinh câu hỏi trùng; reload lúc chờ xác nhận → khôi phục proposal hợp lệ.
- Closing có thắc mắc → tiếp tục; không còn → xác nhận kết thúc, không redirect trước khi lưu `completed`. Jev timeout/thiếu key/sai schema toàn phiên → vẫn phỏng vấn và kết thúc an toàn, không tự chuyển.
- Script JD có `scenario|system_design|behavioral` không mất/lặp vì ánh xạ sai. JD nhiều item hơn thời lượng có thể xử lý → yêu cầu thu gọn trước phiên. Unit kiểm tra state/gate/evidence; integration kiểm tra persistence/Jev stub; acceptance kiểm tra WebSocket voice/text, barge-in, reconnect, proposal, defer, confirm và manual end. Không tự chạy build/headless preview khi chưa được yêu cầu.

## 9. Chính sách cần xác nhận trước khi code

- **Item bắt buộc:** Đề xuất generator gắn nhãn theo năng lực/JD; người dùng xem và chỉnh trước khi bắt đầu. Chưa chốt thuật toán chọn số lượng item theo thời lượng.
- **Chuyển sớm:** Đề xuất chỉ khi đã xử lý item bắt buộc, ứng viên chủ động xin chuyển, không có lượt trả lời đang mở và xác nhận proposal; không để BE/LLM tự đề nghị chuyển sớm chỉ vì thiếu chuyện để hỏi.
- **Overtime:** Khi hết mốc mà còn item bắt buộc, hỏi người dùng tiếp tục quá giờ hoặc bỏ qua item chưa xử lý với xác nhận và lý do; không bỏ qua im lặng. Khi hết tổng thời lượng, vẫn cho khép lượt hiện tại trước khi hỏi lựa chọn. Cần chốt giới hạn overtime tối đa và cách phân bổ lại mốc các chặng còn lại.
- **Mất kết nối:** Đề xuất tạm dừng đồng hồ khi WS thực sự ngắt, tính thời lượng hoạt động khi kết nối và tiếp tục từ snapshot BE lúc reconnect; không tính thời gian mất mạng vào 1:4:1. Cần chốt timeout vắng mặt bao lâu thì phiên tạm dừng/hết hạn, và xử lý audio phát dang dở.
- **Giới hạn hỏi sâu:** Đề xuất tối đa hai follow-up/item, điều chỉnh theo chế độ/cấp độ; thêm lượt nếu ứng viên chủ động yêu cầu. Đến giới hạn vẫn thiếu năng lực thì `completed_unresolved`, không giữ mãi một câu.
- **Jev lỗi và ngưỡng quyết định:** Đề xuất fallback theo plan và xác nhận ứng viên khi đã đến mốc, ghi `source=fallback`; không tự chuyển. Hiệu chỉnh ngưỡng `confidence`/`probabilities` và `noul` trên tập hội thoại mẫu trước khi rollout; không gán một ngưỡng tùy tiện. Không yêu cầu Jev thứ hai ở cấp chặng trong phiên bản đầu.
- **Phiên rất ngắn:** Cần chốt thời lượng tối thiểu và cách làm tròn 1:4:1 để chặng đầu/cuối vẫn đủ thời gian trò chuyện có ý nghĩa.
