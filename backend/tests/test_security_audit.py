import ast
from pathlib import Path
import pytest
from app.models.projects import Project, ProjectStatus
from app.models.users import User, UserRole
from app.services.collector import run_collection
from app.services.github_client import GitHubClient, AuthResolution
from tests.conftest import TestSessionLocal


def test_no_shell_true_used_in_codebase():
    """
    Verifies that no subprocess command uses shell=True anywhere in app/services.
    """
    services_dir = Path(__file__).resolve().parent.parent / "app" / "services"
    for py_file in services_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check for shell keyword argument
                for kw in node.keywords:
                    if kw.arg == "shell":
                        assert isinstance(kw.value, ast.Constant) and kw.value.value is False, (
                            f"Disallowed shell={kw.value.value} found in {py_file}"
                        )


def test_tokens_never_appear_in_error_message_or_logs(caplog):
    """
    Simulates a failure during collection with a fake sensitive token
    and verifies that the token is never leaked into logs, DB, or error_message.
    """
    fake_secret_token = "ghp_SUPER_SECRET_TOKEN_DO_NOT_LEAK_9999"

    session = TestSessionLocal()
    project_id = None
    user_id = None
    try:
        user = User(
            github_id=99999,
            username="audit_test_user",
            display_name="Audit User",
            email="audit@example.com",
            role=UserRole.student,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

        project = Project(
            owner_id=user.id,
            repo_url="https://github.com/secret-org/secret-repo.git",
            repo_full_name="secret-org/secret-repo",
            name="secret-repo",
            github_owner="secret-org",
            github_repo="secret-repo",
            status=ProjectStatus.pending,
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        project_id = project.id

        class MockFailingClient(GitHubClient):
            def resolve_auth(self, owner: str, repo: str):
                return AuthResolution(token=fake_secret_token)

            def verify_and_get_metadata(self, owner, repo, user, token):
                raise Exception(f"Connection failure to upstream with token {fake_secret_token}")

        run_collection(
            project_id=project_id,
            github_client=MockFailingClient(),
            db_factory=TestSessionLocal,
        )

        session.expire_all()
        reloaded_project = session.query(Project).filter(Project.id == project_id).first()

        # 1. Project should be marked failed
        assert reloaded_project is not None
        assert reloaded_project.status == ProjectStatus.failed

        # 2. Token MUST NOT be present in project.error_message
        assert reloaded_project.error_message is not None
        assert fake_secret_token not in reloaded_project.error_message

        # 3. Token MUST NOT be present in any database column
        assert fake_secret_token not in (reloaded_project.warnings or "")
        assert fake_secret_token not in (reloaded_project.clone_path or "")

        # 4. Token MUST NOT be present in captured logs
        assert fake_secret_token not in caplog.text

    finally:
        if project_id:
            session.query(Project).filter(Project.id == project_id).delete()
        if user_id:
            session.query(User).filter(User.id == user_id).delete()
        session.commit()
        session.close()
