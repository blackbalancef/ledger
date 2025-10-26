#!/usr/bin/env python3
"""Database backup script with rotation and S3 upload support."""

import gzip
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from core.config import settings

# Ensure backups directory exists
BACKUPS_DIR = Path(settings.backup_local_path)
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)


def execute_pg_dump(host: str, port: int, database: str, user: str, password: str, output_file: Path) -> bool:
    """
    Execute pg_dump via Docker to create backup.
    
    Args:
        host: PostgreSQL host
        port: PostgreSQL port
        database: Database name
        user: Database user
        password: Database password
        output_file: Path to output file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Set password via PGPASSWORD environment variable
        env = os.environ.copy()
        env["PGPASSWORD"] = password
        
        # Execute pg_dump via docker exec
        cmd = [
            "docker", "exec", "finance_bot_db",
            "pg_dump",
            "-h", host,
            "-p", "5432",
            "-U", user,
            "-d", database,
            "--no-owner",
            "--no-privileges",
            "-F", "c",  # custom format
            "-f", f"/tmp/backup.dump"
        ]
        
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
        logger.info(f"pg_dump completed successfully")
        
        # Copy backup from container to host
        docker_cp_cmd = [
            "docker", "cp",
            "finance_bot_db:/tmp/backup.dump",
            str(output_file)
        ]
        subprocess.run(docker_cp_cmd, check=True)
        logger.info(f"Backup copied to {output_file}")
        
        # Compress the backup
        compressed_file = output_file.with_suffix(".dump.gz")
        with open(output_file, "rb") as f_in:
            with gzip.open(compressed_file, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        # Remove uncompressed file
        output_file.unlink()
        logger.info(f"Backup compressed to {compressed_file}")
        
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error executing pg_dump: {e}")
        logger.error(f"stdout: {e.stdout}")
        logger.error(f"stderr: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during backup: {e}")
        return False


def create_backup_filename() -> str:
    """Generate backup filename with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"backup_{timestamp}.dump.gz"


def upload_to_s3(local_path: Path, s3_key: str) -> bool:
    """
    Upload backup file to S3.
    
    Args:
        local_path: Local path to backup file
        s3_key: S3 object key
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import boto3
        from botocore.exceptions import ClientError
        
        s3_client = boto3.client(
            "s3",
            region_name=settings.backup_s3_region,
            aws_access_key_id=settings.effective_aws_access_key_id,
            aws_secret_access_key=settings.effective_aws_secret_access_key,
        )
        
        s3_client.upload_file(local_path, settings.backup_s3_bucket, s3_key)
        logger.info(f"Uploaded to S3: s3://{settings.backup_s3_bucket}/{s3_key}")
        return True
        
    except ClientError as e:
        logger.error(f"AWS S3 error: {e}")
        return False
    except Exception as e:
        logger.error(f"Error uploading to S3: {e}")
        return False


def rotate_backups():
    """
    Rotate backups according to 7-4-12 strategy:
    - Keep 7 daily backups
    - Keep 4 weekly backups (one per week)
    - Keep 12 monthly backups (one per month)
    """
    try:
        backups = sorted(BACKUPS_DIR.glob("backup_*.dump.gz"))
        
        if len(backups) <= 7:
            # Not enough backups to rotate
            return
        
        now = datetime.now()
        
        # Keep 7 daily backups (last 7 days)
        daily_backups = set()
        for i in range(7):
            day = now - timedelta(days=i)
            day_prefix = day.strftime("%Y%m%d")
            for backup in backups:
                if backup.name.startswith(f"backup_{day_prefix}"):
                    daily_backups.add(backup)
                    break
        
        # Keep 4 weekly backups (one per week)
        weekly_backups = set()
        for i in range(4):
            week_date = now - timedelta(weeks=i)
            week_prefix = week_date.strftime("%Y%m%d")
            for backup in backups:
                if backup.name.startswith(f"backup_{week_prefix}"):
                    weekly_backups.add(backup)
                    break
        
        # Keep 12 monthly backups (one per month)
        monthly_backups = set()
        for i in range(12):
            month_date = now - timedelta(days=i * 30)
            month_prefix = month_date.strftime("%Y%m")
            for backup in backups:
                if backup.name.startswith(f"backup_{month_prefix}"):
                    monthly_backups.add(backup)
                    break
        
        # Union of all backups to keep
        keep_backups = daily_backups | weekly_backups | monthly_backups
        
        # Delete backups not in keep set
        deleted_count = 0
        for backup in backups:
            if backup not in keep_backups:
                backup.unlink()
                deleted_count += 1
        
        if deleted_count > 0:
            logger.info(f"Rotated backups: deleted {deleted_count} old backup(s)")
            
    except Exception as e:
        logger.error(f"Error rotating backups: {e}")


def parse_database_url(url: str):
    """
    Parse database URL to extract connection parameters.
    
    Supports format: postgresql+asyncpg://user:password@host:port/database
    """
    try:
        # Remove the +asyncpg part
        clean_url = url.replace("+asyncpg://", "://")
        
        # Simple parsing
        parts = clean_url.split("://")[1]
        
        auth, rest = parts.split("@")
        user, password = auth.split(":")
        
        host_port, database = rest.split("/")
        if ":" in host_port:
            host, port = host_port.split(":")
        else:
            host = host_port
            port = "5432"
        
        return {
            "host": host,
            "port": int(port),
            "database": database,
            "user": user,
            "password": password,
        }
    except Exception as e:
        logger.error(f"Error parsing database URL: {e}")
        return None


def main():
    """Main backup function."""
    logger.info("Starting database backup...")
    
    # Parse database URL
    db_params = parse_database_url(settings.database_url)
    if not db_params:
        logger.error("Failed to parse database URL")
        sys.exit(1)
    
    # Create backup filename
    backup_filename = create_backup_filename()
    backup_path = BACKUPS_DIR / backup_filename
    
    # Verify database container is running
    try:
        subprocess.run(
            ["docker", "ps", "--filter", "name=finance_bot_db", "--format", "{{.Names}}"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        logger.error("Database container 'finance_bot_db' is not running")
        sys.exit(1)
    
    # Execute backup
    success = execute_pg_dump(
        host=db_params["host"],
        port=db_params["port"],
        database=db_params["database"],
        user=db_params["user"],
        password=db_params["password"],
        output_file=backup_path.with_suffix(""),
    )
    
    if not success:
        logger.error("Backup failed")
        sys.exit(1)
    
    compressed_path = backup_path
    
    # Upload to S3 if enabled
    if settings.backup_s3_enabled:
        s3_key = f"backups/{backup_filename}"
        upload_success = upload_to_s3(compressed_path, s3_key)
        if not upload_success:
            logger.warning("Failed to upload to S3, but local backup was created")
    
    # Rotate backups
    rotate_backups()
    
    logger.info(f"Backup completed successfully: {compressed_path}")
    logger.info(f"Backup size: {compressed_path.stat().st_size / (1024 * 1024):.2f} MB")


if __name__ == "__main__":
    main()

