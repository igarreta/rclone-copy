# rclone-copy

Secondary backup copy system using rclone with cron-based scheduling. This Python application automatically backs up directories to remote storage with configurable scheduling, retention policies, and comprehensive monitoring.

## Features

- **Dual backup modes**: Support for both rclone remote storage and local filesystem backups
- **Cron-based scheduling**: Flexible scheduling using cron syntax for daily, weekly, monthly, or custom intervals
- **Multiple backup sources**: Configure multiple directories with individual settings
- **Remote storage support**: Works with any rclone-supported remote (OneDrive, Google Drive, S3, etc.)
- **Local filesystem backups**: Direct backup to local directories when run with path argument
- **Uptime Kuma monitoring**: Automatic health monitoring with push notifications
- **Size and age filtering**: Control backup size and file age limits
- **Retention management**: Automatic cleanup of old backups
- **Pre-flight checks**: Validates sources, destinations, and available space before starting
- **Dual logging**: Console output for CLI usage, file logging for cron jobs
- **Email notifications**: Comprehensive backup summaries with metrics
- **Robust error handling**: Continues processing other backups if one fails

## Requirements

- Python 3.13+
- rclone (must be configured with remote storage)  
- uv (for dependency management)
- Uptime Kuma (optional, for health monitoring)

## Installation

1. **Clone the repository** (with submodules):
   ```bash
   git clone --recurse-submodules https://github.com/yourusername/rclone-copy.git
   cd rclone-copy
   ```

   If you already cloned without submodules:
   ```bash
   git submodule update --init --recursive
   ```

2. **Set up Python environment**:
   ```bash
   uv venv
   uv pip install -e .
   ```

