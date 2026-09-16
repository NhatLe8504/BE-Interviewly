-- =====================================================================
-- AI Interview Coach (AI-PJIPP) — Database Schema (PostgreSQL)
-- Sinh từ tài liệu thiết kế "Thiết kế Cơ sở dữ liệu — AI Interview Coach"
-- Chuẩn hóa 3NF cho các bảng nghiệp vụ cốt lõi; JSONB cho dữ liệu linh hoạt.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 0. Extensions & helper function
-- ---------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- cho gen_random_uuid() nếu cần sau này

-- Hàm dùng chung để tự động cập nhật updated_at
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- 0.1 ENUM types
-- ---------------------------------------------------------------------
CREATE TYPE user_role_enum        AS ENUM ('candidate', 'admin');
CREATE TYPE language_enum         AS ENUM ('vi', 'en');
CREATE TYPE user_status_enum      AS ENUM ('active', 'suspended', 'deleted');
CREATE TYPE experience_level_enum AS ENUM ('intern', 'fresher', 'junior', 'mid', 'senior');
CREATE TYPE question_type_enum    AS ENUM ('behavioral', 'technical', 'situational');
CREATE TYPE session_mode_enum     AS ENUM ('text', 'voice');
CREATE TYPE session_status_enum  AS ENUM ('in_progress', 'completed', 'abandoned');
CREATE TYPE turn_speaker_enum     AS ENUM ('ai', 'candidate');
CREATE TYPE billing_cycle_enum    AS ENUM ('free', 'monthly', 'yearly');
CREATE TYPE sub_status_enum       AS ENUM ('active', 'expired', 'cancelled');
CREATE TYPE payment_status_enum   AS ENUM ('pending', 'success', 'failed', 'refunded');
CREATE TYPE audit_action_enum     AS ENUM ('insert', 'update', 'delete');

