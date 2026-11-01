# Case fixbug 1 - Confirmed interview regressions

Date: 2026-10-30. This file is an execution guide for bugs found in the two review rounds. It does not itself change code. FE/BE are separate repos. Handle one numbered item per small agent/atomic commit; do not overwrite unrelated work. AGENTS.md normally prohibits unsolicited tests/build, but the user explicitly requested tests in the previous turn. Reconfirm permission for new test execution if needed.

## B1 - BE enum mismatch (blocker)

Observed: `SessionStatus` defines only lowercase `in_progress`, `completed`, `abandoned` in `reference_app/app/infrastructure/persistence/models/enums.py`. `reference_app/app/application/voice/orchestrator.py` uses `SessionStatus.COMPLETED` near lines 115 and 1614-1615; `reference_app/app/presentation/api/routers/voice_ws.py` uses `SessionStatus.COMPLETED` and nonexistent `SessionStatus.CANCELLED` near line 547. These branches raise AttributeError when evaluated. 21 focused unit tests passed, but did not exercise actual enum values at these sites.

Agent scope: those two BE code files and focused test files. Use actual enum members (`completed`, `abandoned`) consistently; decide whether cancelled is a real domain state before adding it (do not silently expand DB enum). Test persisted completion (early and natural), reconnect to completed session, and audio upload status active/completed/abandoned. Do not replace with string-only comparisons. Acceptance: no AttributeError, DB status/time persisted before done ACK, completed upload rejected as intended. Suggested commit: `fix(interview): use persisted session status enum`.

## B2 - Acceptance fixture contract prevents security tests

Observed command from BE cwd: `./reference_app/.venv/Scripts/python.exe -m pytest reference_app/tests/acceptance/test_voice_websocket.py -x -q --tb=short` fails at `reference_app/tests/acceptance/test_voice_websocket.py:21`: helper expects `login_resp.json()["user"]["user_id"]`, response has no `user` key. Full acceptance batch was interrupted after repeated failures; do not claim WS security tests passed.

Agent scope: `reference_app/tests/acceptance/test_voice_websocket.py` and shared acceptance fixtures only if needed. Inspect actual login response schema; derive ID from supported response/authorized `/me`, check register/login status codes and print useful assertion on failure. Avoid hardcoding ID 1. Also inspect `test_voice_e2e_stages.py` for same helper assumption. Then rerun focused WS acceptance and report next distinct failure rather than patching production blindly. Suggested commit: `test(interview): align websocket fixture with auth response`.

## B3 - Active audio deletion threshold

Observed: `reference_app/app/config.py` cleanup branch removes an `in_progress` session's audio if directory mtime exceeds `max_age_seconds` (86400), although docstring says never delete active session audio. This may be desirable only after a verified stale/abandoned transition, not from file age alone.

Agent scope: `reference_app/app/config.py`, `reference_app/tests/unit/test_audio_cleanup.py`, session lifecycle job if required. Define stale-session policy using DB heartbeat/last activity and a state transition to `abandoned`; until then do not delete DB-active session folders based solely on mtime. Test active old directory survives, truly abandoned/finished expires, orphan cleanup remains restart-safe. Suggested commit: `fix(interview): preserve active session audio during sweep`.

## B4 - Previous review follow-through

Recheck the prior findings after B1/B2: WebSocket token + owner, authorized audio read/upload, DB completion before done, FE awaiting ACK, legacy REST turn number and mock fallback removal, dead FE hook/component cleanup. These commits are present, but static review and 21 passing unit tests are not end-to-end proof. Once B1/B2 are fixed, run (with permission) focused unit tests, WS/API acceptance, FE typecheck, then manual normal/JD voice/text and result/audio smoke tests. Do not conflate existing unrelated test failures with these regressions.

Current worktree at writing: BE already has modified `reference_app/docs/openapi.json` and untracked `case_plan_1.md`; preserve both. Creating these documents is not authorization to commit, push, switch branch, or modify VPS.
