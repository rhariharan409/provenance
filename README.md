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

---

## Section 4: Passports, Seal, QR Code and Disputes

Section 4 introduces shareable, tamper-evident **Contribution Passports** with cryptographic verification, QR codes, public read-only views, and a formal score dispute mechanism.

### Key Features

1. **Frozen Snapshot & Cryptographic Seal**:
   - Each passport captures a complete, immutable snapshot of the project, member attribution, signals, stats, evidence, and anonymized team context at a specific analysis run.
   - Sealed using HMAC-SHA256 (`provenance-seal-v1\n` prefix) over a canonical JSON serialization (`sort_keys=True`, `,` and `:` separators, UTF-8 bytes).
   - Any tampering with the stored snapshot invalidates the verification check.

2. **Public Verification & QR Codes**:
   - `/p/[code]`: Publicly accessible, responsive document view designed strictly with Provenance's design tokens (IBM Plex Sans/Mono, Source Serif 4 title, flat 1px borders, print-ready CSS).
   - `/api/public/passports/{code}/verify`: Instant cryptographic verification endpoint that re-calculates the seal using `hmac.compare_digest`. Never leaks the signing secret or server hashes.
   - `/api/public/passports/{code}/qr.svg`: Dynamic SVG QR code generated with `segno` pointing directly to the public passport URL. Cached with `Cache-Control: public, max-age=3600`.

3. **Privacy & Security Guarantees**:
   - Public responses strip internal user IDs, email addresses, and dispute text.
   - Teammates are anonymized as "Teammate A", "Teammate B"... with their contribution shares, revealing real GitHub logins only if that teammate has published an active passport for the same run.
   - Public endpoints include security headers: `X-Robots-Tag: noindex, nofollow` and `Referrer-Policy: no-referrer`.
   - In-memory rate limiting (60 requests/minute per client IP) returning HTTP 429 when exceeded.
   - Revoking a passport returns HTTP 404 with the exact same response body as unknown codes, preventing existence leakage.

4. **Contribution Score Dispute Workflow**:
   - Members can raise disputes regarding their own score (enforcing `MAX_DISPUTE_TEXT` up to 1000 characters and `MAX_OPEN_DISPUTES_PER_USER`).
   - Project owners and administrators review disputes via the "Disputes" panel, recording resolution notes and setting status (`resolved` or `rejected`).
   - Resolving a dispute instructs the administrator to trigger a re-analysis run without auto-mutating past historical records.

### Configuration Variables (`backend/.env`)

```ini
# Section 4 (Passports, Seal & Disputes)
PASSPORT_SIGNING_SECRET=your_32_byte_secret_key_here  # Required to publish; returns 503 if not set
PUBLIC_BASE_URL=http://localhost:3000                 # Base URL for public passport links and QR codes
MAX_DISPUTE_TEXT=1000                                 # Maximum characters allowed per dispute message
MAX_OPEN_DISPUTES_PER_USER=5                          # Maximum concurrent open disputes per user
```

### API Endpoints

- `POST /projects/{id}/members/{member_id}/passport`: Creates or returns existing active passport for the member (login required; only the member's linked user can publish).
- `GET /passports/mine`: Lists all passports published by the authenticated user with view counts and dispute summary.
- `DELETE /passports/{code}`: Revokes an active passport (owner or admin only).
- `GET /public/passports/{code}`: Public passport snapshot with seal and dispute summary.
- `GET /public/passports/{code}/verify`: Public seal verification result (`valid: boolean`).
- `GET /public/passports/{code}/qr.svg`: Public QR code in SVG format.
- `POST /projects/{id}/members/{member_id}/disputes`: Raises a dispute on a member's score.
- `GET /projects/{id}/disputes`: Lists disputes for a project (members see own; owners/admins see all).
- `POST /projects/{id}/disputes/{dispute_id}/resolve`: Resolves or rejects a dispute with optional note (owner/admin only).