-- =====================================================================
-- 1. users (FR-01, FR-13)
-- =====================================================================
CREATE TABLE users (
    user_id             BIGSERIAL PRIMARY KEY,
    full_name           VARCHAR(150) NOT NULL,
    email               VARCHAR(255) NOT NULL UNIQUE,
    password_hash       VARCHAR(255) NOT NULL,
    phone               VARCHAR(20),
    role                user_role_enum NOT NULL DEFAULT 'candidate',
    preferred_language  language_enum NOT NULL DEFAULT 'vi',
    status              user_status_enum NOT NULL DEFAULT 'active',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =====================================================================
-- 2. candidate_profiles (FR-01) — 1-1 với users, chỉ áp dụng role=candidate
-- =====================================================================
CREATE TABLE job_domains ( -- khai báo sớm để candidate_profiles FK được
    domain_id    SERIAL PRIMARY KEY,
    domain_name  VARCHAR(100) NOT NULL UNIQUE,
    description  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE candidate_profiles (
    user_id           BIGINT PRIMARY KEY
                          REFERENCES users(user_id) ON DELETE CASCADE,
    experience_level  experience_level_enum,
    target_domain_id  INT REFERENCES job_domains(domain_id) ON DELETE SET NULL,
    bio               TEXT,
    avatar_url        VARCHAR(500),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_candidate_profiles_updated_at
    BEFORE UPDATE ON candidate_profiles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =====================================================================
-- 3. job_roles (FR-02, FR-12)
-- =====================================================================
CREATE TABLE job_roles (
    role_id      SERIAL PRIMARY KEY,
    domain_id    INT NOT NULL REFERENCES job_domains(domain_id) ON DELETE CASCADE,
    role_name    VARCHAR(150) NOT NULL,
    description  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (domain_id, role_name)
);
CREATE INDEX idx_job_roles_domain_id ON job_roles(domain_id);

-- =====================================================================
-- 4. star_guidance_templates (FR-10)
-- =====================================================================
CREATE TABLE star_guidance_templates (
    star_template_id SERIAL PRIMARY KEY,
    title            VARCHAR(150) NOT NULL,
    situation_guide  TEXT,
    task_guide       TEXT,
    action_guide     TEXT,
    result_guide     TEXT,
    language         language_enum NOT NULL DEFAULT 'vi',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- 5. question_bank (FR-12, FR-10, FR-13)
-- =====================================================================
CREATE TABLE question_bank (
    question_id       BIGSERIAL PRIMARY KEY,
    domain_id         INT NOT NULL REFERENCES job_domains(domain_id) ON DELETE CASCADE,
    role_id           INT REFERENCES job_roles(role_id) ON DELETE SET NULL, -- NULL = câu hỏi chung
    experience_level  experience_level_enum,
    language          language_enum NOT NULL DEFAULT 'vi',
    question_type     question_type_enum NOT NULL,
    question_text     TEXT NOT NULL,
    star_template_id  INT REFERENCES star_guidance_templates(star_template_id) ON DELETE SET NULL,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_by        BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_question_bank_updated_at
    BEFORE UPDATE ON question_bank
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX idx_question_bank_domain_role ON question_bank(domain_id, role_id);
CREATE INDEX idx_question_bank_language ON question_bank(language);
-- Full-text search mở rộng (gợi ý mục 5 của tài liệu thiết kế)
CREATE INDEX idx_question_bank_text_fts
    ON question_bank USING GIN (to_tsvector('simple', question_text));

-- =====================================================================
-- 6. interview_sessions (FR-02, FR-03)
-- =====================================================================
CREATE TABLE interview_sessions (
    session_id        BIGSERIAL PRIMARY KEY,
    candidate_id      BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    domain_id         INT REFERENCES job_domains(domain_id) ON DELETE SET NULL,
    role_id           INT REFERENCES job_roles(role_id) ON DELETE SET NULL,
    experience_level  experience_level_enum,
    language          language_enum NOT NULL DEFAULT 'vi',
    mode              session_mode_enum NOT NULL DEFAULT 'text',
    status            session_status_enum NOT NULL DEFAULT 'in_progress',
    total_score       NUMERIC(5,2),
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_interview_sessions_candidate_id ON interview_sessions(candidate_id);
CREATE INDEX idx_interview_sessions_status ON interview_sessions(status);

-- =====================================================================
-- 7. interview_turns (FR-03, FR-08)
-- =====================================================================
CREATE TABLE interview_turns (
    turn_id            BIGSERIAL PRIMARY KEY,
    session_id         BIGINT NOT NULL REFERENCES interview_sessions(session_id) ON DELETE CASCADE,
    turn_number        INT NOT NULL,
    speaker            turn_speaker_enum NOT NULL,
    question_id        BIGINT REFERENCES question_bank(question_id) ON DELETE SET NULL,
    message_text       TEXT,
    audio_url          VARCHAR(500),
    transcribed_text   TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, turn_number)
);
CREATE INDEX idx_interview_turns_session_id ON interview_turns(session_id);

-- =====================================================================
-- 8. answer_evaluations (FR-04) — 1-1 với interview_turns (turn của candidate)
-- =====================================================================
CREATE TABLE answer_evaluations (
    evaluation_id   BIGSERIAL PRIMARY KEY,
    turn_id         BIGINT NOT NULL UNIQUE
                        REFERENCES interview_turns(turn_id) ON DELETE CASCADE,
    clarity_score   NUMERIC(4,2) CHECK (clarity_score BETWEEN 0 AND 10),
    logic_score     NUMERIC(4,2) CHECK (logic_score BETWEEN 0 AND 10),
    example_score   NUMERIC(4,2) CHECK (example_score BETWEEN 0 AND 10),
    overall_score   NUMERIC(4,2) CHECK (overall_score BETWEEN 0 AND 10),
    feedback_text   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- 9. speech_quality_analysis (FR-09) — 1-1 với interview_turns (turn voice)
-- =====================================================================
CREATE TABLE speech_quality_analysis (
    analysis_id        BIGSERIAL PRIMARY KEY,
    turn_id             BIGINT NOT NULL UNIQUE
                            REFERENCES interview_turns(turn_id) ON DELETE CASCADE,
    speaking_pace       NUMERIC(6,2),   -- từ/phút (WPM)
    hesitation_count    INT DEFAULT 0,
    filler_word_count   INT DEFAULT 0,
    tips_text           TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- 10. session_progress_summary (FR-05) — bảng cache/derived
-- =====================================================================
CREATE TABLE session_progress_summary (
    summary_id          BIGSERIAL PRIMARY KEY,
    session_id          BIGINT NOT NULL UNIQUE
                            REFERENCES interview_sessions(session_id) ON DELETE CASCADE,
    candidate_id        BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    avg_clarity_score   NUMERIC(4,2),
    avg_logic_score     NUMERIC(4,2),
    avg_example_score   NUMERIC(4,2),
    avg_overall_score   NUMERIC(4,2),
    total_turns         INT DEFAULT 0,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_session_progress_summary_candidate_id
    ON session_progress_summary(candidate_id);

-- =====================================================================
-- 11. pdf_reports (FR-11) — 1-1 với interview_sessions
-- =====================================================================
CREATE TABLE pdf_reports (
    report_id      BIGSERIAL PRIMARY KEY,
    session_id     BIGINT NOT NULL UNIQUE
                       REFERENCES interview_sessions(session_id) ON DELETE CASCADE,
    file_url       VARCHAR(500) NOT NULL,
    generated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- 12. subscription_plans (FR-06)
-- =====================================================================
CREATE TABLE subscription_plans (
    plan_id          SERIAL PRIMARY KEY,
    plan_name        VARCHAR(100) NOT NULL UNIQUE,
    price            NUMERIC(10,2) NOT NULL DEFAULT 0,
    billing_cycle    billing_cycle_enum NOT NULL DEFAULT 'free',
    feature_limits   JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- 13. user_subscriptions (FR-06)
-- =====================================================================
CREATE TABLE user_subscriptions (
    user_subscription_id  BIGSERIAL PRIMARY KEY,
    user_id                BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    plan_id                INT NOT NULL REFERENCES subscription_plans(plan_id),
    status                 sub_status_enum NOT NULL DEFAULT 'active',
    auto_renew             BOOLEAN NOT NULL DEFAULT FALSE,
    start_date             TIMESTAMPTZ NOT NULL DEFAULT now(),
    end_date               TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_user_subscriptions_user_id ON user_subscriptions(user_id);
CREATE INDEX idx_user_subscriptions_status ON user_subscriptions(status);

-- =====================================================================
-- 14. payment_transactions (FR-07) — idempotent theo cổng thanh toán
-- =====================================================================
CREATE TABLE payment_transactions (
    transaction_id           BIGSERIAL PRIMARY KEY,
    user_subscription_id     BIGINT NOT NULL
                                 REFERENCES user_subscriptions(user_subscription_id) ON DELETE CASCADE,
    payment_gateway          VARCHAR(50) NOT NULL,
    gateway_transaction_id   VARCHAR(255) NOT NULL,
    amount                   NUMERIC(10,2) NOT NULL,
    currency                 VARCHAR(10) NOT NULL DEFAULT 'VND',
    status                   payment_status_enum NOT NULL DEFAULT 'pending',
    paid_at                  TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (payment_gateway, gateway_transaction_id)
);
CREATE INDEX idx_payment_transactions_user_subscription_id
    ON payment_transactions(user_subscription_id);

-- =====================================================================
-- 15. moderation_logs (FR-14)
-- =====================================================================
CREATE TABLE moderation_logs (
    log_id        BIGSERIAL PRIMARY KEY,
    admin_id      BIGINT NOT NULL REFERENCES users(user_id) ON DELETE SET NULL,
    target_type   VARCHAR(50) NOT NULL,   -- e.g. 'question', 'ai_output', 'user_account'
    target_id     BIGINT,
    action        VARCHAR(50) NOT NULL,   -- e.g. 'approve', 'remove', 'suspend'
    reason        TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_moderation_logs_target ON moderation_logs(target_type, target_id);

-- =====================================================================
-- 16. audit_logs (NFR-04)
-- =====================================================================
CREATE TABLE audit_logs (
    audit_id     BIGSERIAL PRIMARY KEY,
    user_id      BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    table_name   VARCHAR(100) NOT NULL,
    record_id    BIGINT,
    action       audit_action_enum NOT NULL,
    old_value    JSONB,
    new_value    JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_logs_table_record ON audit_logs(table_name, record_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);
-- Gợi ý mở rộng (mục 5): khi scale, partition bảng này theo tháng (created_at)
-- bằng PostgreSQL declarative partitioning.

COMMIT;
