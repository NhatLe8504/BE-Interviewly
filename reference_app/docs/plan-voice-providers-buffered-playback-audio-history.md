# Interviewly: speech providers, buffered playback and audio history

Date: 2026-10-10 (Asia/Saigon)
Owner: nhatle08052004n
Status: investigation and implementation plan; application changes are NOT implemented.
Repositories: Interview_Coach_SRC_CODE/FE and Interview_Coach_SRC_CODE/BE only.
Paths below are relative to the indicated repository. Preserve the existing LLM, scoring, question selection and interview stages.

## 1. Product decisions

- Free: preserve current browser speech recognition and Edge TTS. Show real ElevenLabs voice choices as locked, with an accessible explanation and a separate upgrade action.
- Every active non-Free plan may opt into ElevenLabs STT and/or TTS. Paid users retain the default providers. Do not silently opt anyone into paid audio.
- Treat recognition provider (STT), speaking provider/voice (TTS), interview language and input mode as separate settings. Do not conflate a voice name with a language.
- Keep the existing eight interview languages: vi, en, zh, es, fr, de, ja, ko. UI localization remains separate.
- Default answer flow stays record -> stop -> listen/edit -> Send. Automatic submission remains OFF unless the user enables it.
- Audio replay/history applies to both Free and paid sessions. An expired paid plan blocks new premium generation, not replay of previously saved personal recordings.
- No voice cloning, new LLM, generated assessment scores, new interview-stage pipeline, new billing product or broad redesign.
- Community sharing exposes the question set, NEVER personal recordings, answers or session history.

## 2. Verified baseline, not assumptions

### 2.1 Recognition and recording

- FE src/hooks/useVoiceAnswerDraft.ts uses SpeechRecognition/webkitSpeechRecognition and MediaRecorder. It requires browser recognition even to start recording.
- The recorded Blob becomes a browser object URL for local review. submit() and automatic submission pass only text/duration, then discard the recording.
- FE src/hooks/useRealtimeVoiceInterview.ts sendTextMessage() sends final_transcript over the WebSocket. It does not upload the candidate's audio.
- There is no STT provider port in the current application/voice/ports.py.

### 2.2 TTS and playback

- BE reference_app/app/bootstrap.py wires EdgeTTSAdapter as the current TTS implementation.
- application/voice/orchestrator.py:729-764 has an LLM producer and ONE sequential TTS consumer, with a sentence queue of four.
- _stream_sentence_tts collects a complete sentence's MP3 before sending it. _stream_predefined_text also synthesizes sequentially.
- Important correction: the backend does NOT wait for the browser to finish playing sentence 1 before requesting sentence 2. It waits for synthesis of sentence 1. The bottleneck is serialized synthesis/insufficient audio buffering, not an onended request loop.
- FE useRealtimeVoiceInterview.ts already contains StreamingAudioPlayer: async decoding, scheduled AudioBufferSourceNode starts, generation cancellation and subtitle timing. Reuse it instead of adding a second competing player.
- application/voice/sentence_splitter.py recognizes more than periods, but abbreviation handling can stop scanning the buffer; token-boundary punctuation/decimals and CJK punctuation without whitespace need regression cases.
- infrastructure/tts/edge_tts_adapter.py caches up to about 200 entries in process memory, clearing the map when oversized. It is not a durable history store.
- That adapter returns SILENT_MP3_FRAME for missing dependencies, empty responses and exceptions. Production must not label silence as successful speech.

### 2.3 History and storage

- application/voice/orchestrator.py:193,202 stores audio_url='voice_streamed', NOT a playable resource. Conversation history broadcasts text only.
- infrastructure/persistence/models/session.py has a single audio_url per InterviewTurn and a unique (session_id, turn_number). The current voice flow puts AI message_text and candidate transcribed_text on the same row.
- Therefore a single new URL assignment would overwrite/misattribute one speaker. Do not redesign turn numbering or scoring just to add audio.
- Existing analytics history is exposed by presentation/api/routers/analytics.py and infrastructure/persistence/analytics_repository.py. FE uses types/analytics.ts and redux/api/user/historyApi.ts.
- Existing application/storage/ports.py and infrastructure/storage/cloudinary_storage.py support upload. They do NOT currently provide the private audio read/delete contract required here.

### 2.4 Authorization and plans: release blocker

