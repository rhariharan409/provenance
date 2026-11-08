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

---

## Section 3: Analysis and Scoring Engine

Section 3 adds an evidence-backed contribution scoring engine that moves beyond raw commit counts or line volume, computing fair and auditable contribution shares for team members.

### Core Principles
- **No Execution of Repo Code**: Code is never checked out, compiled, or executed. Files are analyzed purely through Git commands on the bare repository (`git ls-tree`, `git cat-file`, `git blame`, `git log`, `git diff`).
- **Meaningful Lines Only**: Blank lines, block/line comments (in C-like, Python/YAML, HTML, SQL families), lockfiles, minified bundles, vendor libraries, and binaries are excluded.
- **Dampening & Anti-Gaming**: A sublinear function `log2(1 + lines)` dampens giant single-commit line counts, and merge/bot commits are filtered out.
- **Exact 100.00% Guarantee**: Proportional normalized scores sum to exactly 100.00% using Decimal rounding correction.

### The 4 Weighted Signals

| Signal | Default Weight | Description |
|---|---|---|
| **Code Survival** | `0.40` (40%) | Measures lines present in HEAD using `git blame --line-porcelain -w -M -C`, crediting true authors even across whitespace changes and refactors. |
| **Effective Change** | `0.25` (25%) | Dampened commit line changes (`log2(1 + lines)`) across project history, capturing consistent long-term engineering effort. |
| **Module Ownership** | `0.15` (15%) | Measures code concentration across top-level modules (directories with >= 20 surviving lines) where a member wrote >= 50% of the code. |
| **Collaboration** | `0.20` (20%) | Evaluates GitHub PR activity: merged PRs (1.0), open/closed PRs (0.25), and peer code reviews given (0.5 each, capped at 3/PR). Automatically redistributes its weight across the other three signals when no PR data exists. |

### Confidence Levels & Flags

- **Confidence**: Each member receives a `high`, `medium`, or `low` confidence rating based on active days (>= 5), commit count (>= 5), surviving code lines (>= 50), and PR collaboration. Automatically downgraded if the repository is truncated or has unlinked author identities.
- **Flags**:
  - `single_bulk_commit`: One commit contains > 70% of all added lines.
  - `late_dump`: >= 60% of commits submitted in the final 10% of the repository timeline or last 3 days.
  - `low_data`: Fewer than 10 commits analyzed.
  - `truncated`: Analysis capped at `MAX_BLAME_FILES` (default 1500) or exceeded timeout.
  - `no_collaboration_data`: No pull requests or reviews recorded; collaboration weight safely redistributed.
  - `rewritten_history_suspected`: Timestamps show commits older than their parents by > 30 days.
  - `bot_excluded`: Identified bot accounts excluded from scoring.
  - `unlinked_identities`: One or more authors could not be linked to project members.

### Configuration Variables (`backend/.env`)

```ini
# Section 3 (Scoring Engine Defaults)
SCORE_WEIGHT_SURVIVAL=0.40
SCORE_WEIGHT_EFFECTIVE_CHANGE=0.25
SCORE_WEIGHT_OWNERSHIP=0.15
SCORE_WEIGHT_COLLABORATION=0.20
MAX_BLAME_FILES=1500
MAX_FILE_SIZE_KB=400
ANALYSIS_TIMEOUT_SECONDS=600
BULK_COMMIT_LINE_CAP=5000
```

### Analysis API Endpoints

- `POST /projects/{id}/analyze`: Triggers a background analysis run. Returns `202 Accepted` (or `409 Conflict` if already running).
- `GET /projects/{id}/analysis/status`: Returns current status (`pending`, `running`, `complete`, `failed`) and any error message.
- `GET /projects/{id}/scores`: Returns the latest complete analysis run, including weights, project flags, and member score items.
- `GET /projects/{id}/scores/{member_id}/evidence`: Returns detailed explainability breakdown for a member (top 5 commits, top 5 files, owned modules, signal values, and natural-language summary sentence).

### Ground Truth Accuracy Tooling

Compare Provenance scores against ground-truth faculty/team estimates:

```bash
cd backend
# 1. Create a ground truth file from the example
cp scripts/ground_truth.example.json ground_truth.json
# Edit ground_truth.json with project_id and expected_scores

# 2. Run the comparison script
python scripts/compare_ground_truth.py --file ground_truth.json
```

The script reports:
- Mean Absolute Error (MAE) and Max Error against ground truth.
- Baseline MAE from raw commit counts.
- Spearman rank correlation comparing Provenance rankings vs. raw commit count rankings.


