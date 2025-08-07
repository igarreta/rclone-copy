# Secondary backup copy
This project will make copies of some directories to a remote storage to a secondary backup.
It will be written in Python 3.13 and will be run as a daily cron job .
As this project will not have external inputs, it will not run in a docker container.
Provide instructions to authorize rclone. The server does not have a web browser.

## General instructions
Use general and project CLAUDE.md files for general instructions. 

## Backup location
Backup origins may be mounted as read only. They may be external USB disk that could disconnect, and mounted on this server by a samba share.
Backup destination will be accessed with rclone, which shoud be previously configured. Rclone configuration must be confirmed to be correct.

## Check process 
These checks will be performed:
1. Check if the directories listed in copy_dir_list are mounted and accessible. If not, send an alert.
2. Check if the backup disk has at least 200 GB of free space. If not, send an alert and stop.
3. For each directory in the list, copy all the files to the rclone_path that are less than the specified number of days old. If days == 0 or not defined, copy all files. Include files in subdirectories. First check that the total size of the files to copy is less than the specified maximum size. If not, send an alert and stop.
4.

## Backup copy process (backup_copy_list)
1. Check if rclone is installed and configured.
2. For each directory in backup_copy_list, copy all files from teh source_dirless than the specified number of days old to the specified rclone directory using rclone. If days == 0 or not defined, copy all files. Include files in subdirectories. First check that the total size of the files to copy is less than the specified maximum size. 
3.  Keep the number of backups indicated in retention. Keep the latest backup and the previous backup if retention is not specified.
4. Make directories for each backup with the name of the backup and the timestamp of the backup (format YYYY-MM-DD). This is intended to be run daily. A second backup on the same day will be copied to the same directory.


## cron job
The cron job will be run daily at 5:00 AM by the server main cron.
Give a cron example for the job.


## Configuration
The configuration file (`config.yaml`) will be a YAML file with the following structure:
```yaml
email: # list of emails to send notifications to 
  - user@example.com
log_level: INFO # logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
log_file: log/rclone_copy.log # path to log file relative to project root

backup_copy_list: # list of directories to copy to remote storage
  - name: contabo1 # short name/identifier for the backup (required)
    source_dir: /mnt/backup_usb1/contabo1 # path to the source directory (required)
    rclone_path: onedrive:/GR_SRV03/backup/contabo1 # path to the rclone directory (required)
    max_size_mb: 200 # maximum size in MB for the backup (optional, default = 1 GB)
    days: 1 # maximum age in days of the files to be copied (optional, default = 1 day)
    retention: 2 # backups to keep (optional, default = 2)

```

### Configuration file location
The configuration file will be located at `var/config.yaml` relative to project root.

### Configuration integrity
The configuration file will be validated against a schema. If the configuration is not valid, the program will exit with an critical error.
    source_dir: /mnt/hassio # path to the source directory (required)
    rclone_path: onedrive:/GR_SRV03/backup/homeassistant # path to the rclone directory (required)
    max_size_mb: 200 # maximum size in MB for the backup (optional)
    days: 1 # maximum age in days of the files to be copied (optional)
    retention_days: 7 # number of days to keep the backup (optional)
    retention_weeks: 4 # number of weeks to keep the backup (optional)
    retention_months: 12 # number of months to keep the backup (optional)

```


## Notification
Send email when process is completed with a summary of the results.
Include total size for each backup and copy name and latest file date.

## Error handling
If an directory is not mounted, include it in the summary and continue.
If any of the backup_copy_list is not possible to copy, include it in the summary and continue.
If errors are detected, alerts will be sent through multiple channels :
1. Email (using SendGrid): all alerts
2. Pushover notifications (low priority): only critical alerts

## Metrics
Do not save metrics.

## Alert Process
Each alert will include:
- Timestamp
- Alert level (INFO, WARNING, ERROR, CRITICAL)
- Affected backup  name
- Detailed error message
- Relevant metrics (backup size, age, etc.)

## Logging
Logging follows predefined logging instructions (CLAUDE.md)

## Documentation
Provide a README.md file with instructions on how to install and run the project. 
Include example configuration file.