- presentation/api/routers/voice_ws.py accepts before authenticating, defaults invalid/missing auth to user 1, accepts arbitrary numeric sessions, and does not enforce session ownership before creating the orchestrator.
- Never attach a billable provider or a private audio endpoint to this unchecked path.
- application/billing/service.py check_quota() currently returns quota_allowed=True and a nominal allowance; it is not a durable usage reservation mechanism. Do not treat it as one.
- Actual public billing API returned: Free, Sprint 7 Ngay, Pro Monthly and Pro Yearly. The existing feature_limits have no STT/TTS provider capability flags.
- An active subscription can itself be Free. has_active_subscription alone is NOT premium authorization.

### 2.5 Interviewer framing

- FE practice/[sessionId]/page.tsx:437 passes width=180 and height=180 to ChromaVideoCanvas.
- interviewRoom.module.css also limits interviewerMediaStage to 180x180.
- ChromaVideoCanvas.tsx explicitly crops from the top to focus on head/shoulders, so increasing CSS width alone cannot reveal the rest of the frame.
- ffprobe confirmed both public/videos/leader.mp4 and senior.mp4 are 720x1280, 10 seconds. Their actual full-body coverage has NOT been visually verified. Do not claim CSS can recover body parts absent from the assets.

## 3. Preparation completed in this planning turn

- [x] Read FE/BE agent rules, local UI/UX guidance and the relevant voice/billing/history code.
- [x] Save ELEVENLABS_API_KEY only to ignored BE/.env and BE/reference_app/.env. No key in this plan, frontend, source control or example files.
- [x] Verify both files are git-ignored and each has exactly one configured key entry.
- [x] Read-only provider probes: GET /v1/models and GET /v2/voices?page_size=5 returned HTTP 401, missing_permissions.
- [x] Exact missing permissions reported: models_read and voices_read.
- [ ] Owner enables those read permissions, and ensures Text to Speech / Speech to Text generation permissions and sufficient account quota. No synthesis/transcription request was made, so generation permissions and voice quality are NOT verified.
- [ ] Wire new settings into Settings, composition root and compose environment during Phase 1. Saving .env alone does not make the running Docker service support ElevenLabs.
- [ ] Implement all four phases below. No feature is marked complete based on this document.

Security note: this key has appeared in chat. Prefer replacing it with a restricted key before production. Do not ask for it to be pasted again; update the ignored environment files locally.

## 4. Target design and explicit trade-offs

### 4.1 Provider selection

Keep small application ports, with infrastructure adapters injected in bootstrap.py:

- SpeechRecognitionPort: transcribe uploaded audio for a declared interview language.
- Extend TTSPort carefully to return/declare codec, content type and sample rate, and accept a validated voice configuration; preserve the existing Edge adapter contract during migration.
- VoiceCatalogPort: server-side access to available voice/model metadata.
- VoiceEntitlementService: derive allowed capabilities from authenticated user, valid subscription dates and plan feature_limits.
- InterviewAudioRepositoryPort + private storage operations: persist per-speaker audio without application importing ORM/storage adapters.

Initial premium STT: Scribe v2 batch transcription after recording stops. This matches the existing review-before-send workflow and avoids a second realtime WebSocket/PCM pipeline in the first release. Show an honest transcription state, not fake interim text. Realtime Scribe is a later optional enhancement, not required for this task.

Preserve verbatim recognition (no_verbatim=false): keep raw STT text/timestamps separate from the candidate-reviewed submitted text. Do not use automatic transcript rewriting or remove filler words and then score that edited text as original speech delivery. Leave optional diarization/entity/editing extras off unless explicitly required; verify their costs before enabling them.

Initial TTS candidate: Eleven Flash v2.5, subject to actual key/model availability and language sample checks. Official docs list Vietnamese support. Do not blindly use Eleven Multilingual v2 for all eight languages; its documented language set does not include Vietnamese. Evaluate a higher-quality supported model only with measured samples; do not assume the latest advertised model uses the same API or supports all voices.

Voice catalog: fetch real account metadata server-side, curate/allowlist usable voice IDs and expose only display-safe fields. Do not expose private training files, arbitrary custom voices, raw account metadata or guessed voice IDs. Cache metadata with bounded TTL. If no successful catalog is available, show an honest unavailable state rather than fabricated voice rows.

### 4.2 Buffered TTS, exactly ordered

The user requested receiving audio before uninterrupted sequential playback. For the first implementation, use a full-turn buffer for the naturally short AI interview utterances:

LLM tokens -> sentence segmentation -> bounded synthesis workers -> indexed audio packets -> client decode buffer -> generation_done + all expected packets ready -> schedule complete turn -> playback_complete

