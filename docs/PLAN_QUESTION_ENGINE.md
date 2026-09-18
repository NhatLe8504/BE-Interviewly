# PLAN BE — Interview Question Engine: Dynamic, Bank-backed, Moderation-gated

> Muc tieu: nguoi dung tuy chinh sau hon (so luot hoi, chon cau hoi, random tu ngan hang),
> AI KHONG doc nguyen van cau hoi trong ngan hang ma hoi theo tinh huong.
> Pham vi: worktree BE `nhatle08052004n` — `Interview_Coach_SRC_CODE/BE/reference_app`.

---

## 1. Hien trang (da khao sat)

### Da co san — giu nguyen
- `QuestionBank` ORM model (`app/infrastructure/persistence/models/catalog.py`): domain_id, role_id,
  experience_level, language, question_type, question_text, star_template_id, is_active, created_by.
- Catalog router: `GET /api/v1/catalog/questions` (da co filter/search), `GET /questions/{id}`.
- Admin router: `POST /api/v1/admin/questions` (tao cau hoi thu cong), update.
- `ModerationLog` (`models/system.py`) chi ghi log hanh dong admin — CHUA gan vao question.
- `InterviewService` (`app/application/interview/service.py`): `MAX_INTERVIEW_TURNS = 5` HARD-CODED,
  `start_session` luon goi `llm.generate_first_question` tu role/level (khong dung ngan hang),
  `submit_turn` -> `generate_follow_up` (khong co context cau hoi goc).
- Voice Orchestrator (`app/application/voice/orchestrator.py`): da co `selected_stages` +
  `questions_per_stage` (so turn co dinh, client dat truoc) nhung KHONG lien quan den ngan hang cau hoi.
- `schema.sql` o BE root: phan anh schema hien tai (chua co moderation status).

### Dang do dang / thieu (can lam)
- Chua co trang thai kiem duyet (pending/approved/rejected) tren `question_bank`.
- Chua co "practice do nguoi dung tao" (user-generated Job practice) lien ket voi bo cau hoi AI sinh ra.
- Chua co bo phan chon mau (sampling) cau hoi theo stage + dieu kien loc.
- AI chua nhan "intent" cua cau hoi goc de paraphrase theo tinh huong — luon hoi y nguyen cau mac dinh.

---

## 2. Nguyen tac thiet ke (bat buoc)

1. **Intent separation**: moi cau hoi trong ngan hang la `intent` (chu de/ky nang can danh gia).
   AI chi nhan intent + chi dan `paraphrase theo tinh huong hoi thoai, khong doc nguyen van`.
2. **Moderation gate**: chi cau hoi `approved` moi duoc xuat hien trong flow auto-random.
   - Ngan hang he thong / admin tao -> admin duyet.
   - Ngan hang cua practice do nguoi dung tao -> chinh nguoi do duyet (owner).
3. **Dynamic turns**: so luot hoi moi stage la `min_turns`/`max_turns` hoac count + `re-roll`,
   khong con so co dinh `MAX_INTERVIEW_TURNS = 5`.
4. **Selection modes**: moi stage co the la `auto_random` | `manual` (user chon truoc) | `mixed`
   (manual truoc, het thi random bo sung).
5. **Session persistence**: luu config stage + danh sach intent duoc chon vao DB, de report/evaluate
   trace duoc cau hoi goc.

---

## 3. Data model changes

### 3.1 `question_bank` — them cot (migration nhe, khong drop)
| Cot | Type | Ghi chu |
| --- | --- | --- |
| `moderation_status` | Enum `question_moderation_status_enum` (`pending`/`approved`/`rejected`) | default `approved` cho cac row cu (backfill) |
| `moderated_by` | BigInteger FK users nullable | admin hoac owner |
| `moderated_at` | DateTime nullable | |
| `moderation_reason` | Text nullable | ly do reject |
| `source` | Enum `question_source_enum` (`admin_manual`/`admin_ai`/`user_ai`/`user_manual`) | biet ai sinh ra |
| `practice_id` | BigInteger FK nullable | practice nguoi dung tao |
| `intent` | Text nullable | tom tat chu de/ky nang (AI sinh, bắt buộc khi source chứa `_ai`) |
| `difficulty` | SmallInt nullable (1-5) | optional |
| `tags` | JSONB/Text nullable | optional |

- Cap nhat `models/catalog.py`, `models/enums.py`, `schema.sql`, va file seed (seed du lieu mau: 8-10
  cau hoi approved cho moi domain lon de demo).

