import os
import subprocess
import tempfile
import pytest
from app.services.collector import parse_git_log_output


def test_git_log_parser_with_real_git_repo():
    with tempfile.TemporaryDirectory() as repo_dir:
        def run_git(args, env=None):
            git_env = os.environ.copy()
            git_env["GIT_AUTHOR_DATE"] = "2026-01-01T12:00:00Z"
            git_env["GIT_COMMITTER_DATE"] = "2026-01-01T12:00:00Z"
            if env:
                git_env.update(env)
            res = subprocess.run(
                ["git"] + args,
                cwd=repo_dir,
                capture_output=True,
                text=True,
                env=git_env,
                shell=False
            )
            assert res.returncode == 0, f"Git command failed: {res.stderr}"
            return res

        # 1. Initialize repo
        run_git(["init"])
        run_git(["config", "user.name", "Alice"])
        run_git(["config", "user.email", "alice@example.com"])
        run_git(["config", "commit.gpgsign", "false"])

        # 2. First commit by Alice
        with open(os.path.join(repo_dir, "hello.txt"), "w") as f:
            f.write("Line 1\nLine 2\nLine 3\n")
        run_git(["add", "hello.txt"])
        run_git(["commit", "-m", "Initial commit from Alice"], env={
            "GIT_AUTHOR_NAME": "Alice",
            "GIT_AUTHOR_EMAIL": "alice@example.com",
            "GIT_COMMITTER_NAME": "Alice",
            "GIT_COMMITTER_EMAIL": "alice@example.com",
        })

        # 3. Second commit by Alice: binary file
        with open(os.path.join(repo_dir, "image.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00")
        run_git(["add", "image.png"])
        run_git(["commit", "-m", "Add binary asset"], env={
            "GIT_AUTHOR_NAME": "Alice",
            "GIT_AUTHOR_EMAIL": "alice@example.com",
            "GIT_COMMITTER_NAME": "Alice",
            "GIT_COMMITTER_EMAIL": "alice@example.com",
        })

        # 4. Branch feature: commit by Bob
        run_git(["checkout", "-b", "feature"])
        with open(os.path.join(repo_dir, "bob_feature.txt"), "w") as f:
            f.write("Bob's feature content\n")
        run_git(["add", "bob_feature.txt"])
        run_git(["commit", "-m", "Bob's feature implementation"], env={
            "GIT_AUTHOR_NAME": "Bob Jones",
            "GIT_AUTHOR_EMAIL": "bob@example.com",
            "GIT_COMMITTER_NAME": "Bob Jones",
            "GIT_COMMITTER_EMAIL": "bob@example.com",
        })

        # 5. Switch back to master/main, make another Alice commit
        # Determine default branch name (master or main)
        branch_res = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_dir,
            capture_output=True,
            text=True
        )
        # Checkout previous branch
        run_git(["checkout", "-"])
        with open(os.path.join(repo_dir, "alice_main.txt"), "w") as f:
            f.write("Alice ongoing work\n")
        run_git(["add", "alice_main.txt"])
        run_git(["commit", "-m", "Alice ongoing work"], env={
            "GIT_AUTHOR_NAME": "Alice",
            "GIT_AUTHOR_EMAIL": "alice@example.com",
            "GIT_COMMITTER_NAME": "Alice",
            "GIT_COMMITTER_EMAIL": "alice@example.com",
        })

        # 6. Merge feature into current branch (create a real merge commit with 2 parents)
        run_git(["merge", "feature", "--no-ff", "-m", "Merge branch feature into main"], env={
            "GIT_AUTHOR_NAME": "Alice",
            "GIT_AUTHOR_EMAIL": "alice@example.com",
            "GIT_COMMITTER_NAME": "Alice",
            "GIT_COMMITTER_EMAIL": "alice@example.com",
        })

        # 7. Execute machine-readable git log
        log_format = "\x1e%H\x1f%an\x1f%ae\x1f%aI\x1f%s\x1f%P"
        log_res = run_git(["log", "HEAD", "--numstat", f"--format={log_format}"])

        commits = parse_git_log_output(log_res.stdout)

        # Total 5 commits: Initial, Binary, Bob, Alice, Merge
        assert len(commits) == 5

        # Check merge commit
        merge_commit = commits[0]
        assert merge_commit.subject == "Merge branch feature into main"
        assert merge_commit.parent_count == 2

        # Find binary file commit
        binary_commit = next(c for c in commits if c.subject == "Add binary asset")
        assert binary_commit.author_name == "Alice"
        assert binary_commit.files_changed == 1
        assert binary_commit.additions == 0  # Binary files count as 0
        assert binary_commit.deletions == 0

        # Find Bob's commit
        bob_commit = next(c for c in commits if c.author_name == "Bob Jones")
        assert bob_commit.author_email == "bob@example.com"
        assert bob_commit.subject == "Bob's feature implementation"
        assert bob_commit.additions == 1
        assert bob_commit.files_changed == 1