- Start synthesis while LLM text arrives. Do NOT wait for playback acknowledgements to start another sentence's TTS.
- Initial per-generation concurrency target: 2, configurable and bounded by the provider/account allowance. Add a service-wide cap; a semaphore per user alone cannot protect a shared key.
- Full-turn buffering means the first spoken word waits for every sentence to finish and decode. This deliberately trades initial latency for the user's requested smoothness. Text can render earlier with an explicit preparing-audio state.
- A future prebuffer-two-sentences mode could reduce startup delay but cannot guarantee no network underruns. Do not silently substitute it for full-turn behavior or promise zero latency.
- Workers may finish out of order; playback and subtitles must follow sentence_index, not arrival time. Deduplicate packets by session/generation/index.
- Provider settings, voice and language are immutable snapshots for each generation. A settings change applies to the next turn or cancels/restarts explicitly; never mix voices within an utterance.
- Use previous_text/next_text context where the selected provider/model supports it. With full-turn text available before a request, use next context; otherwise use only context actually known. Do not fabricate look-ahead or misuse a previous request ID from another model.
- Split at real sentence boundaries, not every literal dot. Handle abbreviations, decimal/version numbers, URLs, ellipses, quotes, CJK punctuation, newline lists, no final punctuation and provider text limits.
- Bound text length, sentence count, pending bytes and generation timeout. Full-turn buffering is not an unbounded in-memory download.
- Reuse the AudioContext player and schedule starts against the audio clock. Use one small shared startup lead, not a new delay per sentence. Never put the next synthesis call inside audio.onended.
- Natural punctuation pauses and codec padding are not necessarily bugs. Measure audible gaps and scheduling separately; avoid chopping phonemes or overlapping spoken words to manufacture a zero-gap metric.
- Separate text completion, synthesis completion, decode completion and actual playback completion. Enable normal candidate recording after playback_complete, not merely the server's done event. Keep explicit barge-in behavior.
- Cancellation must stop producer, workers, outbound packets, decode jobs and scheduled sources for that generation. Ignore late packets after abort, language change, reroll, stage change or session end.

### 4.3 Persistent audio, not just cache

Use a new additive interview_audio_assets table (final naming follows local model conventions):

- asset_id, session_id, turn_id, speaker (ai/user), generation_id OR client_answer_id;
- provider/model/voice/language snapshot, mime/codec, duration_ms, byte_size, content_hash;
- state (pending/ready/failed/partial), interruption metadata, created_at;
- ordered segment manifest containing sentence_index and private storage keys. Candidate recordings normally have one segment.

Keep existing turn identities/evaluations intact. Add uniqueness for the AI generation and the candidate answer submission, rather than assuming one recording for the whole turn row. A retry/reroll must not overwrite a different generation's audio.

Store original generated bytes and original candidate recordings. Replaying MUST NOT call TTS or STT again. Initially keep sentence audio as ordered segments and replay through the same scheduler; do not concatenate independently encoded MP3 files with a naive byte join and pretend it is one seekable file. A proper remuxed export is optional later.

Separate two lifecycles:

1. Bounded synthesis cache: content/provider/model/voice/language/settings/context/codec key, scoped to owner for private content, with TTL and byte budget. Avoid indefinite plaintext text keys and clear-all eviction.
2. Durable personal history: DB metadata + private objects. It survives refresh, API restart and device change. Retention is explicit and configurable; do not silently delete recordings on plan expiry or introduce an undocumented retention deadline.

Extend the existing storage adapter for authenticated/private audio and deletion. Authorize reads by session owner before returning a short-lived signed manifest/URL or an authenticated streaming response. Do not use guessable public URLs or persist expiring delivery URLs in DB. Validate private delivery support against the actual storage account before release.

Use pending/ready/failed storage states with bounded retry and cleanup. Do not mark history ready until bytes are durable. Deleting a session/account must schedule deletion of associated objects; draft uploads need a configurable short expiry and orphan cleanup.

Candidate submission protocol:

record Blob -> local review (default STT) OR authenticated draft upload + ElevenLabs transcription -> review/edit -> media draft + final_transcript + client_answer_id -> validate ownership/current question -> commit answer + audio attachment idempotently -> answer_accepted -> discard local draft

