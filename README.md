# LinkedIn AI Content Agent

Give it a prompt and a few photos. It drafts a LinkedIn post, shows you a preview, and — only after
you explicitly approve it — publishes it to your LinkedIn profile.

```
USER (prompt + photos)
   -> AI image understanding + intent understanding
   -> LinkedIn post draft (text + hashtags + image selection)
   -> Preview (edit / regenerate as needed)
   -> Approve
   -> Publish (LinkedIn API)
```

It's general-purpose: certifications, projects, events, job changes, awards, whatever you point it
at. There are no hard-coded post categories — the model figures out what kind of post fits from the
prompt and the images themselves.

## Why publishing is safe

The AI is never given a "publish" tool. It only ever returns a draft. Publishing is a completely
separate, deterministic code path (`POST /api/linkedin/publish`) that:

- only runs if the post's status is `APPROVED` in the database,
- only reaches `APPROVED` from an explicit `POST /api/posts/:id/approve` call, which only your
  frontend session (not the model) can make,
- resets back to `DRAFT`/`EDITED` the moment the text is changed, so a stale approval can never be
  replayed against edited content,
- is guarded by an atomic `APPROVED -> PUBLISHING` transition plus a DB-level unique constraint, so
  a double-click (or a retry) can't publish the same draft twice.

There is no code path — prompt injection included — that lets model output reach the LinkedIn API
directly.

## Two separate LinkedIn connections — don't confuse them

1. **"Continue with LinkedIn" on the login page** — Supabase's built-in `linkedin_oidc` social
   login provider. Identity only (`openid profile email`). Lets you sign into *this app* using your
   LinkedIn account instead of an email/password. Supabase owns this token; the backend never sees
   it.
2. **"Connect LinkedIn" after you're signed in** — our own OAuth flow (`GET /api/linkedin/connect`
   → `GET /api/linkedin/callback`), requesting `w_member_social` so the backend can actually post on
   your behalf. This is the one stored (encrypted) in `oauth_tokens` and refreshed before publishing.

Using (1) does not satisfy (2) — you'll still see the amber "connect your LinkedIn account" banner
until you do the second one, even if you just logged in with LinkedIn. That's intentional: logging
in and granting posting permission are different levels of trust, so they're kept as two explicit
steps rather than silently bundled.

## Architecture

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js (App Router) + Supabase Auth | Fast to iterate on; auth handled by Supabase directly, nothing custom to secure |
| Backend | Python / FastAPI | Owns OAuth, the AI pipeline, and every LinkedIn API call |
| Database | Postgres (Supabase), via SQLAlchemy (async) | One schema, direct SQL migration, no extra ORM-vs-DB drift |
| Storage | Supabase Storage (public bucket) | Images are destined to be public LinkedIn attachments anyway |
| AI | Claude (Anthropic), multimodal | One model call analyzes the images *and* drafts the post via forced structured tool output |
| LinkedIn | Official REST API only | `Sign In with LinkedIn (OIDC)` + `Share on LinkedIn` — both self-serve, no manual review needed |

The AI pipeline is one agent behind a deterministic pipeline, not a multi-agent system and not a
freeform tool-calling loop:

```
1. [deterministic] validate + store uploaded images
2. [AI]            one Claude call, forced tool-use -> { post_text, hashtags, image_analysis,
                                                          selected_image_indexes, reasoning }
3. [deterministic] persist as a DRAFT, return to the frontend
4. [user]          edit inline and/or regenerate with feedback (loops back to step 2)
5. [user]          Approve
6. [deterministic] Publish: LinkedIn Images API (upload) -> LinkedIn Posts API (create)
```

### Repo layout

```
backend/
  app/
    main.py            FastAPI app + router wiring
    config.py           env-driven settings
    models.py            SQLAlchemy models
    auth.py               Supabase JWT verification
    crypto.py              Fernet encryption for stored LinkedIn tokens + signed OAuth state
    routers/                 linkedin_auth, uploads, generation, posts, publish
    services/
      ai_pipeline.py           Claude multimodal call + structured draft schema
      linkedin_client.py        LinkedIn OAuth + Images API + Posts API calls
      linkedin_account.py        token refresh logic
      generation_service.py       background job orchestration (generate / regenerate)
      images.py                    upload validation, EXIF stripping, AI-input downscaling
      storage.py                    Supabase Storage upload/download
  migrations/001_init.sql   full DB schema (run once in Supabase SQL editor)
  scripts/test_ai_pipeline.py  standalone AI pipeline smoke test (no DB/Supabase needed)
frontend/
  src/app/
    login/, connect-linkedin/, create/, posts/[id]/, history/
    components/NavBar.tsx
  src/lib/
    supabaseClient.ts, api.ts (backend fetch wrapper), useSession.ts, types.ts
```

### Data model

`linkedin_accounts` + `oauth_tokens` (encrypted at rest) → `prompts` + `uploaded_images` →
`ai_jobs` (+ `tool_calls` audit trail) → `generated_posts` (+ `generated_post_images`) →
`linkedin_posts` (unique per `generated_post_id`, records the published permalink) →
`usage_logs`. Full definitions with indexes and constraints: `backend/migrations/001_init.sql`.

## What LinkedIn access this actually needs

Verified against LinkedIn's live API docs, not an old tutorial. Everything here is self-serve —
no waiting on LinkedIn's manual review queue:

- **Sign In with LinkedIn using OpenID Connect** (`openid profile email` scopes) — identifies the
  user.
- **Share on LinkedIn** (`w_member_social` scope) — posts to *the authenticated member's own feed*,
  including the image upload flow. Rate limit: 150 requests/member/day, 100,000/app/day.

