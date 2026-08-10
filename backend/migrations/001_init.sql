-- LinkedIn AI Content Agent — initial schema
-- Run this once in the Supabase SQL editor (or via `psql $DATABASE_URL -f 001_init.sql`).
-- `users` itself is Supabase's built-in `auth.users` table — we reference it, not recreate it.

create extension if not exists "pgcrypto";

create table if not exists linkedin_accounts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    linkedin_member_urn text not null unique,
    linkedin_name text,
    linkedin_email text,
    status text not null default 'active' check (status in ('active', 'revoked')),
    connected_at timestamptz not null default now()
);
create index if not exists ix_linkedin_accounts_user_id on linkedin_accounts(user_id);

create table if not exists oauth_tokens (
    id uuid primary key default gen_random_uuid(),
    linkedin_account_id uuid not null references linkedin_accounts(id) on delete cascade,
    access_token_encrypted text not null,
    refresh_token_encrypted text,
    access_token_expires_at timestamptz not null,
    refresh_token_expires_at timestamptz,
    scopes text[] not null default '{}',
    updated_at timestamptz not null default now()
);
create index if not exists ix_oauth_tokens_linkedin_account_id on oauth_tokens(linkedin_account_id);

create table if not exists projects (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    name text not null default 'My Posts',
    created_at timestamptz not null default now()
);
create index if not exists ix_projects_user_id on projects(user_id);

create table if not exists prompts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    project_id uuid references projects(id) on delete set null,
    raw_text text not null,
    optional_context text,
    created_at timestamptz not null default now()
);
create index if not exists ix_prompts_user_id on prompts(user_id);

create table if not exists uploaded_images (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    prompt_id uuid references prompts(id) on delete set null,
    storage_path text not null,
    mime_type text not null,
    size_bytes integer not null,
    width integer,
    height integer,
    created_at timestamptz not null default now()
);
create index if not exists ix_uploaded_images_user_id on uploaded_images(user_id);
create index if not exists ix_uploaded_images_prompt_id on uploaded_images(prompt_id);

create table if not exists ai_jobs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    prompt_id uuid not null references prompts(id) on delete cascade,
    job_type text not null check (job_type in ('ANALYZE_IMAGES', 'GENERATE_POST', 'REGENERATE')),
    status text not null default 'PENDING' check (status in ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')),
    model_used text,
    input_tokens integer,
    output_tokens integer,
    cost_usd double precision,
    error_message text,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now()
);
create index if not exists ix_ai_jobs_user_id on ai_jobs(user_id);
create index if not exists ix_ai_jobs_status on ai_jobs(status);

create table if not exists tool_calls (
    id uuid primary key default gen_random_uuid(),
    ai_job_id uuid not null references ai_jobs(id) on delete cascade,
    tool_name text not null,
    input_json jsonb not null default '{}',
    output_json jsonb not null default '{}',
    duration_ms integer,
    created_at timestamptz not null default now()
);
create index if not exists ix_tool_calls_ai_job_id on tool_calls(ai_job_id);

create table if not exists generated_posts (
    id uuid primary key default gen_random_uuid(),
    prompt_id uuid not null references prompts(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    ai_job_id uuid references ai_jobs(id) on delete set null,
    post_text text not null,
    hashtags text[] not null default '{}',
    status text not null default 'DRAFT'
        check (status in ('DRAFT', 'EDITED', 'APPROVED', 'PUBLISHING', 'PUBLISHED', 'FAILED', 'CANCELLED')),
    version integer not null default 1,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists ix_generated_posts_user_id on generated_posts(user_id);
create index if not exists ix_generated_posts_status on generated_posts(status);

create table if not exists generated_post_images (
    id uuid primary key default gen_random_uuid(),
    generated_post_id uuid not null references generated_posts(id) on delete cascade,
    uploaded_image_id uuid not null references uploaded_images(id) on delete cascade,
    sort_order integer not null default 0
);
create index if not exists ix_generated_post_images_post_id on generated_post_images(generated_post_id);

create table if not exists linkedin_posts (
    id uuid primary key default gen_random_uuid(),
    generated_post_id uuid not null references generated_posts(id) on delete cascade,
    linkedin_account_id uuid not null references linkedin_accounts(id) on delete cascade,
    linkedin_post_urn text not null,
    linkedin_permalink text not null,
    status text not null default 'PUBLISHED' check (status in ('PUBLISHED', 'DELETED')),
    published_at timestamptz not null default now(),
    constraint uq_linkedin_posts_generated_post_id unique (generated_post_id)
);

create table if not exists usage_logs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    event_type text not null,
    metadata jsonb not null default '{}',
    created_at timestamptz not null default now()
);
create index if not exists ix_usage_logs_user_event on usage_logs(user_id, event_type);

-- Row Level Security: backend uses the service role key (bypasses RLS) for all writes,
-- so these tables are locked down by default against the anon/authenticated keys.
alter table linkedin_accounts enable row level security;
alter table oauth_tokens enable row level security;
alter table projects enable row level security;
alter table prompts enable row level security;
alter table uploaded_images enable row level security;
alter table ai_jobs enable row level security;
alter table tool_calls enable row level security;
alter table generated_posts enable row level security;
alter table generated_post_images enable row level security;
alter table linkedin_posts enable row level security;
alter table usage_logs enable row level security;
-- No policies are defined, which means only the service role (used exclusively by the
-- FastAPI backend) can read/write. The frontend never talks to Postgres directly.