- A successful WebSocket send() is NOT an acknowledgement. Retain Blob/text until server acknowledgement; retries must not create duplicate turns or repeated evaluations.
- A transcription/upload draft is private and not yet answer history. Discarded drafts must never appear as submitted answers.
- When upload fails, preserve the draft; offer retry or an explicit send-text-only action. Do not silently claim the voice was saved.
- Premium STT uploads before Send so it can transcribe for review: disclose this before recording in that mode. Never upload candidate audio while the chosen mode is text-only.
- Keep generated, delivered and heard/acknowledged audio distinct for interrupted responses. Label partial history and never present unheard/cancelled speech as a completed answer.
- Old voice_streamed placeholders become 'audio unavailable' in DTO mapping. Do not regenerate old recordings, and do not rewrite unverified historical URLs.

### 4.4 API/event contracts to design before UI work

Proposed routes, subject to existing routing conventions:

- GET /api/v1/voice/options: defaults, actual usable catalog and effective capability/lock reasons; no secrets.
- PATCH /api/v1/interviews/sessions/{id}/voice-settings: validated provider/voice preferences, owner only; snapshot per generation.
- POST /api/v1/interviews/sessions/{id}/audio-drafts: bounded private upload, with optional paid transcription after entitlement checks.
- GET /api/v1/interviews/sessions/{id}/audio/{asset_id}: private manifest/delivery contract, owner only.
- Extend existing analytics history DTOs with separate ai_audio/user_audio descriptors; preserve old nullable audio_url for compatibility during migration.

WebSocket fields: session_id, stable turn reference, generation_id, sentence_index, mime_type/codec and expected sentence count at generation_done. Add answer_accepted for idempotent user submission and playback progress/completion for presentation state. Reject malformed/out-of-range payloads. Never trust client plan, provider URL, storage key, user ID or transcript draft ownership.

## 5. Four atomic implementation phases

### Phase 1 - secure provider options and honest STT/TTS

Goal: Free cannot trigger paid provider calls; paid users can select real providers safely without changing the default flow.

- [ ] P1.1 Add required failing tests for invalid/missing token, foreign/nonexistent session, Free active subscription and expired paid subscription.
- [ ] P1.2 Fix both voice WebSocket aliases to authenticate and verify ownership before constructing the orchestrator; remove user-1 and hash-session fallbacks on this path. Update existing tests that currently open unauthenticated sessions 99/100/101/102 to create real owned fixtures.
- [ ] P1.3 Define explicit stt/tts capability flags in feature_limits; additive backfill Free=false, all current active paid plans=true, preserving unrelated limits. Apply correct start/end timestamps, plan activation and status checks server-side. Do not rely on plan-name substring or client claims.
- [ ] P1.4 Add Settings/example placeholders/compose injection for the secret and provider options. Ensure .env precedence cannot override deployed secrets unexpectedly, and exclude env secrets from Docker build context/logging. No key in NEXT_PUBLIC_*.
- [ ] P1.5 Add catalog and provider adapters using verified endpoint/model schemas. Handle timeout, 401/403, 429 and quota exhaustion distinctly. Limit retries and avoid duplicate billable requests on ambiguous timeouts.
- [ ] P1.6 Add STT audio draft flow with MIME sniffing, size/duration limits, ownership, no arbitrary remote URL ingestion, and private expiry/cleanup. Decouple MediaRecorder capability from browser SpeechRecognition so premium STT works when browser STT is absent.
- [ ] P1.7 Remove production silent-MP3 success fallback. On failure, keep readable text, disclose unavailable audio and allow retry/default-provider choice. Never silently switch paid speech mid-sentence.
- [ ] P1.8 Add runtime concurrency/budget controls. Use real per-user usage accounting where provider quotas are promised; current nominal check_quota is not sufficient. Reservation/usage updates must be atomic, with provider billable failures distinguished from no-call failures.
- [ ] P1.9 Return options with locked rows for Free and available rows for valid paid subscriptions. Revalidate at configuration and every new paid operation. Reuse premium recorded audio without rechecking generation entitlement.

Files: BE application/voice/ports.py + new voice service modules, domain/voice.py, config.py, bootstrap.py, application/container.py, billing service/repository, voice_ws.py, API voice schemas, new provider/storage adapters; FE services voice options/audio API and hooks/useVoiceAnswerDraft.ts as needed.

Gate: direct tampered HTTP/WS requests from Free/foreign owners make ZERO ElevenLabs generation calls. Defaults still work with no ElevenLabs key. Metadata failures show real errors rather than empty success or fabricated catalog entries.

### Phase 2 - sentence synthesis and full-turn playback

