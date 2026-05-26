import logging
from typing import Any, Callable, Coroutine

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config.schema import ScheduleConfig

logger = logging.getLogger(__name__)


class NewsScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._pipeline_callback: Callable[..., Coroutine[Any, Any, Any]] | None = None

    def set_pipeline(self, callback: Callable[..., Coroutine[Any, Any, Any]]) -> None:
        """Set the pipeline callback function to run on schedule."""
        self._pipeline_callback = callback

    def load_schedules(
        self, schedules: list[ScheduleConfig], timezone: str = "Asia/Seoul"
    ) -> None:
        """Load schedule configs and create jobs."""
        self.scheduler.remove_all_jobs()

        for sched in schedules:
            cron_parts = sched.cron.split()
            tz = sched.timezone or timezone

            trigger = CronTrigger(
                minute=cron_parts[0] if len(cron_parts) > 0 else "*",
                hour=cron_parts[1] if len(cron_parts) > 1 else "*",
                day=cron_parts[2] if len(cron_parts) > 2 else "*",
                month=cron_parts[3] if len(cron_parts) > 3 else "*",
                day_of_week=cron_parts[4] if len(cron_parts) > 4 else "*",
                timezone=tz,
            )

            self.scheduler.add_job(
                self._run_pipeline,
                trigger=trigger,
                id=sched.name,
                name=f"Schedule: {sched.name}",
                kwargs={
                    "schedule_name": sched.name,
                    "sites": sched.sites,
                    "recipients": sched.recipients,
                },
                replace_existing=True,
            )
            logger.info(f"Scheduled '{sched.name}' with cron '{sched.cron}' ({tz})")

    async def _run_pipeline(
        self, schedule_name: str, sites: list[str], recipients: list[str]
    ) -> None:
        if self._pipeline_callback:
            await self._pipeline_callback(
                schedule_name=schedule_name, sites=sites, recipients=recipients
            )

    def start(self) -> None:
        self.scheduler.start()
        logger.info("Scheduler started")

    def stop(self) -> None:
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    def get_next_runs(self) -> list[dict]:
        """Get info about next scheduled runs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append(
                {
                    "name": job.name,
                    "next_run": str(job.next_run_time) if job.next_run_time else "N/A",
                }
            )
        return jobs
