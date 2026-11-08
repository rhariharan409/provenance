import pytest
from app.config import Settings


def test_database_url_normalization():
    # postgres:// converted to postgresql+psycopg:// with sslmode preserved
    s1 = Settings(DATABASE_URL="postgres://user:pass@host:5432/db?sslmode=require")
    assert s1.DATABASE_URL == "postgresql+psycopg://user:pass@host:5432/db?sslmode=require"

    # postgresql:// converted to postgresql+psycopg://
    s2 = Settings(DATABASE_URL="postgresql://user:pass@host:5432/db")
    assert s2.DATABASE_URL == "postgresql+psycopg://user:pass@host:5432/db"

    # postgresql+psycopg:// remains untouched
    s3 = Settings(DATABASE_URL="postgresql+psycopg://user:pass@host:5432/db?sslmode=require")
    assert s3.DATABASE_URL == "postgresql+psycopg://user:pass@host:5432/db?sslmode=require"


def test_production_secret_validation():
    # Production with short session secret fails
    with pytest.raises(ValueError, match="SESSION_SECRET"):
        Settings(
            ENV="production",
            SESSION_SECRET="short-secret",
            PASSPORT_SIGNING_SECRET="a" * 32,
        )

    # Production with short passport secret fails
    with pytest.raises(ValueError, match="PASSPORT_SIGNING_SECRET"):
        Settings(
            ENV="production",
            SESSION_SECRET="a" * 32,
            PASSPORT_SIGNING_SECRET="short",
        )

    # Production with both secrets >= 32 chars succeeds
    s = Settings(
        ENV="production",
        SESSION_SECRET="a" * 32,
        PASSPORT_SIGNING_SECRET="b" * 32,
    )
    assert s.is_production is True


def test_missing_clone_triggers_recollection(monkeypatch, tmp_path):
    from unittest.mock import patch, MagicMock
    from app.models.projects import Project, ProjectStatus
    from app.models.users import User, UserRole
    from tests.conftest import TestSessionLocal
    from app.services.analysis.runner import run_analysis

    session = TestSessionLocal()
    user_id = None
    project_id = None
    try:
        user = User(
            github_id=999901,
            username="reclone_user",
            display_name="Reclone User",
            email="reclone@example.com",
            role=UserRole.student,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

        missing_dir = str(tmp_path / "wiped_disk.git")
        project = Project(
            owner_id=user.id,
            repo_url="https://github.com/org/repo.git",
            repo_full_name="org/repo",
            name="repo",
            github_owner="org",
            github_repo="repo",
            default_branch="main",
            clone_path=missing_dir,
            status=ProjectStatus.ready,
            analysis_status="pending",
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        project_id = project.id

        recollection_called = False

        def fake_run_collection(pid, **kwargs):
            nonlocal recollection_called
            recollection_called = True
            # Create the missing directory so analysis can proceed or finish
            import os
            os.makedirs(missing_dir, exist_ok=True)

        with patch("app.services.collector.run_collection", side_effect=fake_run_collection):
            with patch("app.services.analysis.runner._resolve_head_sha", return_value="abc1234"):
                with patch("app.services.analysis.runner._list_candidate_files") as mock_list:
                    from app.services.analysis.runner import CandidateFilesResult
                    mock_list.return_value = CandidateFilesResult([], 0, 0, {})
                    run_analysis(project_id, db_factory=TestSessionLocal)

        assert recollection_called is True
        session.expire_all()
        refreshed = session.query(Project).filter(Project.id == project_id).first()
        assert refreshed is not None
        assert refreshed.progress_step in ("Re-collecting repository history...", "Analysis complete")

    finally:
        if project_id:
            session.query(Project).filter(Project.id == project_id).delete()
        if user_id:
            session.query(User).filter(User.id == user_id).delete()
        session.commit()
        session.close()
