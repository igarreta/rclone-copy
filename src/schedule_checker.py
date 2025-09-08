"""Schedule checking logic for cron-based backup scheduling."""

from datetime import datetime

from croniter import croniter

from .config import BackupItem


class ScheduleChecker:
    """Handles evaluation of cron-based backup schedules."""

    @staticmethod
    def should_run_backup(
        backup_item: BackupItem, current_time: datetime = None
    ) -> bool:
        """
        Check if a backup should run based on its cron schedule.

        Args:
            backup_item: The backup configuration item
            current_time: Current time (defaults to now)

        Returns:
            True if backup should run today, False otherwise
        """
        if current_time is None:
            current_time = datetime.now()

        schedule = backup_item.schedule.strip()

        # Parse the cron expression
        try:
            # Create croniter instance
            cron = croniter(schedule, current_time)

            # Get the previous occurrence (when this schedule last matched)
            prev_occurrence = cron.get_prev(datetime)

            # Check if the previous occurrence was today
            # Since we run daily at 5 AM, we check if the cron would have
            # triggered between midnight and now today
            today_start = current_time.replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            return prev_occurrence >= today_start

        except Exception as e:
            raise ValueError(
                f"Error evaluating schedule '{schedule}' for backup '{backup_item.name}': {e}"
            )

    @staticmethod
    def get_scheduled_backups(
        backup_list: list[BackupItem], current_time: datetime = None
    ) -> list[BackupItem]:
        """
        Filter backup list to only include rclone-enabled items scheduled to run.

        Args:
            backup_list: List of all backup items
            current_time: Current time (defaults to now)

        Returns:
            List of backup items that should run today
        """
        scheduled_backups = []

        for backup_item in backup_list:
            # Skip backups that are disabled for rclone mode
            if not backup_item.rclone_enabled:
                continue
            try:
                if ScheduleChecker.should_run_backup(backup_item, current_time):
                    scheduled_backups.append(backup_item)
            except Exception as e:
                # Log the error but don't stop processing other backups
                print(
                    f"Warning: Could not evaluate schedule for backup '{backup_item.name}': {e}"
                )
                continue

        return scheduled_backups

    @staticmethod
    def next_run_time(
        backup_item: BackupItem, current_time: datetime = None
    ) -> datetime:
        """
        Get the next time this backup is scheduled to run.

        Args:
            backup_item: The backup configuration item
            current_time: Current time (defaults to now)

        Returns:
            Next scheduled run time
        """
        if current_time is None:
            current_time = datetime.now()

        schedule = backup_item.schedule.strip()

        try:
            cron = croniter(schedule, current_time)
            return cron.get_next(datetime)
        except Exception as e:
            raise ValueError(
                f"Error calculating next run time for backup '{backup_item.name}': {e}"
            )

    @staticmethod
    def validate_schedule_format(schedule: str) -> bool:
        """
        Validate that a schedule string is a valid cron expression.

        Args:
            schedule: Cron schedule string

        Returns:
            True if valid, False otherwise
        """
        try:
            croniter(schedule.strip())
            return True
        except Exception:
            return False
