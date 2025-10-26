"""Scheduled backup tasks using APScheduler."""

import subprocess
import sys
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from core.config import settings

# Global scheduler instance
scheduler = AsyncIOScheduler()


async def run_backup_task():
    """Run backup task using the backup script."""
    logger.info("Running scheduled database backup...")
    
    try:
        # Run backup script
        backup_script = Path(__file__).parent.parent.parent / "scripts" / "backup.py"
        result = subprocess.run(
            [sys.executable, str(backup_script)],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout
        )
        
        if result.returncode == 0:
            logger.info(f"Scheduled backup completed successfully")
            logger.debug(f"Backup output: {result.stdout}")
        else:
            logger.error(f"Scheduled backup failed: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        logger.error("Backup task timed out after 5 minutes")
    except Exception as e:
        logger.error(f"Error running scheduled backup: {e}")


def setup_backup_scheduler():
    """Setup the APScheduler to run backups according to cron schedule."""
    try:
        # Parse cron expression (format: minute hour day month day_of_week)
        cron_parts = settings.backup_schedule_cron.strip().split()
        
        if len(cron_parts) != 5:
            logger.error(f"Invalid cron expression: {settings.backup_schedule_cron}")
            logger.info("Using default cron: 0 3 * * * (3 AM daily)")
            cron_parts = ["0", "3", "*", "*", "*"]
        
        minute, hour, day, month, day_of_week = cron_parts
        
        # Add job to scheduler
        scheduler.add_job(
            run_backup_task,
            CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
            ),
            id="database_backup",
            name="Daily Database Backup",
            max_instances=1,
            misfire_grace_time=3600,  # 1 hour grace period
        )
        
        logger.info(f"Scheduled backup task: {settings.backup_schedule_cron}")
        logger.info("Backup scheduler started")
        
    except Exception as e:
        logger.error(f"Error setting up backup scheduler: {e}")


async def start_backup_scheduler():
    """Start the backup scheduler."""
    if scheduler.running:
        logger.warning("Scheduler already running")
        return
    
    setup_backup_scheduler()
    scheduler.start()
    logger.info("Backup scheduler started")


async def stop_backup_scheduler():
    """Stop the backup scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Backup scheduler stopped")


def test_backup_now():
    """Manually trigger a backup (for testing)."""
    import asyncio
    asyncio.run(run_backup_task())

