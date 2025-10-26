# Database Backup Guide

This guide explains how to set up and use the database backup system for the Finance Telegram Bot.

## Overview

The backup system provides:
- **Local backups**: Stored in the `./backups/` directory
- **S3 backups**: Optional cloud storage via AWS S3
- **Automatic scheduling**: Daily backups using APScheduler
- **Smart rotation**: Keeps 7 daily, 4 weekly, and 12 monthly backups

## Quick Start

### 1. Basic Setup (Local Backups Only)

The backup system is configured by default to use local storage. No additional configuration needed!

1. Start the bot:
```bash
poe up
```

2. Create a manual backup:
```bash
poe backup
```

3. List available backups:
```bash
poe backup-list
```

4. Restore from a backup:
```bash
poe restore
```

The restore command will show a list of available backups and restore the most recent one by default.

### 2. Enable S3 Backup Storage

To enable automatic cloud backups to AWS S3:

1. **Create an S3 bucket**:
   - Log in to your AWS account
   - Go to S3 and create a new bucket (e.g., `finance-bot-backups`)
   - Note the bucket name and region

2. **Create IAM credentials**:
   - Go to IAM → Users → Create User
   - Attach a policy with permissions to upload to your bucket
   - Example policy:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": ["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
         "Resource": [
           "arn:aws:s3:::your-bucket-name",
           "arn:aws:s3:::your-bucket-name/*"
         ]
       }
     ]
   }
   ```
   - Create access keys and save them

3. **Update your `.env` file**:
   ```env
   # Backup Settings
   BACKUP_LOCAL_PATH=./backups
   BACKUP_S3_ENABLED=true
   BACKUP_S3_BUCKET=finance-bot-backups
   BACKUP_S3_REGION=eu-central-1
   AWS_ACCESS_KEY_ID=your_access_key
   AWS_SECRET_ACCESS_KEY=your_secret_key
   BACKUP_SCHEDULE_CRON=0 3 * * *
   ```

4. **Restart the bot**:
```bash
poe restart
```

## Configuration Options

### Environment Variables

Add these to your `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| `BACKUP_LOCAL_PATH` | Directory for local backups | `./backups` |
| `BACKUP_S3_ENABLED` | Enable S3 backups | `false` |
| `BACKUP_S3_BUCKET` | S3 bucket name | - |
| `BACKUP_S3_REGION` | AWS region | `eu-central-1` |
| `AWS_ACCESS_KEY_ID` | AWS access key | - |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | - |
| `BACKUP_SCHEDULE_CRON` | Cron schedule for backups | `0 3 * * *` |

### Cron Schedule Format

The `BACKUP_SCHEDULE_CRON` uses standard cron syntax:
```
minute hour day month day_of_week
```

Examples:
- `0 3 * * *` - Every day at 3 AM
- `0 2 * * 0` - Every Sunday at 2 AM
- `0 */6 * * *` - Every 6 hours
- `0 0 1 * *` - First day of every month at midnight

## Backup Rotation Strategy

The system automatically manages backup retention using a 7-4-12 strategy:

- **7 Daily**: Keep the most recent 7 days of backups
- **4 Weekly**: Keep one backup per week for the last 4 weeks
- **12 Monthly**: Keep one backup per month for the last 12 months

Backups older than these periods are automatically deleted to save disk space.

## Manual Commands

### Create Backup

```bash
poe backup
```

This creates a backup with timestamp `backup_YYYYMMDD_HHMMSS.dump.gz`.

### List Backups

```bash
poe backup-list
```

Or manually:
```bash
ls -lh backups/
```

### Restore Database

```bash
poe restore
```

This will:
1. Show a list of available backups
2. Ask for confirmation (restores most recent by default)
3. DROP and recreate the database
4. Restore from the selected backup

**Warning**: Restoring will delete all current data!

### Restore Specific Backup

```bash
poe restore 3  # Restores the 3rd backup in the list
```

## Backup File Format

- **Format**: PostgreSQL custom format (`.dump`)
- **Compression**: Gzip compressed (`.gz`)
- **Naming**: `backup_YYYYMMDD_HHMMSS.dump.gz`

