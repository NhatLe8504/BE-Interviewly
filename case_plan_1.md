# Case plan 1: Interview fixes and cleanup

Scope: active WebSocket room `/practice/[sessionId]`, session/audio/result APIs, and legacy REST/SSE. FE and BE are separate repos. This plan changes no runtime code. Execute tasks in order: T1+T2 (coordinated rollout), T3, T4, T5 decision, T6, T7. Only edit within FE/BE; preserve existing changes. Each task is suitable for one small agent, with an atomic commit after verification under the assigned branch/identity and TEAM_GIT_RULES.md. Do not switch branches, commit, push, or deploy merely to create this plan. AGENTS.md forbids unsolicited tests/build/UI preview; request permission before running checks. Never hotfix VPS code.

## T1. Authenticate and authorize WebSocket (BE)

Files: `reference_app/app/presentation/api/routers/voice_ws.py`, optionally a shared helper under `presentation/api`, `reference_app/tests/acceptance/test_voice_websocket.py`.

1. Inspect token parser in `dependencies.py`, session ownership model, and JD job ID resolution. Remove fallback `user_id=1` and hash-derived session ID; fail closed for missing/unresolvable IDs.
2. Parse token before `websocket.accept()`. Reject absent/invalid/expired token with policy close (e.g. 1008), without logging it. Load resolved session and verify `session.user_id == authenticated_user_id` before orchestrator creation or any message.
3. Preserve both WS paths if consumers still use them. Do not trust `client_ready` role/level/language to override server-owned session configuration without explicit rules.
4. Cover absent/bad token, wrong owner, missing numeric/JD session, valid owner on each path; assert rejected sockets create no turn/side effect.

Done: all messages require authenticated session owner. Commit: `fix(interview): authorize voice websocket sessions`.

## T2. Send token and handle authentication failures (FE)

Files: `src/hooks/useRealtimeVoiceInterview.ts`, existing token helper `src/services/apiClient.ts` if needed.

1. Read token from same source as HTTP (`getStoredToken`). Append encoded query token to custom WS base, API base, and same-origin URLs. Never log credential-bearing URL; refresh token on each reconnect.
2. Without token, show sign-in error instead of opening WS. On auth/policy close stop automatic retries; retain backoff for transient disconnects.
3. Verify setup to room for normal/JD session, valid owner, expired token/logout, and network reconnect when UI checking is authorized.

Done: FE connects after BE enforcement; auth failure does not retry five times. Commit: `fix(interview): authenticate voice socket client`. Deploy T1 and T2 together.

## T3. Secure upload and playback of audio (BE then FE)

BE files: `reference_app/app/presentation/api/routers/voice_ws.py` audio routes and focused acceptance tests. FE files: `src/app/(user)/practice/[sessionId]/page.tsx`, supporting voice service/hook. Separate commits per repo.

1. Require authenticated owner for POST `.../user-audio`. Verify session and turn ownership/existence before reading, mkdir, or writing; reject empty, oversized, or unsupported content. Define 409 on finished sessions if uploads are disallowed.
2. Require owner for audio GET and HEAD. Restrict session ID/filename to server-issued forms, resolve path beneath session directory, and reject traversal/symlink escape.
3. Native `<audio src>` cannot attach Bearer header: choose short-lived signed URL or authenticated Blob fetch + object URL (revoke on cleanup). Update FE replay accordingly; do not leave public read route as workaround.
4. Cases: no token, other owner, missing turn, bad filename, too-large upload, owner replay, GET/HEAD, expiry -> 404.

Done: no cross-user access or path escape; authorized replay works.

## T4. Persist completion and await server ACK (BE then FE)

BE files: `reference_app/app/application/voice/orchestrator.py`, session service/repository as needed, `reference_app/tests/unit/test_voice_orchestrator.py`, `reference_app/tests/acceptance/test_voice_e2e_stages.py`. FE: `src/hooks/useRealtimeVoiceInterview.ts`, room `page.tsx`.