### 3.2 Bang moi: `interview_session_config`
| Cot | Type | Ghi chu |
| --- | --- | --- |
| `session_config_id` | BigInteger PK | |
| `session_id` | BigInteger FK `interview_sessions` | |
| `stage_key` | String (`warmup`/`technical`/`closing`) | |
| `stage_order` | Integer | |
| `source_mode` | String (`auto_random`/`manual`/`mixed`) | |
| `min_turns` | Integer default 1 | |
| `max_turns` | Integer default 2 | |
| `selected_question_ids` | JSONB (list int) | cho mode manual/mixed |
| `difficulty_filter` | SmallInt nullable | |
| `type_filter` | JSONB nullable (list `behavioral`/`technical`/`situational`) | |

### 3.3 Bang moi: `session_question_selection`
| Cot | Type | Ghi chu |
| --- | --- | --- |
| `selection_id` | BigInteger PK | |
| `session_id` | BigInteger FK | |
| `stage_key` | String | |
| `question_id` | BigInteger FK `question_bank` | intent goc |
| `selection_order` | Integer | thu tu trong stage |
| `used_at_turn` | BigInteger nullable | turn da hoi |
| `was_rerolled` | Boolean default false | |
| `created_at` | DateTime | |

> Tat ca cac bang dung SQLAlchemy Base — khong can alembic; `Base.metadata.create_all` se tao
> bang moi, con cot moi tren bang cu thi ghi ro buoc backfill trong migration script thu cong
> (file `migrations/001_question_engine.sql` + script python chay 1 lan).

---

## 4. Application layer (service + commands)

### 4.1 `QuestionBankService` (moi, hoac extend `CatalogService`)
- `search_questions(filters, moderation_status='approved')` — chi tra approved cho candidate.
- `create_ai_questions(practice_id, jd_text, count)` -> tra list intent draft `pending` (source=`user_ai`).
- `moderate_question(question_id, actor, action, reason)`:
  - actor la admin -> duyet bat ky.
  - actor la owner cua `practice_id` -> chi duyet question thuoc practice do.
- `update_intent(question_id, intent)` — cho phep owner/admin sua intent truoc khi duyet.

### 4.2 `QuestionSelectionService` (moi)
- Input: `session_config` + filters (domain/role/level/type/difficulty/language).
- `sample_for_stage(stage_key, mode, count, exclude_used)`:
  - `auto_random`: sample ngau nhien tu approved bank, khong trung cau da dung trong session, co
    the dung `random` seed luu trong config de re-run kha lap (debug/test).
  - `manual`: lay theo `selected_question_ids`, validate quyen so huu + approved.
  - `mixed`: manual truoc, thieu thi auto bo sung.
- `reroll(session_id, stage_key, current_selection_id)` -> chon intent moi, danh dau `was_rerolled`,
  gui event cho FE (voice/text).
- Luu ket qua vao `session_question_selection`.

### 4.3 `QuestionIntentComposer` (moi — module nho trong `application/interview/`)
- Build prompt cho LLM tu intent:
  - System guardrail: `"Ban KHONG duoc doc nguyen van cau hoi trong ngan hang. Hay chuyen intent
    thanh cau hoi tinh huong tu nhien, phu hop dien bien hoi thoai hien tai."`
  - Include: intent, question_type, star_template (neu co), language, stage instruction (da co
    `_build_stage_instructions` trong orchestrator).
- Tra ve `QuestionIntentContext` (intent_id, topic_label, full prompt) cho ca text flow va voice flow.

---

## 5. Interview flow changes

### 5.1 `StartSessionCommand` / schema `StartSessionIn` (mo rong, giu backward-compatible)
```python
stage_configs: list[StageConfigIn] | None = None   # neu None -> default full 3 stages
total_turn_mode: "auto" | "exact" = "auto"
selected_question_ids: list[int] | None = None      # mode manual/mixed
practice_id: int | None = None
```
- Loai bo HARD-CODE `MAX_INTERVIEW_TURNS = 5`; tinh tong turn tu `stage_configs`.
- `start_session` luu config vao `interview_session_config` + sinh selection cho stage dau tien.

### 5.2 `InterviewService.submit_turn`
- Truyen `intent` cua cau hoi hien tai cho `generate_follow_up` de follow-up van theo dung intent
  (khong lan sang chu de khac) — them tham so `intent` vao `LLMInterviewerPort`.
- Khi turn cuoi cua stage hoan thanh -> lay intent tiep theo tu `QuestionSelectionService`.
- Ghi `used_at_turn` vao `session_question_selection`.

### 5.3 Voice Orchestrator (can chinh nho)
- `handle_client_ready` nhan them `stage_configs` + `question_plan` (id cua cac intent da chon).
- `_build_stage_instructions` nhan them intent context (thay vi chi stage instruction).
- Goi `QuestionSelectionService` qua port moi (inject qua container) — hoac WS router lay truoc
  khi tao orchestrator (don gian hon: router resolve intent per turn va truyen vao orchestrator).
