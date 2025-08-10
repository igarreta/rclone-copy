# Secondary backup copy
This project will make copies of some directories to a remote storage to a secondary backup.
It will be written in Python 3.13 and will be run as a daily cron job.
As this project will not have external inputs, it will not run in a docker container.
Provide instructions to authorize rclone. The server does not have a web browser.

## General instructions
Use general and project CLAUDE.md files for general instructions. 

## Backup location
Backup origins may be mounted as read only. They may be external USB disk that could disconnect, and mounted on this server by a samba share.
Backup destination will be accessed with rclone, which should be previously configured. Rclone configuration will be validated using "rclone about [remote]:" command to confirm connectivity and check available space.

## Pre-flight checks 
These checks will be performed before starting any backup operations:
1. Check if rclone is installed and configured correctly.
2. Check if the directories listed in backup_copy_list are accessible. If not, send an alert.
3. Use "rclone about [remote]:" to check if the remote storage has at least 200 GB of free space. If not, send an alert and stop. Do this for each remote, differente rclone_path may share the same remote.
4. For each directory in backup_copy_list, calculate the total size of files that match the age criteria (using python_utils size utilities). If the total size exceeds the specified maximum size, send an alert and stop.

## Backup copy process (backup_copy_list)
Run this process for each directory in backup_copy_list based on cron schedule criteria. Only day-of-month and day-of-week fields are evaluated as this will be run daily at 5:00 AM by the server main cron.
1. For each directory in backup_copy_list, copy all files from the source_dir less than the specified number of days old to the specified rclone directory using rclone. Include files in subdirectories.
2. Directories may contain subdirectories dated like backup_20250807_034502. Backup subdirectories that are less than the specified number of days old.
3. Create directories for each backup with the name of the backup and the timestamp (format YYYY-MM-DD_HH-MM) to ensure unique directory names for multiple runs per day.
4. Keep the number of backup copies indicated in retention (number of backup directories to retain). If retention is not specified, keep 2 copies by default.
5. After successful backup, clean up old backup directories based on the retention count, keeping the most recent ones.


## Project Structure
Follow the standard Python project structure as defined in CLAUDE.md:
```
rclone-copy/
├── README.md
├── CLAUDE.md
├── pyproject.toml
├── config.yaml
├── main.py
├── python_utils/          # Git submodule
├── src/
│   ├── __init__.py
│   └── backup_manager.py
├── log/
└── var/
```

## Dependency management
This project uses `uv` for Python dependency management as specified in the project CLAUDE.md file.

Setup commands:
```bash
# Project initialization
uv venv
uv pip install -e .
```

Required dependencies in pyproject.toml:
- pydantic-settings (configuration management)
- PyYAML (configuration file parsing)

## cron job
The cron job will be run daily at 5:00 AM by the server main cron, using uv to activate the virtual environment.

Example cron configuration:
```bash
# Add to /etc/cron.d/rclone-backup  
0 5 * * * rsi cd /home/rsi/rclone-copy && uv run python main.py >> log/cron.log 2>&1
```


## Configuration
The configuration file (`config.yaml`) will be a YAML file with the following structure:
```yaml
# Notification configuration
email: # list of emails to send notifications to 
  - user@example.com

# Logging configuration
log_level: INFO # logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
log_file: log/rclone_copy.log # path to log file relative to project root

# System checks configuration
checks:
  min_free_space: 200GB # minimum free space required on remote storage

# Backup configuration
backup_copy_list: # list of directories to copy to remote storage
  - name: contabo1 # short name/identifier for the backup (required)
    source_dir: /mnt/backup_usb1/contabo1 # path to the source directory (required)
    rclone_path: onedrive:/GR_SRV03/backup/contabo1 # path to the rclone directory (required)
    max_size: 200MB # maximum size for the backup using KB/MB/GB format (optional, default = 1GB)
    max_age: 1 # maximum age in days of the files to be copied (optional, default = 0 = all files)
    schedule: "* * * * 1" # cron-like schedule: "minute hour day-of-month month day-of-week" (optional, default = "* * * * 1" = weekly on Monday)
    retention: 2 # number of backup copies to keep (optional, default = 2)

  - name: homeassistant
    source_dir: /mnt/hassio
    rclone_path: onedrive:/GR_SRV03/backup/homeassistant
    max_size: 200MB
    max_age: 1
    schedule: "* * * * 1" # cron-like schedule: "minute hour day-of-month month day-of-week" (optional, default = "* * * * 1" = weekly on Monday)
    retention: 7
```

#### Schedule Configuration
The `schedule` field uses cron-like syntax with the format: `"minute hour day-of-month month day-of-week"`

**Important notes:**
- Minutes and hours are always `*` (placeholders) since the script runs once daily at 5:00 AM
- Only day-of-month and day-of-week fields are used for scheduling
- Day-of-week: 1=Monday, 2=Tuesday, ..., 7=Sunday

**Common schedule examples:**
```yaml
schedule: "* * * * *"     # Every day
schedule: "* * * * 1"     # Every Monday (default)
schedule: "* * * * 1,3,5" # Monday, Wednesday, Friday
schedule: "* * 1,15 * *"  # 1st and 15th of every month
schedule: "* * 1 * *"     # 1st of every month
schedule: "* * * * 7"     # Every Sunday
schedule: "* * 10,20,30 * *" # 10th, 20th, and 30th of every month
```

### Configuration file location
The configuration file will be located at `config.yaml` in the project root directory.

### Configuration integrity
The configuration file will be validated using pydantic models. If the configuration is not valid, the program will exit with a critical error. 
The max_size field will be parsed using python_utils parse_size_to_bytes() function to support KB/MB/GB formats.


## Notification
Send email using python_utils EmailNotifier when process is completed with a summary of the results.
Include total size for each backup, copy name, latest file date, and any errors encountered.
Send only one email with all the results.

## Error handling
If a directory is not mounted, log the error, include it in the email summary, and continue with remaining backups.
If any rclone operation fails, log the error, include it in the email summary, and continue with the next backup. Do not implement retry logic.
If errors are detected, alerts will be sent via email using python_utils EmailNotifier with Gmail SMTP for all notifications and alerts.

## Metrics
Track only these metrics during execution:
- Total bytes transferred for each backup
- Total execution time for the entire process

Include these metrics in the email summary. Do not save metrics to files.

## Alert Process
Each alert will include:
- Timestamp
- Alert level (INFO, WARNING, ERROR, CRITICAL)
- Affected backup  name
- Detailed error message
- Relevant metrics (backup size, age, etc.)

## Logging
Use simple text-based logging with python_utils setup_backup_logging. Log to both console and file (log/rclone_copy.log). No structured or JSON logging required.

## Rclone setup instructions (headless server)
Since the server does not have a web browser, rclone must be configured using one of these methods:

1. **Remote configuration** (recommended):
   ```bash
   # On the server
   rclone config create onedrive onedrive --config-no-browser
   # Follow the URL on another machine with browser
   # Copy the resulting token back to the server
   ```

2. **Configuration file transfer**:
   ```bash
   # Configure rclone on a machine with browser
   # Copy ~/.config/rclone/rclone.conf to the server
   # Test with: rclone lsd onedrive:
   ```

3. **Validate configuration**:
   ```bash
   rclone config show         # Verify remote is configured
   rclone about onedrive:     # Test connectivity and check space
   rclone lsd onedrive:/      # List root directories
   ```

## Documentation
Provide a README.md file with instructions on how to install and run the project using uv. 
Include example configuration file and rclone setup instructions.