1. Trace `InterviewService.complete_session`, scoring, quota and result/history. Add one idempotent persistence path for natural completion and `stop_session`: set completed status/time, do not overwrite existing score; DB commit before `done/is_completed`.
2. Schedule skill sync/audio cleanup after successful commit. On DB error send error, not success; allow safe retry. Reconnect must read persisted status and refuse resumed turns for completed session.
3. FE `endSessionEarly`: set pending only if stop message sent; disable repeat click; redirect and set completed only on server `done`/ack. On timeout/close/error show retry/status check, not fake completion.
4. Cases: natural/early, duplicate stop, disconnect/reconnect, DB failure, no turns after completion, completed status in history/result, pending evaluation if applicable.

Done: DB and UI agree exactly once. Separate commits: `fix(interview): persist voice session completion` and `fix(interview): await server completion before redirect`.

## T5. Repair or retire legacy REST/SSE contract

FE files: `src/redux/api/user/interviewApi.ts`, `src/services/interviewApi.ts`, `src/hooks/useInterviewSession.ts`. BE if retained: `reference_app/app/presentation/api/routers/interview.py`, `reference_app/tests/acceptance/test_interview_api.py`.

1. Check external API clients before removing server REST/SSE. Old hook has no runtime FE consumer, only type imports; that does not prove server route is unused.
2. If retained, send mandatory `turn_number` query expected by BE (currently FE omits it and BE defaults to 1); validate current unanswered turn server-side to prevent skip/re-submit.
3. FE `audio_blob` sends FormData to BE JSON schema `TurnSubmitIn`: use T3 authenticated upload or explicitly support multipart. Align `pause_duration_seconds`/`audio_url` with actual persistence and reports.
4. Remove production catch-and-return mock responses for session, turns, quota/catalog. Keep deliberate mock fixtures only in dev/test. Tighten `any` types. Check turns 1..N, retries, JSON/audio, 401/403/409/500.

Done: one documented contract with no false success, or documented retirement decision. Atomic FE/BE commits.

## T6. Remove unused FE paths (after T5)

Files: `src/hooks/useInterviewSession.ts`, `src/hooks/useSseStreaming.ts`, `src/app/(user)/practice/[sessionId]/components/{InterviewHeader,ConversationTimelineDrawer,AiStageAvatar}.tsx`, `src/services/interviewApi.ts`, `src/redux/api/user/interviewApi.ts`, affected types/imports.

1. Search runtime/dynamic imports, docs, scripts. Active room uses `useRealtimeVoiceInterview`; old components currently import types from old hook. Move still-needed types to stable type module first.
2. Confirm individual consumers: wrapper `getDomains`, `getRoles`, `checkSubscriptionQuota`, `getTurnEvaluation`, `getSessionResult` currently show no external FE call; result UI uses `historyApi`. Preserve setup's `startSession`.
3. Remove in small independent commits: dead components, old hooks, unused wrappers/endpoints. Do not delete BE routes until external consumers are checked and a sunset plan exists.

Done: no dangling imports, setup/room/result behavior unchanged.

## T7. Restart-safe audio retention (BE, after T4)

Files: `reference_app/app/application/voice/orchestrator.py`, existing background-job/infra files as needed, focused tests; FE only for expired replay UX.

1. Current `_schedule_audio_cleanup` is an in-process sleeping task gated on orchestrator COMPLETED state. Add bounded restart-safe sweep/job for old completed/abandoned sessions and orphan directories with configurable TTL; never delete active audio.
2. Decide behavior for persisted `audio_url` and `user_audio_url` after cleanup: keep transcript in reports, make expired playback explicit instead of a broken control.
3. Cover completed/abandoned/orphan/active, restart sweep, repeated cleanup, path/symlink safety, normal and JD sessions.

Done: audio is not retained indefinitely or removed from active sessions. Separate commit.

## Validation / handoff

After user authorization, run focused unit/acceptance tests per task, then interview/voice suite, FE typecheck and manual browser smoke test. Matrix: owner/no token/other owner; normal/JD; text/voice; reconnect; early/natural completion; result/history; upload/replay/expiry; network failure. Each agent reports files, contract changes, checks pass/fail, unresolved risks and commit hash. Coordinate FE+BE rollout so BE does not enforce token/audio authentication before FE sends credentials and supports authorized playback.