Goal: every sentence is synthesized before playback of the buffered turn; no request-on-playback-end pattern.

- [ ] P2.1 Expand splitter tests with tokens split immediately before/after a dot; 'Dr. Smith', 'TP. HCM', '3.14', 'v1.2.3', URLs, short answers, ellipses, quotations and CJK without spaces.
- [ ] P2.2 Implement bounded workers and ordered packets shared by LLM output AND predefined/opening questions. Preserve the selected LLM and question semantics.
- [ ] P2.3 Add complete-turn manifest/end count, timeout/error packets and immutable generation settings. Do not emit successful done for missing audio segments.
- [ ] P2.4 Refactor StreamingAudioPlayer surgically to buffer/decode all required segments, then schedule them on one clock; subtitles follow playback, not text arrival.
- [ ] P2.5 Handle duplicate/out-of-order/missing packets, reconnect, autoplay suspension, mute and barge-in. Cancellation invalidates both pending work and already scheduled sources.
- [ ] P2.6 Distinguish synthesis finished from playback finished; prevent auto-recording/auto-submit while AI audio is still playing. Keep explicit interruption controls.
- [ ] P2.7 Record metrics without private text/audio: text-ready time, synthesis time per sentence, all-audio-ready time, first sound time, buffer bytes and underrun count. Report measured startup delay rather than 'instant'.

Files: BE application/voice/sentence_splitter.py, orchestrator.py and new pipeline helper; FE hooks/useRealtimeVoiceInterview.ts and a small extracted audio player module if needed; shared voice event schemas.

Gate: with three sentences and intentionally reordered provider completion, requests start before any playback-end event and speech plays 0,1,2 exactly once. No later generation receives stale speech/subtitles. Zero queue starvation within a fully buffered turn; natural spoken pauses are preserved.

### Phase 3 - real audio history for both speakers

Goal: refresh/restart/device change preserves playable original recordings without calling speech providers again.

- [ ] P3.1 Add audio asset/manifest model, indexes, constraints and an idempotent migration following repository migration conventions; update schema/ERD documentation as appropriate. create_all is not an ALTER migration.
- [ ] P3.2 Extend storage ports/adapter with private media upload/read/delete and explicit failure results. Validate authorization for the actual serving path, not just upload.
- [ ] P3.3 Persist AI sentence bytes/manifest from the synthesis pipeline with generation identity, retry state and bounded orphan cleanup. A storage failure must not block conversational text forever or appear as ready audio.
- [ ] P3.4 Retain candidate Blob, upload/link an owned draft with client_answer_id, and discard only after answer_accepted. Verify manual and auto-send flows share one idempotent path.
- [ ] P3.5 Extend analytics/conversation-history DTOs with separate speaker audio metadata. Map old sentinels to unavailable. Never overwrite question_id, scores, tracking evidence or turn ordering.
- [ ] P3.6 Add one reusable replay control for the conversation drawer and existing history/result consumers. Support play/pause/progress, loading/error, one clip playing at a time and refresh of expired signed links.
- [ ] P3.7 Add cleanup for abandoned drafts, expired ephemeral cache and deleted sessions/accounts, including deletion failures/retry. Document retention separately from billing eligibility.
- [ ] P3.8 Verify community-public JD access does not grant session/audio access. Verify paid-plan expiry does not destroy stored voice recordings.

Files: BE infrastructure/persistence/models/session.py or focused new audio model, application/storage/ports.py, infrastructure/storage/cloudinary_storage.py, voice/analytics services, repositories and schemas; FE types/analytics.ts, ConversationTurn, ConversationTimelineDrawer.tsx, history API/consumers, new shared replay control.

Gate: two users, multiple turns, refresh and API restart; each user can replay ONLY their own AI and candidate recordings. Replays cause ZERO STT/TTS requests. Simulated upload failure/retry does not lose draft or duplicate answer evaluation. Unavailable legacy audio is not a broken player link.

### Phase 4 - refined room UI and more complete interviewer framing

Goal: keep the room's functions and familiar composition, improve hierarchy and show the existing character frame without a head-only crop.