Example: `backup_20241026_143022.dump.gz`

## Automatic Backups

When the bot is running, backups are automatically created according to the `BACKUP_SCHEDULE_CRON` schedule.

The scheduler:
- Runs backups as a background task
- Prevents multiple backups from running simultaneously
- Logs all backup operations
- Handles errors gracefully

## How It Works

### Backup Process

1. **Connect**: Connect to PostgreSQL via Docker
2. **Dump**: Execute `pg_dump` in the database container
3. **Extract**: Copy backup from container to host
4. **Compress**: Compress backup using gzip
5. **Upload**: (Optional) Upload to S3
6. **Rotate**: Clean up old backups according to retention policy

### Restore Process

1. **Select**: Choose backup to restore (from local or S3)
2. **Decompress**: Uncompress the backup file
3. **Terminate**: Drop all database connections
4. **Drop**: Drop existing database
5. **Create**: Create new database
6. **Restore**: Execute `pg_restore` from the backup
7. **Cleanup**: Remove temporary files

## Troubleshooting

### "Database container not running"

Make sure the bot and database containers are running:
```bash
docker ps
```

Start the services:
```bash
poe up
```

### "No backups found"

Check if the backups directory exists:
```bash
ls -la backups/
```

Create a backup manually:
```bash
poe backup
```

### S3 Upload Fails

Check your AWS credentials:
```bash
echo $AWS_ACCESS_KEY_ID
echo $AWS_SECRET_ACCESS_KEY
```

Verify S3 permissions by testing with AWS CLI:
```bash
aws s3 ls s3://your-bucket-name/
```

### Out of Disk Space

The backup rotation should prevent this, but if needed:
```bash
# Check disk usage
du -sh backups/

# Manually remove old backups
rm backups/backup_20240101_*.dump.gz
```

## Best Practices

1. **Test your backups regularly**: Periodically restore from a backup to ensure they work
2. **Monitor disk space**: Ensure you have enough disk space for backups
3. **Use S3 for production**: Enable S3 backups for important deployments
4. **Document your schedule**: Keep a record of your backup schedule
5. **Keep credentials secure**: Never commit AWS credentials to version control

## Recovery Scenarios

### Scenario 1: Volume Deleted Accidentally

```bash
# Stop the bot
poe down

# Recreate the database (this creates a new empty database)
poe up

# Restore from backup
poe restore

# Restart the bot
poe restart
```

### Scenario 2: Corrupted Database

```bash
# Stop the bot
poe down

# Drop the corrupted database
docker exec finance_bot_db psql -U finance_user -d postgres -c "DROP DATABASE finance_bot;"
docker exec finance_bot_db psql -U finance_user -d postgres -c "CREATE DATABASE finance_bot;"

# Restore from backup
poe restore

# Start the bot
poe up
```

### Scenario 3: Migrating to New Server

On old server:
```bash
poe backup
# Transfer backups/ directory to new server
```

On new server:
```bash
# Set up environment and start services
poe up

# Copy backups to new server
scp -r backups/ user@newserver:./finance_tg_bot/

# Restore from backup
poe restore
```

## Security Considerations

1. **Backup files contain sensitive data**: Protect your backups
2. **Encryption**: Consider encrypting backups if storing in cloud
3. **Access control**: Limit access to backup files
4. **Rotation**: Regular rotation prevents accumulation of old data
5. **Testing**: Regularly test restore procedures

## Monitoring

Check backup logs:
```bash
# View bot logs
poe logs

# Search for backup-related logs
poe logs | grep -i backup
```

The backup system logs all operations with timestamps. Look for:
- Backup creation: `"Starting database backup..."`
- Backup completion: `"Backup completed successfully"`
- Rotation activity: `"Rotated backups: deleted X old backup(s)"`
- S3 upload: `"Uploaded to S3: s3://..."`

## Additional Resources

- PostgreSQL documentation: https://www.postgresql.org/docs/
- pg_dump documentation: https://www.postgresql.org/docs/current/app-pgdump.html
- AWS S3 documentation: https://docs.aws.amazon.com/s3/
- APScheduler documentation: https://apscheduler.readthedocs.io/

