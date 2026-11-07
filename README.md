# Provenance

Provenance is a web application that analyzes Git repositories and produces evidence-backed contribution reports for students, faculty, and recruiters.

---

## Architecture & Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2.0 (typed models), Alembic, psycopg 3, pydantic-settings, PyJWT, httpx, pytest.
- **Frontend**: Next.js (App Router) + TypeScript + Tailwind CSS with a strict, minimal design system.
- **Database**: PostgreSQL 16 via Docker Compose.

---

## Getting Started

### 1. Database Setup
Start the PostgreSQL container:
```bash
docker compose up -d
```
The database will be available at `localhost:5432` with username `provenance`, password `provenance`, and database name `provenance`.

### 2. Backend Setup
Create and activate a virtual environment, install dependencies, and run migrations:
```bash
cd backend
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Unix/macOS:
source .venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000` in your browser.

---

## Section 1: Foundation & GitHub Authentication

- GitHub OAuth login with minimal read-only scope (`read:user,user:email`).
- Session cookies (`provenance_session`) signed with HS256 JWT, `HttpOnly`, `SameSite=Lax`.
- Route protection for `/dashboard` via Next.js proxy.
- Users table with roles (`student`, `faculty`, `admin`).
- Initial Alembic migration `001_initial_schema.py`.

---

## Section 2: Repository Collection and Identity Merging

Section 2 adds automated Git repository collection, history parsing, GitHub API metadata enrichment, and multi-pass author identity resolution.

### Features
1. **Hardened Bare Clone**:
   - Clones bare repositories into `REPO_STORAGE_PATH/{project_id}.git`.
   - Disables hooks via empty `core.hooksPath` to protect against untrusted repositories.
   - Blocks local file exfiltration using `protocol.file.allow=never`.
   - Never exposes tokens in URLs, disk configs, or logs; passes credentials via temporary in-memory environment variables.
   - Enforces configurable clone timeouts (`CLONE_TIMEOUT_SECONDS`) and maximum commit limits (`MAX_COMMITS`).
2. **Deterministic Identity Resolution**:
   - **Pass 0**: Bot email/name detection (`[bot]`, dependabot, github-actions, etc.).
   - **Pass 1**: Noreply parsing (`{id}+{login}@users.noreply.github.com` or `{login}@users.noreply.github.com`).
   - **Pass 2**: GitHub API commit and PR author matching.
   - **Pass 3**: Normalized display name matching against known members.
   - **Pass 4**: Preserves user manual identity assignments across recollects.
3. **Identity Assignment & Merging Controls**:
   - Owners and admins can link unlinked author aliases to an existing member or create a new member.
   - Merge member profiles with automated alias reassignment and deduplication.
4. **Resilient Background Processing**:
   - Bounded concurrency pipeline for cloning and git log parsing.
   - Frontend auto-polling while repositories are `pending` or `analyzing`.

### Configuration Variables (`backend/.env`)

```ini
# Section 1
ENV=development
DATABASE_URL=postgresql+psycopg://provenance:provenance@localhost:5432/provenance
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret
GITHUB_REDIRECT_URI=http://localhost:3000/api/auth/github/callback
SESSION_SECRET=a_very_long_secure_random_string_at_least_32_chars
FRONTEND_URL=http://localhost:3000
ADMIN_GITHUB_USERNAMES=

# Section 2 (Optional / Defaulted)
GITHUB_API_TOKEN=                      # Read-only personal access token for higher public repo rate limits
GITHUB_APP_ID=                         # GitHub App ID for private repo installation access
GITHUB_APP_SLUG=                       # GitHub App slug for installation redirects
GITHUB_APP_PRIVATE_KEY_PATH=./secrets/github-app.pem
REPO_STORAGE_PATH=./data/repos
MAX_REPO_SIZE_MB=500
MAX_COMMITS=20000
MAX_PULL_REQUESTS=300
CLONE_TIMEOUT_SECONDS=600
MAX_PROJECTS_PER_USER=20
```

### GitHub App Setup (for Private Repositories)
To enable private repository collection:
1. Create a GitHub App in your organization or personal account:
   - Repository permissions: `Contents: Read-only`, `Pull requests: Read-only`, `Metadata: Read-only`.
   - Install the GitHub App on your account or organization.
2. Download the App's private key (`.pem`) and place it at `backend/secrets/github-app.pem`.
3. Set `GITHUB_APP_ID`, `GITHUB_APP_SLUG`, and `GITHUB_APP_PRIVATE_KEY_PATH` in `backend/.env`.
4. If a user submits a private repository where the app is not installed, the UI prompts them to install the app and retry.

### Running Tests

Backend test suite:
```bash
cd backend
pytest
```

Frontend lint & build check:
```bash
cd frontend
npm run lint
npm run build
```
