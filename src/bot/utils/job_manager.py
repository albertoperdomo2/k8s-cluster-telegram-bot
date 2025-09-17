import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ExecJob:
    """Represents an async exec job."""

    job_id: str
    user_id: int
    chat_id: int
    pod_name: str
    namespace: str
    command: list
    status: str  # pending, running, completed, failed
    start_time: datetime
    end_time: Optional[datetime] = None
    output: Optional[str] = None
    error: Optional[str] = None


class JobManager:
    """Manages async execution jobs."""

    def __init__(self):
        """Initialize job manager."""
        self.jobs: Dict[str, ExecJob] = {}
        self.active_tasks: Dict[str, asyncio.Task] = {}

    def create_job(
        self, user_id: int, chat_id: int, pod_name: str, namespace: str, command: list
    ) -> str:
        """Create a new exec job."""
        job_id = str(uuid.uuid4())[:8]  # Short ID for display

        job = ExecJob(
            job_id=job_id,
            user_id=user_id,
            chat_id=chat_id,
            pod_name=pod_name,
            namespace=namespace,
            command=command,
            status="pending",
            start_time=datetime.now(),
        )

        self.jobs[job_id] = job
        logger.info(f"Created exec job {job_id} for pod {pod_name}")
        return job_id

    def get_job(self, job_id: str) -> Optional[ExecJob]:
        """Get job by ID."""
        return self.jobs.get(job_id)

    def update_job_status(
        self, job_id: str, status: str, output: str = None, error: str = None
    ):
        """Update job status and results."""
        if job_id in self.jobs:
            job = self.jobs[job_id]
            job.status = status
            if output is not None:
                job.output = output
            if error is not None:
                job.error = error
            if status in ["completed", "failed"]:
                job.end_time = datetime.now()
                # Clean up task reference
                if job_id in self.active_tasks:
                    del self.active_tasks[job_id]

    def get_user_jobs(self, user_id: int) -> list:
        """Get all jobs for a user."""
        return [job for job in self.jobs.values() if job.user_id == user_id]

    def start_job_task(self, job_id: str, task: asyncio.Task):
        """Register an active task for a job."""
        self.active_tasks[job_id] = task
        if job_id in self.jobs:
            self.jobs[job_id].status = "running"

    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Clean up old completed jobs."""
        cutoff_time = datetime.now()
        cutoff_time = cutoff_time.replace(hour=cutoff_time.hour - max_age_hours)

        jobs_to_remove = []
        for job_id, job in self.jobs.items():
            if (
                job.status in ["completed", "failed"]
                and job.end_time
                and job.end_time < cutoff_time
            ):
                jobs_to_remove.append(job_id)

        for job_id in jobs_to_remove:
            del self.jobs[job_id]
            logger.info(f"Cleaned up old job {job_id}")
