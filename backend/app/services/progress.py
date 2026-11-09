from contextlib import contextmanager
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple
import uuid
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.projects import Project

logger = logging.getLogger(__name__)

# In-memory throttle tracker: project_id_str -> (last_timestamp, last_step)
_PROGRESS_THROTTLE: Dict[str, Tuple[float, str]] = {}
_THROTTLE_LOCK = threading.Lock()


def set_progress(
    project_id: uuid.UUID | str,
    step: str,
    current: Optional[int] = None,
    total: Optional[int] = None,
    db_factory: Callable[[], Session] = SessionLocal,
) -> None:
    """
    Updates progress on the project with throttling:
    writes to database at most once per second and immediately on step change
    or on completion (current == total). Uses a short session and never blocks or fails.
    """
    pid_str = str(project_id)
    now = time.time()

    should_write = False
    with _THROTTLE_LOCK:
        last_info = _PROGRESS_THROTTLE.get(pid_str)
        if last_info is None:
            should_write = True
            _PROGRESS_THROTTLE[pid_str] = (now, step)
        else:
            last_time, last_step = last_info
            if step != last_step or (current is not None and total is not None and current >= total) or (now - last_time >= 1.0):
                should_write = True
                _PROGRESS_THROTTLE[pid_str] = (now, step)

    if not should_write:
        return

    try:
        db = db_factory()
        try:
            proj_uuid = uuid.UUID(pid_str) if isinstance(project_id, str) else project_id
            proj = db.query(Project).filter(Project.id == proj_uuid).first()
            if proj:
                proj.progress_step = step
                proj.progress_current = current
                proj.progress_total = total
                if current is not None and total is not None and total > 0:
                    proj.progress_percent = min(100, max(0, int((current / total) * 100)))
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.debug("Non-fatal progress update error for project %s: %s", project_id, e)


def record_step_timing(
    project_id: uuid.UUID | str,
    step_name: str,
    seconds: float,
    db_factory: Callable[[], Session] = SessionLocal,
) -> None:
    """
    Records elapsed seconds for a named step into project.timings. Never logs secrets.
    """
    pid_str = str(project_id)
    sec_rounded = round(seconds, 3)
    logger.info("Timing [%s] %s: %.3fs", pid_str, step_name, sec_rounded)

    try:
        db = db_factory()
        try:
            proj_uuid = uuid.UUID(pid_str) if isinstance(project_id, str) else project_id
            proj = db.query(Project).filter(Project.id == proj_uuid).first()
            if proj:
                curr_timings = dict(proj.timings or {})
                curr_timings[step_name] = sec_rounded
                proj.timings = curr_timings
                # Keep timing_stats synced for backwards compatibility
                proj.timing_stats = curr_timings
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.debug("Non-fatal timing record error for project %s: %s", project_id, e)


@contextmanager
def step_timer(
    project_id: uuid.UUID | str,
    step_name: str,
    db_factory: Callable[[], Session] = SessionLocal,
):
    """
    Context manager that times the execution of a step and saves it to projects.timings.
    Steps include: estimate, clone, read_history, api_enrichment, identity, blame, scoring, total.
    """
    start_time = time.time()
    try:
        yield
    finally:
        elapsed = time.time() - start_time
        record_step_timing(project_id, step_name, elapsed, db_factory=db_factory)

