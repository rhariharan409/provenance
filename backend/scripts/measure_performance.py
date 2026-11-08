import time
import uuid
from app.db import SessionLocal
from app.models.projects import Project
from app.models.analysis_runs import AnalysisRun
from app.services.collector import run_collection
from app.services.analysis.runner import run_analysis

def main():
    db = SessionLocal()
    try:
        # Find rhariharan409/Smart_face_attendance_system
        project = db.query(Project).filter(
            Project.repo_full_name.ilike("%rhariharan409/Smart_face_attendance_system%")
        ).first()

        if not project:
            print("Project rhariharan409/Smart_face_attendance_system not found in DB.")
            return

        print(f"Benchmarking Project: {project.repo_full_name} ({project.id})")

        # 1. Run Collection
        t_col_start = time.time()
        run_collection(project.id)
        col_duration = time.time() - t_col_start

        # 2. Run Analysis
        t_ana_start = time.time()
        run_analysis(project.id)
        ana_duration = time.time() - t_ana_start

        db.refresh(project)
        latest_run = (
            db.query(AnalysisRun)
            .filter(AnalysisRun.project_id == project.id)
            .order_by(AnalysisRun.started_at.desc())
            .first()
        )

        print("\n=== TIMINGS MEASUREMENT ===")
        print(f"Measured Collection Total: {col_duration:.3f}s")
        print(f"Measured Analysis Total:   {ana_duration:.3f}s")
        print(f"Combined Total:            {col_duration + ana_duration:.3f}s")

        print("\n=== STORED TIMING STATS IN DB ===")
        print(f"project.timing_stats: {project.timing_stats}")
        if latest_run and latest_run.stats:
            print(f"analysis_run.stats.timings: {latest_run.stats.get('timings')}")

    finally:
        db.close()

if __name__ == "__main__":
    main()

