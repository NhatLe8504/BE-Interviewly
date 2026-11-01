# Case plan 2 - AuthN/AuthZ router matrix (FE + BE)

Date: 2026-10-30. Scope: `reference_app/app/presentation/api/routers` and FE callers under `src`. This is a static triage plan, not proof of exploitation or a code fix. AuthN = valid identity; AuthZ = permission to the exact resource/action. Do not enforce blanket auth on public catalog, jobs, courses, auth registration/login, or payment webhooks. Audit router dependencies and the service/repository below each route before changing behavior.

## Policy to implement

- Public read: published catalog/domains/questions/question sets, job list/detail/filters, published course list/detail, public plan list, voice catalog/limited preview if intentionally public. Rate-limit expensive public actions. Never expose unpublished/private records.
- User-owned: session/turn/evaluation/result/stream, report PDF/meta, CV/profile, personal history, JD generation/status/private script/start, practice answer/evaluation, billing checkout/history/quota, audio. Require valid user and ownership at service boundary as well as route where practical.
- Admin-only: `/api/v1/admin/*`, `/api/v1/admin/presence`, operational job sync/backfill/status if status reveals internals, moderation/crawler actions. Use `require_admin`, not merely a valid token. Background scheduler keeps internal service calls, not HTTP bypasses.
- Webhooks: no user JWT; verify payment provider signature/secret, reject replay and malformed payload. Public preview/catalog may remain anonymous but enforce limits, cost controls and published-only access.
- Error contract: 401 missing/invalid identity; 403 authenticated non-owner/non-admin; 404 nonexistent resource (or consistently mask existence); 409 invalid state. FE never substitutes another user's data or mocks success.

## Router inventory and decisions

| BE router/routes | Observed state | Decision / FE impact |
| --- | --- | --- |
| `voice_ws.py` interview WS, audio GET/HEAD/upload | Token and session owner checks recently added | Preserve; regression test owner/JD/reconnect. FE `useRealtimeVoiceInterview.ts` and room audio fetch use token; review token-in-query logging/cache. |
| `voice_ws.py` `GET /api/v1/admin/presence`, `WS /api/v1/ws/presence` | Admin HTTP has no guard; WS accepts before optional token and broadcasts online IDs | Admin-only both; FE `SocketContext.tsx` currently connects presence as user: split user-safe aggregate presence from admin detail or stop auto-connect. |
| `interview.py` GET session and GET stream | No identity dependency; POST submit recently has owner check | Require user + session owner for both reads/stream. FE legacy SSE uses token query; choose secure browser EventSource contract. |
| `evaluation.py` GET turn evaluation and GET session result | No auth/owner; turn evaluation fetched by turn ID before checking session linkage | Require user + session owner; assert turn belongs to path session before reading evaluation. FE result currently uses analytics/history; keep legacy consumer contract explicit. |
| `analytics.py` history/detail/result | Uses current user | Keep; confirm service filters by user for every ID, add cross-user tests. FE history/report calls unchanged. |
| `report.py` PDF download/preview/meta | Authenticated current user, but passed ID not checked against owner in route | Authorize report's session owner before generate/read PDF; do not return shared `/reports/{filename}` URL without a protected download contract. FE `historyApi.ts` returns raw PDF URL, so implement authenticated Blob fetch or signed short-lived URL. |
| `jobs.py` POST `/sync`, `/backfill-branding`; GET `/sync/status` | No guard | Admin-only operations/status; FE `jobsApi.ts` sync caller must be admin-gated or removed from normal user UI. Public list/detail/filter remain public. |
| `jd_interview.py` POST text/url/file, GET my-jobs/status, POST start-session | Mostly optional user; start-session can fall back to job owner; status exposes job result | User required for private generation/my-jobs/status/start; enforce job owner. Explicitly separate public community job templates from private jobs; FE `jdInterviewApi.ts` handle 401/403 and polling stop. |
| `catalog.py` questions/practice/sets, evaluation queues/pull/synthesis | Public reads mixed with optional-user mutations and unguarded queue/pull/synthesis | Keep published reads public. Require user for saved answers/reviews/history and evaluate queue; authorize task owner on pull; rate/size-limit AI jobs. Ensure leaderboard/reviews publish only intended fields. FE `catalogApi.ts` displays sign-in or preserves unsaved local draft on 401. |
| `billing.py` plans/checkout/verify/history/quota/webhooks | Plans public; user endpoints authenticated; webhook public by design | Keep policy; verify webhook signature/idempotency and verify-payment ownership in service. FE billing handles 401/403. |
| `profile.py`, `cv.py`, `upload.py`, `onboarding.py` | Mostly required user/Bearer | Preserve, audit ID-specific CV ownership, upload file access and onboarding token handling; no broad auth rewrite. |
| `course.py` public reads; `admin.py` admin writes/reads; `auth.py` login/register | Expected public/user/admin split | Preserve; sample-check lessons entitlement and all admin decorators. Do not add auth to login/register or public published content. |

## Small-agent execution order

### A1 - Core interview read ownership (BE)
Files: `interview.py`, `evaluation.py`, focused acceptance tests. Add shared owner helper using existing session model/service; guard GET session/stream/result/turn evaluation and assert turn/session relation. Test anonymous, other user, owner, missing ID; do not modify WS. Commit separately.

### A2 - PDF/report contract (BE + FE, coordinated)
Files: `report.py`, PDF service/repo and `src/services/historyApi.ts` plus report download consumers. BE checks session owner before generation/download/meta; no public static bypass. FE retrieves PDF with Authorization or short-lived signed URL and handles expiry. Test cross-owner and download/preview. Separate FE/BE commits; deploy together.

### A3 - JD private jobs (BE + FE)
Files: `jd_interview.py`, JD service/repo, `src/services/jdInterviewApi.ts` and setup/poll consumers. Decide public community template vs private job. Require user and exact job ownership for private generation/status/start; remove fallback to job owner when caller anonymous. FE stops polling 401/403 and offers login. Test user A/B and JD ID WS handoff.

### A4 - Operations/admin presence (BE + FE)
Files: `jobs.py`, `voice_ws.py`, `src/services/jobsApi.ts`, `src/context/SocketContext.tsx`. Guard sync/backfill/status/admin presence by role before accept/execute. Keep user presence only if a sanitized endpoint is genuinely needed; do not send online user IDs to ordinary users. Audit UI route visibility separately; hiding buttons is not authorization. Test anon/user/admin.

### A5 - Catalog write/AI queue isolation (BE + FE)
Files: `catalog.py`, task queue/service, `src/services/catalogApi.ts`. Separate public reads from personal writes and AI work; require user, associate task ID with owner and check pull/synthesis inputs. Add rate/size limits. Preserve draft on auth failure. Test cross-user task IDs and anonymous public reads.

### A6 - Remaining route audit and regression (BE + FE)
Check `billing`, `cv`, `profile`, `upload`, `onboarding`, `course`, `admin`, `auth` service-level ownership/role; webhook signature. No speculative mass refactor. Produce per-route checklist with anonymous/user A/user B/admin, verify FE 401/403 behavior and network retry. Each agent owns one router family; atomic commits only for proven gaps.

## Handoff / rollout

Per task report route, policy, affected FE call, exact 401/403/404 behavior, tests and residual compatibility risk. Coordinate FE+BE for PDF, JD and presence. Never put long-lived JWT into downloadable/shareable URL; redact query tokens in logs. Do not run build/test/UI without user permission per AGENTS.md. Follow assigned branch/identity and TEAM_GIT_RULES.md after authorization, no VPS code edits.