Deliberately **not** used: the Community Management API (needed only for company-page posting or
analytics — requires a multi-week manual "Standard tier" review) and `r_member_social` (reading a
member's past posts back — a closed permission LinkedIn isn't granting to new apps). Neither is
needed for this product: we already have the post's URN from the publish response.

## Prerequisites

- Python 3.11–3.13 (**not 3.14** — see Troubleshooting)
- Node.js 20+
- A LinkedIn account, a Supabase account, an Anthropic account

## One-time setup

### 1. LinkedIn Developer App

1. Create (or reuse) a Company Page you administer: https://www.linkedin.com/company/setup/new/
   (any name works — it just needs to exist so an app can attach to it).
2. Create an app at https://www.linkedin.com/developers/apps, associated with that page.
3. Settings tab → verify the app↔Page link (you approve it yourself as the page admin).
4. Products tab → add **"Sign In with LinkedIn using OpenID Connect"** and **"Share on
   LinkedIn"** — both activate instantly.
5. Auth tab → add **both** redirect URLs (one for our backend's posting-permission flow, one for
   Supabase's login flow — see step 2.6 below):
   ```
   http://localhost:8000/api/linkedin/callback
   https://<your-supabase-project-ref>.supabase.co/auth/v1/callback
   ```
   Then copy the **Client ID** and **Client Secret**.

### 2. Supabase

1. Create a project at https://supabase.com.
2. Project Settings → API: copy the Project URL, `anon` public key, and `service_role` key.
3. Project Settings → Data API / Database: copy the JWT secret and the direct Postgres connection
   string.
4. Storage → create a bucket named `post-images`, set to **public**.
5. SQL Editor → paste and run `backend/migrations/001_init.sql`.
6. Authentication → Providers → **LinkedIn (OIDC)** → enable it, paste the same Client ID/Secret
   from step 1 → save. This is what powers the "Continue with LinkedIn" button on the login page —
   it's a separate thing from the backend's own LinkedIn OAuth flow below: this one just signs you
   into the *app* via your LinkedIn identity; it does **not** grant posting permission. You'll still
   do the **Connect LinkedIn** step once logged in before you can publish, even if you logged in
   with LinkedIn.

### 3. Anthropic

Create an API key at https://console.anthropic.com.

## Running it

### Backend

```bash
cd backend
python -m venv venv
./venv/Scripts/activate   # Windows; `source venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
cp .env.example .env       # fill in every value collected above
uvicorn app.main:app --reload --port 8000
```

Sanity-check just the AI half (no DB/Supabase/LinkedIn required) once `ANTHROPIC_API_KEY` is set:

```bash
python scripts/test_ai_pipeline.py "I completed this certification, announce it" path/to/photo.jpg
```

Interactive API docs once running: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # Supabase URL/anon key + backend URL
npm run dev
```

http://localhost:3000

## End-to-end test

1. Sign up on the frontend (this is Supabase Auth — your app account).
2. **LinkedIn** tab → Connect LinkedIn → approve on LinkedIn → redirected back "connected".
3. **Create** → upload a real photo → describe what you want the post to say → Generate.
4. Review the draft, edit if you want, **Approve**, then **Publish to LinkedIn**.
5. Open the returned permalink and confirm the post is live on your profile.

## API reference

| Endpoint | Behavior |
|---|---|
| `GET /api/linkedin/status` | Whether the current user has a connected LinkedIn account |
| `GET /api/linkedin/connect` | Returns the LinkedIn OAuth authorize URL |
| `GET /api/linkedin/callback` | OAuth redirect target; stores tokens, redirects to the frontend |
| `POST /api/upload` | Multipart image upload, returns validated/stored image records |
| `POST /api/generate` | Starts a generation job from a prompt + image ids |
| `GET /api/generation/:id` | Poll a generation/regeneration job's status |
| `GET /api/posts`, `GET /api/posts/:id` | List / fetch drafts and published posts |
| `PATCH /api/posts/:id` | Edit text/hashtags/images (resets approval) |
| `POST /api/posts/:id/approve` | The only way a post becomes publishable |
| `POST /api/posts/:id/regenerate` | Re-run generation with feedback text |
| `POST /api/linkedin/publish` | Publish an `APPROVED` post; idempotent on repeat calls |

## Security notes

- LinkedIn access/refresh tokens are encrypted at rest (Fernet) and never sent to the frontend.
- OAuth `state` is a signed, time-boxed token (also Fernet) — not a DB row, but still tamper-proof
  and replay-limited.
- Uploaded images are content-sniffed (not just extension-checked), size-capped, and re-encoded
  server-side to strip EXIF/metadata before storage or forwarding to LinkedIn.
- All Postgres tables have RLS enabled with no policies — only the backend's Supabase
  `service_role` key can read/write; the frontend never talks to Postgres directly.

## MVP scope

Upload photo(s) + prompt → generate → preview/edit → approve → publish, one LinkedIn personal
profile per user. No scheduling, no analytics, no other platforms, no autonomous posting, no
company-page support.

## Troubleshooting

- **`pip install` fails compiling `pydantic-core`/`asyncpg`**: you're probably on a very new Python
  version that doesn't have prebuilt wheels yet (this happened with 3.14). Use Python 3.11–3.13.
- **Backend won't bind to port 8000**: something else on your machine is already using it — run
  `uvicorn app.main:app --reload --port 8001` and update `LINKEDIN_REDIRECT_URI` /
  `NEXT_PUBLIC_BACKEND_URL` to match.
- **LinkedIn publish fails with a permissions error**: re-check the app has both products added
  under the Products tab and that your access token was issued after they were added (reconnect
  LinkedIn if you added a product after first connecting).
- **`Linkedin-Version` header**: LinkedIn versions its REST API monthly (`YYYYMM`). If publish
  starts failing after a long gap, bump `LINKEDIN_API_VERSION` in `backend/.env` to a recent month.
