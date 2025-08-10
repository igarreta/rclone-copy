# rclone-copy

Secondary backup copy system using rclone with cron-based scheduling. This Python application automatically backs up directories to remote storage with configurable scheduling, retention policies, and comprehensive monitoring.

## Features

- **Cron-based scheduling**: Flexible scheduling using cron syntax for daily, weekly, monthly, or custom intervals
- **Multiple backup sources**: Configure multiple directories with individual settings
- **Remote storage support**: Works with any rclone-supported remote (OneDrive, Google Drive, S3, etc.)
- **Size and age filtering**: Control backup size and file age limits
- **Retention management**: Automatic cleanup of old backups
- **Pre-flight checks**: Validates sources, destinations, and available space before starting
- **Email notifications**: Comprehensive backup summaries with metrics
- **Robust error handling**: Continues processing other backups if one fails

## Requirements

- Python 3.13+
- rclone (must be configured with remote storage)
- uv (for dependency management)

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
```bash
# Run immediately (respects schedules)
uv run python main.py

# Check configuration without running backups
uv run python -c "from src.config import load_config; print('Config valid!')"
```

### Automated Execution (Cron)

Create a cron job to run daily at 5:00 AM:

```bash
# Edit cron jobs
sudo crontab -e

# Add this line:
0 5 * * * cd /home/rsi/rclone-copy && uv run python main.py >> log/cron.log 2>&1
```

Or create a system cron file:
```bash
sudo tee /etc/cron.d/rclone-backup << 'EOF'
# rclone-copy backup job - runs daily at 5:00 AM
0 5 * * * rsi cd /home/rsi/rclone-copy && uv run python main.py >> log/cron.log 2>&1
EOF
```

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