- Event moi: `question_context` (topic label + intent id — KHONG gui nguyen van de tranh ro ri) va
  `reroll_question` (client -> server) + `question_rerolled` (server -> client).

---

## 6. API endpoints (them / chinh sua)

### Candidate
- `GET /api/v1/catalog/questions` — mac dinh chi `approved`; them filter `practice_id`,
  `source_mode`, `type`, `difficulty`, `moderation_status=owned_pending` (chi xem cua minh).
- `POST /api/v1/practices/{practice_id}/questions/generate` — AI sinh N intent tu JD (dang pending).
- `POST /api/v1/practices/questions/{question_id}/moderate` — owner approve/reject.
- `POST /api/v1/interviews/sessions` — payload mo rong nhu 5.1.

### Admin
- `GET /api/v1/admin/questions/pending` — danh sach cho duyet.
- `POST /api/v1/admin/questions/{question_id}/moderate` — approve/reject + reason, ghi ModerationLog.

### WebSocket (voice)
- `client_ready` nhan them: `stage_configs`, `question_plan`.
- Client -> Server them: `reroll_question`.
- Server -> Client them: `question_context` (topic/intent), `question_rerolled`.

---

## 7. Validation & Security
- Chi approved moi vao auto-random (backend enforce — khong tin FE).
- Owner check cho moderate user question; admin check cho admin moderate.
- Reject/cancel phai huy generation dang chay (ke thua co che generationId hien co).
- Validation so turn: `min_turns <= max_turns`, tong turn gioi han theo plan (Free/Pro quota sau).

---

## 8. Migration & Seed
1. `migrations/001_question_engine.sql` — ALTER TABLE + backfill `moderation_status='approved'`.
2. Script Python `scripts/migrate_question_engine.py` — chay an toan 1 lan.
3. Seed: them 8-10 cau hoi approved + intent cho moi stage/domain lon (warmup/technical/closing).

---

## 9. Testing plan (BE)
- Unit: `QuestionSelectionService` (random + manual + mixed + reroll + khong trung lap).
- Unit: `QuestionIntentComposer` — prompt co guardrail, intent duoc truyen, KHONG chua nguyen van.
- Unit: moderation ownership rules (owner duoc, nguoi khac bi 403).
- Acceptance: `POST /sessions` voi stage_configs custom (1 stage, 3 stage, mixed) -> session tao
  dung config, `submit_turn` so turn dong (khong con fix 5).
- Acceptance: cau hoi `pending` KHONG bao gio duoc sampling.
- E2E WS: `question_context` duoc gui, `reroll_question` tra intent moi, audio van stream nhu cu.

---

## 10. Files can tao / sua (BE)
| File | Hanh dong |
| --- | --- |
| `app/infrastructure/persistence/models/catalog.py` | them cot moderation/intent/source/practice_id |
| `app/infrastructure/persistence/models/session.py` | them relationship sang config/selection |
| `app/infrastructure/persistence/models/session_plan.py` (moi) | 2 bang moi |
| `app/infrastructure/persistence/models/enums.py` | them enum moderation status + source |
| `app/infrastructure/persistence/repositories/question_bank_repository.py` | CRUD + filter + sampling |
| `app/application/catalog/service.py` | them moderate/approve/search intent |
| `app/application/interview/question_selection.py` (moi) | sampling + reroll |
| `app/application/interview/intent_composer.py` (moi) | prompt builder + guardrail |
| `app/application/interview/commands.py` | mo rong StartSessionCommand |
| `app/application/interview/service.py` | bo MAX_INTERVIEW_TURNS, dung dynamic budget + intent |
| `app/presentation/api/schemas/interview.py` | StageConfigIn, QuestionContextOut |
| `app/presentation/api/schemas/catalog.py` | moderation fields, generate/moderate in/out |
| `app/presentation/api/routers/interview.py` | endpoint moi + mo rong start session |
| `app/presentation/api/routers/catalog.py` | filter approved + moderate endpoints |
| `app/presentation/api/routers/admin.py` | pending + moderate endpoints |
| `app/presentation/api/routers/voice_ws.py` | question_plan + reroll handling |
| `app/application/voice/orchestrator.py` | intent context + reroll event |
| `app/application/container.py` + `bootstrap.py` | wire QuestionSelectionService |
| `tests/**` | unit + acceptance + E2E nhu muc 9 |
| `schema.sql` + `migrations/` | dong bo schema |

---

## 11. Thu tu trien khai (BE)
1. Data model + enums + migration script + seed.
2. QuestionBankService moderation + repository.
3. QuestionSelectionService + intent composer (pure domain, co unit test truoc).
4. InterviewService dynamic budget + intent follow-up.
5. API endpoints + schemas.
6. WS orchestrator + reroll.
7. Full test suite + E2E.
