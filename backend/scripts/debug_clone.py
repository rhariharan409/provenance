import os
import sys
import tempfile
import shutil
import base64
import subprocess
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.config import settings
from app.services.github_client import GitHubClient
from app.services.collector import _safe_rmtree

def mask_secrets(text: str, secrets: list[str]) -> str:
    if not text:
        return ""
    res = text
    for s in secrets:
        if s:
            res = res.replace(s, "[MASKED_TOKEN]")
    return res

def run_debug_clone(owner: str = "rhariharan409", repo: str = "Paytm_Hackathon", send_auth: bool = False):
    desc = "WITH auth header (old collector behavior)" if send_auth else "WITHOUT auth header (fixed collector behavior)"
    print("=" * 70, flush=True)
    print(f"Testing clone for {owner}/{repo}: {desc}", flush=True)
    print("=" * 70, flush=True)

    client = GitHubClient()
    auth_res = client.resolve_auth(owner, repo)
    token = auth_res.token
    inst_id = auth_res.installation_id

    print(f"Token configured in settings: {bool(settings.GITHUB_API_TOKEN)}", flush=True)
    print(f"Auth resolution - token present: {bool(token)}, installation_id: {inst_id}", flush=True)

    secrets = [token] if token else []
    if settings.GITHUB_API_TOKEN:
        secrets.append(settings.GITHUB_API_TOKEN)

    temp_dir = tempfile.mkdtemp(prefix="debug_clone_target_")
    clone_path = os.path.abspath(os.path.join(temp_dir, "repo.git"))
    temp_hooks_dir = tempfile.mkdtemp(prefix="git_empty_hooks_")

    clone_env = os.environ.copy()
    clone_env["GIT_TERMINAL_PROMPT"] = "0"

    if send_auth and token:
        auth_header = f"Authorization: Basic {base64.b64encode(f'x-access-token:{token}'.encode()).decode()}"
        clone_env["GIT_CONFIG_COUNT"] = "1"
        clone_env["GIT_CONFIG_KEY_0"] = "http.extraheader"
        clone_env["GIT_CONFIG_VALUE_0"] = auth_header
        print("Git extraheader: Authorization: Basic [MASKED]", flush=True)
    else:
        print("Git extraheader: None (anonymous clone)", flush=True)

    clone_cmd = [
        "git",
        "clone",
        "--bare",
        "-c",
        f"core.hooksPath={temp_hooks_dir}",
        "-c",
        "protocol.file.allow=never",
        "-c",
        "core.fsmonitor=false",
        "--",
        f"https://github.com/{owner}/{repo}.git",
        clone_path,
    ]

    print("Command:", " ".join(clone_cmd), flush=True)

    proc = subprocess.run(
        clone_cmd,
        env=clone_env,
        capture_output=True,
        text=True,
        timeout=settings.CLONE_TIMEOUT_SECONDS,
        shell=False,
    )

    clean_stderr = mask_secrets(proc.stderr, secrets)
    clean_stdout = mask_secrets(proc.stdout, secrets)

    print(f"Git exit code: {proc.returncode}", flush=True)
    print(f"Git stderr:\n{clean_stderr}", flush=True)
    if clean_stdout:
        print(f"Git stdout:\n{clean_stdout}", flush=True)

    _safe_rmtree(temp_dir)
    _safe_rmtree(temp_hooks_dir)
    return proc.returncode, clean_stderr

if __name__ == "__main__":
    owner = "rhariharan409"
    repo = "Paytm_Hackathon"

    # 1. Run collector's clone (anonymous for public repos without app installation)
    run_debug_clone(owner, repo, send_auth=False)
