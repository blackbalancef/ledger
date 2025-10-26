#!/usr/bin/env python3
"""Database restore script."""

import gzip
import os
import shutil
import subprocess
import sys
from pathlib import Path

from loguru import logger

from core.config import settings

BACKUPS_DIR = Path(settings.backup_local_path)


def list_backups() -> list[Path]:
    """List all available backups sorted by date."""
    backups = sorted(BACKUPS_DIR.glob("backup_*.dump.gz"), reverse=True)
    return backups


def list_s3_backups() -> list[str]:
    """List all backups available in S3."""
    try:
        import boto3
        from botocore.exceptions import ClientError
        
        s3_client = boto3.client(
            "s3",
            region_name=settings.backup_s3_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        
        response = s3_client.list_objects_v2(
            Bucket=settings.backup_s3_bucket,
            Prefix="backups/",
        )
        
        if "Contents" not in response:
            return []
        
        backups = [obj["Key"] for obj in response["Contents"] if obj["Key"].endswith(".dump.gz")]
        return sorted(backups, reverse=True)
        
    except Exception as e:
        logger.error(f"Error listing S3 backups: {e}")
        return []


def download_from_s3(s3_key: str, local_path: Path) -> bool:
    """
    Download backup file from S3.
    
    Args:
        s3_key: S3 object key
        local_path: Local path to save file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import boto3
        from botocore.exceptions import ClientError
        
        s3_client = boto3.client(
            "s3",
            region_name=settings.backup_s3_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        
        s3_client.download_file(settings.backup_s3_bucket, s3_key, local_path)
        logger.info(f"Downloaded from S3: {s3_key}")
        return True
        
    except Exception as e:
        logger.error(f"Error downloading from S3: {e}")
        return False


def decompress_backup(compressed_path: Path, decompressed_path: Path) -> bool:
    """Decompress gzip backup file."""
    try:
        with gzip.open(compressed_path, "rb") as f_in:
            with open(decompressed_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        logger.info(f"Decompressed backup to {decompressed_path}")
        return True
    except Exception as e:
        logger.error(f"Error decompressing backup: {e}")
        return False


def restore_backup(backup_path: Path, host: str, port: int, database: str, user: str, password: str) -> bool:
    """
    Restore database from backup using pg_restore via Docker.
    
    Args:
        backup_path: Path to backup file
        host: PostgreSQL host
        port: PostgreSQL port
        database: Database name
        user: Database user
        password: Database password
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Set password via PGPASSWORD environment variable
        env = os.environ.copy()
        env["PGPASSWORD"] = password
        
        # Copy backup to container
        docker_cp_cmd = [
            "docker", "cp",
            str(backup_path),
            "finance_bot_db:/tmp/restore.dump"
        ]
        subprocess.run(docker_cp_cmd, check=True)
        logger.info(f"Backup copied to container")
        
        # Drop existing connections (using psql)
        terminate_cmd = [
            "docker", "exec", "finance_bot_db",
            "psql",
            "-h", host,
            "-p", "5432",
            "-U", user,
            "-d", "postgres",
            "-c", f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{database}' AND pid <> pg_backend_pid();"
        ]
        subprocess.run(terminate_cmd, env=env, capture_output=True)
        
        # Drop and recreate database
        drop_db_cmd = [
            "docker", "exec", "finance_bot_db",
            "psql",
            "-h", host,
            "-p", "5432",
            "-U", user,
            "-d", "postgres",
            "-c", f"DROP DATABASE IF EXISTS {database};"
        ]
        subprocess.run(drop_db_cmd, env=env, check=True)
        logger.info("Existing database dropped")
        
        create_db_cmd = [
            "docker", "exec", "finance_bot_db",
            "psql",
            "-h", host,
            "-p", "5432",
            "-U", user,
            "-d", "postgres",
            "-c", f"CREATE DATABASE {database};"
        ]
        subprocess.run(create_db_cmd, env=env, check=True)
        logger.info("Database created")
        
        # Restore from backup
        restore_cmd = [
            "docker", "exec", "finance_bot_db",
            "pg_restore",
            "-h", host,
            "-p", "5432",
            "-U", user,
            "-d", database,
            "--no-owner",
            "--no-privileges",
            "--verbose",
            "/tmp/restore.dump"
        ]
        result = subprocess.run(restore_cmd, env=env, check=True, capture_output=True, text=True)
        logger.info(f"pg_restore completed")
        
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error restoring backup: {e}")
        logger.error(f"stdout: {e.stdout}")
        logger.error(f"stderr: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during restore: {e}")
        return False


def parse_database_url(url: str):
    """Parse database URL to extract connection parameters."""
    try:
        clean_url = url.replace("+asyncpg://", "://")
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
    """Main restore function."""
    logger.info("Starting database restore...")
    
    # Parse database URL
    db_params = parse_database_url(settings.database_url)
    if not db_params:
        logger.error("Failed to parse database URL")
        sys.exit(1)
    
    # List available backups
    local_backups = list_backups()
    
    logger.info("Available local backups:")
    if not local_backups:
        logger.error("No backups found locally")
        sys.exit(1)
    
    # Display backups
    for i, backup in enumerate(local_backups, 1):
        size_mb = backup.stat().st_size / (1024 * 1024)
        logger.info(f"{i}. {backup.name} ({size_mb:.2f} MB)")
    
    # In interactive mode, prompt for selection
    if len(sys.argv) > 1:
        try:
            index = int(sys.argv[1]) - 1
            if index < 0 or index >= len(local_backups):
                logger.error("Invalid backup index")
                sys.exit(1)
            selected_backup = local_backups[index]
        except ValueError:
            logger.error("Invalid backup index")
            sys.exit(1)
    else:
        # Use most recent backup
        selected_backup = local_backups[0]
        logger.info(f"Using most recent backup: {selected_backup.name}")
    
    # Ask for confirmation
    logger.warning("This will DROP and recreate the database. All current data will be lost!")
    logger.warning(f"Restoring from: {selected_backup.name}")
    
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
    
    # Decompress backup
    decompressed_path = selected_backup.with_suffix("")
    if not decompress_backup(selected_backup, decompressed_path):
        logger.error("Failed to decompress backup")
        sys.exit(1)
    
    try:
        # Restore backup
        success = restore_backup(
            backup_path=decompressed_path,
            host=db_params["host"],
            port=db_params["port"],
            database=db_params["database"],
            user=db_params["user"],
            password=db_params["password"],
        )
        
        if not success:
            logger.error("Restore failed")
            sys.exit(1)
        
        logger.info("Database restore completed successfully!")
        
    finally:
        # Clean up decompressed file
        if decompressed_path.exists():
            decompressed_path.unlink()


if __name__ == "__main__":
    main()