3. **Configure rclone** (see [Rclone Setup](#rclone-setup) section below)

4. **Configure the application**:
   ```bash
   cp config.yaml config.yaml.backup  # Keep the example
   # Edit config.yaml with your backup settings
   ```

5. **Optional: Set up Uptime Kuma monitoring** (see [Uptime Kuma Integration](#uptime-kuma-integration) section below)

## Configuration

### Main Configuration (`config.yaml`)

The configuration file defines backup sources, destinations, schedules, and notification settings:

```yaml
# Email notifications
email:
  - admin@example.com

# Logging
log_level: INFO
log_file: log/rclone_copy.log

# System checks
checks:
  min_free_space: 200GB

# Backup definitions
backup_copy_list:
  - name: daily_documents
    source_dir: /home/user/documents
    rclone_path: onedrive:/backups/documents
    max_size: 500MB
    max_age: 7
    schedule: "* * * * *"  # Every day
    retention: 7
```

### Schedule Configuration

The `schedule` field uses cron syntax: `"minute hour day-of-month month day-of-week"`

Since the script runs daily at 5:00 AM, minutes and hours are always `*` (placeholders). Only day-of-month and day-of-week fields control when backups run.

**Common examples:**
```yaml
schedule: "* * * * *"       # Every day
schedule: "* * * * 1"       # Every Monday (1=Monday, 7=Sunday)
schedule: "* * * * 1,3,5"   # Monday, Wednesday, Friday
schedule: "* * 1 * *"       # 1st of every month
schedule: "* * 1,15 * *"    # 1st and 15th of every month
schedule: "* * 10,20,30 * *" # 10th, 20th, and 30th of every month
```

### Configuration Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | ✓ | - | Unique backup identifier |
| `source_dir` | ✓ | - | Absolute path to source directory |
| `rclone_path` | ✓ | - | Remote path (format: `remote:/path`) |
| `max_size` | | `1GB` | Maximum backup size (KB/MB/GB/TB) |
| `max_age` | | `0` | File age limit in days (0 = all files) |
| `schedule` | | `"* * * * 1"` | Cron schedule (Monday weekly) |
| `retention` | | `2` | Number of backup copies to keep |
| `rclone_enabled` | | `true` | Enable cloud backups via rclone (false = local mode only) |

### Configuration Management with Symlinks

For better configuration management and backup, the `config.yaml` file is implemented as a symlink to `~/etc/rclone-copy-config.yaml`:

```bash
# The actual configuration is stored in ~/etc for backup purposes
ls -la config.yaml
# lrwxrwxrwx ... config.yaml -> /home/user/etc/rclone-copy-config.yaml
```

**Benefits of this approach:**
- **Centralized configuration**: All server configurations stored in `~/etc/`
- **Backup safety**: Configuration preserved independently of project directory
- **Easy maintenance**: Edit configuration from any location
- **Git-friendly**: Symlink allows project to work while keeping sensitive config out of repo

**Setup symlink configuration:**
```bash
# Create ~/etc directory
mkdir -p ~/etc

# Move existing config to ~/etc
mv config.yaml ~/etc/rclone-copy-config.yaml

# Create symlink back to project
ln -s ~/etc/rclone-copy-config.yaml config.yaml
```

**Editing configuration:**
```bash
# Edit from project directory
vim config.yaml

# Or edit directly from ~/etc
vim ~/etc/rclone-copy-config.yaml
```



## Uptime Kuma Integration

The application includes built-in integration with [Uptime Kuma](https://github.com/louislam/uptime-kuma) for automated health monitoring and push notifications.

### Features

- **Smart monitoring**: Only monitors rclone mode backups (cloud storage operations)
- **Push notifications**: HTTP GET requests to Uptime Kuma push monitor endpoint  
- **Status mapping**: Success/failure status based on backup results
- **Retry logic**: Automatic retry with 2-minute delay on notification failures
- **Error isolation**: Notification failures don't affect backup operation

### Setup Uptime Kuma Monitoring

1. **Create Push Monitor in Uptime Kuma**:
   - Open Uptime Kuma web interface
   - Create new monitor of type "Push"
   - Copy the push URL (format: `http://localhost:3001/api/push/MONITOR_ID`)

2. **Update Script Configuration**:
   The current implementation uses push URL: `http://localhost:3001/api/push/MhyfEdOgdA`
   
   To change the monitor ID, edit the `send_uptime_kuma_notification()` function in `main.py`:
   ```python
   base_url = "http://localhost:3001/api/push/YOUR_MONITOR_ID"
   ```

### Notification Behavior

**When notifications are sent:**
- ✅ **Rclone mode** (`python main.py`): Always sends notifications
- ❌ **Local filesystem mode** (`python main.py /path`): Never sends notifications  
- ❌ **Dry-run mode** (`python main.py --dry-run`): Never sends notifications

**Status mapping:**
- **Success** (`return 0`): `status=up&msg=OK`
- **Configuration errors** (`return 1`): `status=down&msg=FAILED`
- **Backup failures** (`return 2`): `status=down&msg=FAILED`

### Troubleshooting Uptime Kuma

**Test connectivity:**
```bash
# Test manual notification
curl "http://localhost:3001/api/push/MhyfEdOgdA?status=up&msg=TEST&ping="
```

**Check logs for notification errors:**
```bash
# Look for Uptime Kuma related messages
grep -i "uptime kuma" log/rclone_copy.log

# Common log messages:
# "Uptime Kuma notification sent successfully"
# "Uptime Kuma notification failed, retrying in 2 minutes..."
# "Uptime Kuma notification failed on retry, giving up"
```

## Rclone Setup

Since the server doesn't have a web browser, use one of these methods:

### Method 1: Remote Configuration (Recommended)
```bash
# On the server
rclone config create onedrive onedrive --config-no-browser

# Follow the URL on another machine with browser
# Copy the resulting token back to the server
```

### Method 2: Configuration File Transfer
```bash
# Configure rclone on a machine with browser
rclone config

# Copy the config to the server
scp ~/.config/rclone/rclone.conf user@server:~/.config/rclone/
```

### Validate Configuration
```bash
rclone config show         # Verify remote is configured
rclone about onedrive:     # Test connectivity and check space
rclone lsd onedrive:/      # List root directories
```

## Usage

### Manual Execution

**Rclone Mode (Remote Storage):**
```bash
# Run with rclone remote storage (respects schedules)
# Sends Uptime Kuma notifications
uv run python main.py

# Check configuration without running backups
uv run python -c "from src.config import load_config; print('Config valid!')"
```

**Local Filesystem Mode:**
```bash
# Run with local filesystem backup to specified path
# Does NOT send Uptime Kuma notifications
uv run python main.py /path/to/backup/destination

# Example: backup to external drive
uv run python main.py /mnt/external_drive/backups

# Example: backup to network share
uv run python main.py /mnt/nas/backup_storage
```


**Dry Run Mode:**
```bash
# Analyze backup size without copying (remote storage)  
# Does NOT send Uptime Kuma notifications
uv run python main.py --dry-run

# Analyze backup size for local filesystem backup
uv run python main.py --dry-run /path/to/backup/destination

# Short form using -n flag
uv run python main.py -n

# Example output:
# === DRY RUN SUMMARY ===
# Total backups: 3
# Successful: 3
# Failed: 0
# Total files: 1,247
# Total size: 2.4 GB
# Estimated time: 8m 32s
# 
# Backup Details:
#   ✅ daily_documents: 342 files, 156.7 MB
#   ✅ weekly_photos: 89 files, 1.2 GB
#   ✅ monthly_code: 816 files, 1.1 GB
```
### Local-Only Backups (rclone_enabled: false)

For sensitive data or compliance requirements, you can configure backups to run only in local filesystem mode and never upload to remote storage:

```yaml
# Example: Sensitive data backup
- name: sensitive_documents
  source_dir: /home/user/private
  rclone_path: onedrive:/backups/private  # Still required for path structure
  schedule: "* * * * *"  # Would run daily if rclone was enabled
  rclone_enabled: false  # Only runs in local mode, never in rclone mode
  retention: 10
```

**Behavior by mode:**
- **Rclone mode** (`python main.py`): Skipped entirely
- **Local mode** (`python main.py /path`): Always runs
- **Dry-run mode** (`--dry-run`): Included in analysis

**Use cases:**
- Sensitive data that should never leave local network
- Compliance requirements for data residency
- Large datasets to avoid bandwidth limits
- Development files for local NAS backup only



### Key Differences Between Modes

| Feature | Rclone Mode | Local Filesystem Mode | Dry Run Mode |
|---------|-------------|----------------------|--------------|
| **Trigger** | `python main.py` | `python main.py /path` | `python main.py --dry-run [path]` |
| **Destination** | Remote storage (cloud) | Local directory | Analysis only (no copying) |
| **Logging** | File only | Console + File | Console + File |
| **Space Check** | 200GB remote check | Skipped | Analysis only |
| **Directory Structure** | `remote:/backup_name_timestamp` | `path/backup_name_timestamp` | Shows planned structure |
| **Use Case** | Scheduled/cron jobs | Interactive/manual use | Planning and verification |
| **Output** | Backup summary | Backup summary | File analysis and size estimates |
| **Schedule Filtering** | Respects schedule and rclone_enabled | Ignores schedule and rclone_enabled | Includes all backups |

### Automated Execution (Cron)

**Rclone Mode (Recommended for automation):**

Create a cron job to run daily at 5:00 AM:

```bash
# Edit cron jobs
sudo crontab -e

# Add this line (uses rclone mode):
0 5 * * * cd /home/rsi/rclone-copy && uv run python main.py >> log/cron.log 2>&1
```

Or create a system cron file:
```bash
sudo tee /etc/cron.d/rclone-backup << 'EOF'
# rclone-copy backup job - runs daily at 5:00 AM (rclone mode)
0 5 * * * rsi cd /home/rsi/rclone-copy && uv run python main.py >> log/cron.log 2>&1
EOF
```

**Local Filesystem Mode in Cron:**

If you want to use local filesystem mode in cron (less common):
```bash
# Backup to local directory via cron
0 5 * * * cd /home/rsi/rclone-copy && uv run python main.py /mnt/backup_drive >> log/cron.log 2>&1
```

> **Note**: Local filesystem mode is primarily designed for interactive/manual use with console output. For automated backups, rclone mode is typically preferred.

### Email Configuration

Email notifications require SMTP configuration. Create `~/etc/grsrv03.env`:
```bash
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
FROM_EMAIL=backup-system@yourdomain.com
TO_EMAIL=admin@yourdomain.com
SMTP_TOKEN=your_app_password
```

## Monitoring and Logs

- **Application logs**: `log/rclone_copy.log`
- **Cron logs**: `log/cron.log`
- **Email summaries**: Sent after each run with metrics and status

### Log Levels
- `INFO`: Normal operation, backup summaries
- `WARNING`: Non-critical issues (cleanup failures, etc.)
- `ERROR`: Backup failures, configuration issues
- `CRITICAL`: System failures, pre-flight check failures

### Output Locations

**Rclone Mode (Cron/Automated):**
- Logs: `log/rclone_copy.log` (file only)
- Output: Redirected to log files

**Local Filesystem Mode (CLI/Interactive):**
- Logs: `log/rclone_copy.log` + console output
- Output: Real-time console feedback + file logging

## Troubleshooting

### Common Issues

**Configuration errors:**
```bash
# Validate configuration
uv run python -c "from src.config import load_config; load_config()"
```

**Rclone connectivity:**
```bash
# Test rclone access
rclone about your_remote:
rclone lsd your_remote:/
```

**Directory access:**
```bash
# Check source directory permissions
ls -la /path/to/source/directory
```

**Email notifications:**
```bash
# Test email configuration
uv run python -c "from python_utils.email_utils import EmailNotifier; print('Email config OK')"
```

**Uptime Kuma integration:**
```bash
# Test manual notification
curl "http://localhost:3001/api/push/MhyfEdOgdA?status=up&msg=TEST&ping="

# Check notification logs
grep -i "uptime kuma" log/rclone_copy.log

# Verify Uptime Kuma is running
curl http://localhost:3001/api/push/MhyfEdOgdA?ping=
```

**Local filesystem mode issues:**
```bash
# Test local backup manually
uv run python main.py /tmp/test_backup

# Check destination permissions
ls -la /path/to/backup/destination

# Monitor real-time output (local mode shows console output)
uv run python main.py /path/to/destination
```

### Exit Codes

- `0`: Success, all backups completed
- `1`: Configuration or system error
- `2`: Some backups failed (check logs)
- `130`: Interrupted by user

### Performance Tips

1. **Schedule optimization**: Spread backups across different days to avoid resource conflicts
2. **Size limits**: Use appropriate `max_size` limits to prevent huge transfers
3. **Age filtering**: Use `max_age` to backup only recent files when appropriate
4. **Retention**: Balance retention with storage costs
5. **Monitoring**: Use Uptime Kuma integration for proactive failure detection

## Development

### Setup Development Environment
```bash
uv pip install -e ".[dev]"
pre-commit install
```

### Running Tests
```bash
uv run pytest tests/ -v
```

### Code Formatting
```bash
uv run black . && uv run ruff check --fix .
```

## License

[Add your license information here]

## Contributing

[Add contribution guidelines here]