- [ ] P4.1 Reuse home button/select/dialog tokens/components. No new decorative badge/icon system, neon gradients or avatar halo effects. CSS Modules only for room-specific geometry/character rendering.
- [ ] P4.2 Add a compact Voice settings disclosure in the existing right control area: STT provider, TTS provider/voice and current entitlement. Reuse language/input-mode controls; avoid a crowded row of new selectors.
- [ ] P4.3 Free sees real premium voices with a lock and readable reason; locked rows cannot select/preview by bypassing UI. Keep upgrade/navigation separate. Do not use paid synthesis just to populate previews.
- [ ] P4.4 Make draft states explicit: recording, transcribing, review, sending, sent. Preserve listen/edit/rerecord/send and the optional auto-send toggle; make upload/privacy state accurate.
- [ ] P4.5 Change ChromaVideoCanvas from top-crop to contain geometry using the FULL source frame, centered with stable aspect ratio. Decouple render buffer resolution from responsive display size.
- [ ] P4.6 Replace fixed 180x180 container with a portrait stage. Starting design targets: approximately 280-320px wide and 400-460px tall on desktop, fitting source ratio without distortion; a smaller portrait on mobile without hiding Send or input. Verify actual assets first; if they only contain a bust, clearly identify the need for a licensed/full-body replacement rather than claiming a CSS fix adds a body.
- [ ] P4.7 Keep left stage list, center interviewer/question and right controls; use a wider center track where space permits. On mobile put question/answer actions before secondary settings, avoid forced no-scroll layouts, and preserve touch targets/focus.
- [ ] P4.8 Avoid per-frame React state updates; stop canvas work when hidden, respect reduced motion and handle video/error fallback honestly. Do not preload every persona video simultaneously.
- [ ] P4.9 Replay controls in history are subordinate to message text and never auto-play on opening the drawer. Do not let replay and live AI overlap.

Files: FE practice/[sessionId]/page.tsx, interviewRoom.module.css, components/ChromaVideoCanvas.tsx, VoiceAnswerPanel.tsx and conversation drawer; shared select/button/replay components, without modifying unrelated pages.

Gate: desktop/tablet/mobile layouts preserve functions, controls do not overlap, long voice/language labels remain readable, keyboard/screen-reader names are correct, and asset framing is checked against actual media rather than a guessed full-body screenshot.

## 6. Verification and reporting contract

- Do not mark a phase complete because TypeScript compiles or an HTTP page returns 200.
- Use existing tests/unit/test_voice_orchestrator.py, test_streaming_sentence_splitter.py, test_edge_tts_adapter.py and billing tests; extend acceptance/test_voice_websocket.py and test_voice_e2e_stages.py with authenticated fixtures.
- Use deterministic fake adapters ONLY in tests to force ordering/errors/cancellation. No fake production voices, transcripts, audio URLs, success statuses or fabricated UI data.
- Targeted backend tests should cover entitlement, ownership, codec metadata, splitter boundaries, concurrency caps, cancellation, duplicate submissions, storage failures and private reads.
- Frontend validation: typecheck, targeted lint for touched files, player/draft tests if a local test harness exists; do not install a broad test stack merely for this task.
- Live provider smoke tests are explicit, bounded and billable: one short owner-approved speech sample, then validate Vietnamese/English and the other supported languages with a documented small budget. Never upload existing private recordings for convenience.
- Browser/audio/device checks are needed before claiming sound quality or full-body visuals; until performed, list them as not verified. Do not perform full builds or browser previews merely to write this plan.
- For each phase report changed files, exact checks run/results, failures left open, whether the running Docker service contains the new code, and any provider usage. Do not confuse saved env, restarted container and rebuilt image.
- Keep commits atomic under nhatle08052004n. Never stage .env; inspect staged paths and scan for secret leakage before push. Preserve all unrelated changes.
- Roll out behind capabilities/provider configuration, retaining the original providers and text-only mode. Rollback disables new generation features without deleting stored audio or reverting additive history migrations.

## 7. Evidence and external references

Local investigation: code reads, ffprobe metadata, billing plans GET, git ignore checks and two provider metadata requests. No browser rendering, end-to-end audio playback, speech synthesis or transcription was performed during planning.

Official reference URLs (re-check supported models and endpoints when implementing):

~~~text
https://elevenlabs.io/docs/overview/models
https://elevenlabs.io/docs/api-reference/text-to-speech/stream
https://elevenlabs.io/docs/api-reference/speech-to-text/convert
https://elevenlabs.io/docs/api-reference/voices/search
https://developer.mozilla.org/en-US/docs/Web/API/AudioBufferSourceNode
~~~

Documentation supports model language checks, context-aware TTS parameters, batch STT, real voice catalog lookup and audio-clock scheduling. Provider marketing latency numbers are NOT measured Interviewly performance and must not be used as acceptance results.
