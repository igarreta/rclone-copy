#!/usr/bin/env python3
"""
rclone-copy: Secondary backup copy using rclone with cron-based scheduling.

Main entry point for the backup application.
"""

import argparse
import logging
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from python_utils.email_utils import send_backup_notification
from python_utils.logging_utils import setup_backup_logging
from src.backup_manager import BackupManager, BackupResult
from src.config import AppConfig, load_config
from src.schedule_checker import ScheduleChecker


def send_uptime_kuma_notification(
    status: str, message: str, logger: logging.Logger | None = None
) -> None:
    """
    Send notification to Uptime Kuma monitoring service.

    Args:
        status: Either "up" for success or "down" for failure
        message: Simple message like "OK" or "FAILED"
        logger: Optional logger instance for error logging
    """
    base_url = "http://localhost:3001/api/push/MhyfEdOgdA"

    # Build query parameters
    params = {
        "status": status,
        "msg": message,
        "ping": "",  # Empty ping parameter as specified
    }

    # Construct full URL
    query_string = urllib.parse.urlencode(params)
    full_url = f"{base_url}?{query_string}"

    def _make_request(url: str) -> bool:
        """Make HTTP request, return True on success, False on failure."""
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                # Any successful HTTP response is considered success
                if response.getcode() < 400:
                    return True
                else:
                    if logger:
                        logger.warning(
                            f"Uptime Kuma notification failed with HTTP {response.getcode()}"
                        )
                    return False
        except Exception as e:
            if logger:
                logger.warning(f"Uptime Kuma notification failed: {e}")
            return False

    # First attempt
    if _make_request(full_url):
        # Success on first try
        if logger:
            logger.debug(
                f"Uptime Kuma notification sent successfully: status={status}, msg={message}"
            )
        return

    # First attempt failed, wait 2 minutes and retry
    if logger:
        logger.info("Uptime Kuma notification failed, retrying in 2 minutes...")

    time.sleep(120)  # 2 minutes

    # Second attempt
    if _make_request(full_url):
        if logger:
            logger.info(
                f"Uptime Kuma notification sent successfully on retry: status={status}, msg={message}"
            )
    else:
        if logger:
            logger.error("Uptime Kuma notification failed on retry, giving up")


def setup_logging(config: AppConfig, cli_mode: bool = False) -> logging.Logger:
    """Set up logging configuration."""
    log_file_path = Path(config.log_file)
    log_dir = log_file_path.parent
    log_dir.mkdir(parents=True, exist_ok=True)

    if cli_mode:
        # In CLI mode, log to both console and file
        logger = setup_backup_logging(
            log_dir=str(log_dir),
            log_level=config.log_level,
            app_name="rclone-copy",
            redirect_streams=False,  # Don't redirect streams in CLI mode to allow console output
        )

        # Add console handler for CLI mode
        console_handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s")
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    else:
        # Cron mode: file only (existing behavior)
        logger = setup_backup_logging(
            log_dir=str(log_dir),
            log_level=config.log_level,
            app_name="rclone-copy",
            redirect_streams=True,
        )

    return logger


def format_backup_summary(
    results: list[BackupResult], total_execution_time: float
) -> str:
    """Format backup results into a readable summary."""
    summary = []
    summary.append("=== Rclone Backup Summary ===\n")

    successful_count = sum(1 for r in results if r.success)
    failed_count = len(results) - successful_count
    total_bytes = sum(r.bytes_transferred for r in results if r.success)

    summary.append(f"Total backups processed: {len(results)}")
    summary.append(f"Successful: {successful_count}")
    summary.append(f"Failed: {failed_count}")
    summary.append(
        f"Total bytes transferred: {total_bytes:,} bytes ({total_bytes / (1024**3):.2f} GB)"
    )
    summary.append(f"Total execution time: {total_execution_time:.2f} seconds")
    summary.append("")

    # Individual backup details
    summary.append("=== Individual Backup Results ===")
    for result in results:
        status = "✓ SUCCESS" if result.success else "✗ FAILED"
        summary.append(f"\n[{status}] {result.backup_name}")
        summary.append(f"  Execution time: {result.execution_time:.2f} seconds")

        if result.success:
            summary.append(f"  Bytes transferred: {result.bytes_transferred:,}")
            if result.latest_file_date:
                summary.append(
                    f"  Latest file date: {result.latest_file_date.strftime('%Y-%m-%d %H:%M:%S')}"
                )
        else:
            summary.append(f"  Error: {result.error_message}")

    return "\n".join(summary)


def send_email_notification(config: AppConfig, summary: str, has_errors: bool) -> None:
    """Send email notification with backup summary."""
    if not config.email:
        return

    try:
        subject = "Rclone Backup Summary"
        if has_errors:
            subject += " - WITH ERRORS"

        # Use python_utils email notification
        send_backup_notification(
            backup_results=[],  # TODO: Pass actual backup results
            errors=[] if not has_errors else ["Backup errors occurred"],
            duration=0.0,  # TODO: Pass actual duration
            config_to_emails=config.email,
        )

        logging.info(f"Email notification sent to: {', '.join(config.email)}")

    except Exception as e:
        logging.error(f"Failed to send email notification: {e}")


def parse_arguments() -> tuple[str | None, bool]:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Backup files using rclone or local filesystem",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                           # Run with rclone (cron mode)
  python main.py /path/to/backup/dest      # Run with local filesystem backup
  python main.py --dry-run                 # Analyze backup size without copying
  python main.py --dry-run /path/dest      # Analyze local backup size
        """,
    )

    parser.add_argument(
        "destination",
        nargs="?",
        help="Local filesystem destination path (enables local backup mode)",
    )

    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Calculate backup size and list files without copying",
    )

    args = parser.parse_args()
    return args.destination, args.dry_run


def run_dry_run_mode(backup_manager, config, logger) -> int:
    """Execute dry run mode."""
    from src.backup_manager import estimate_transfer_time, format_duration, format_size

    logger.info("Running in DRY RUN mode - no files will be copied")

    # Get all backup items (skip schedule filtering for dry run)
    backup_list = config.backup_copy_list

    if not backup_list:
        logger.warning("No backup items configured")
        return 0

    # Run dry run analysis
    summary = backup_manager.run_all_backups_dry_run(backup_list)

    # Simple output for now
    if sys.stdout.isatty():
        # Interactive mode - console output
        print("\n=== DRY RUN SUMMARY ===")
        print(f"Total backups: {summary.total_backups}")
        print(f"Successful: {summary.successful_backups}")
        print(f"Failed: {summary.failed_backups}")
        print(f"Total files: {summary.total_files:,}")
        print(f"Total size: {format_size(summary.total_size)}")

        if summary.total_size > 0:
            dest_type = "local" if backup_manager.local_destination else "remote"
            est_time = estimate_transfer_time(summary.total_size, dest_type)
            print(f"Estimated time: {format_duration(est_time)}")

        print("\nBackup Details:")
        for result in summary.results:
            status = "✅" if result.success else "❌"
            if result.success:
                print(
                    f"  {status} {result.backup_name}: {result.total_files} files, {format_size(result.total_size)}"
                )
            else:
                print(f"  {status} {result.backup_name}: {result.error_message}")
    else:
        # Cron mode - log output
        logger.info("=== DRY RUN SUMMARY ===")
        logger.info(f"Total backups: {summary.total_backups}")
        logger.info(f"Successful analyses: {summary.successful_backups}")
        logger.info(f"Failed analyses: {summary.failed_backups}")
        logger.info(f"Total files: {summary.total_files:,}")
        logger.info(f"Total size: {format_size(summary.total_size)}")

        for result in summary.results:
            if result.success:
                logger.info(
                    f"✅ {result.backup_name}: {result.total_files} files, {format_size(result.total_size)}"
                )
            else:
                logger.error(f"❌ {result.backup_name}: {result.error_message}")

    return 0


def main() -> int:
    """Main application entry point."""
    start_time = datetime.now()

    try:
        # Parse command line arguments
        local_destination, dry_run = parse_arguments()
        cli_mode = local_destination is not None or dry_run

        # Load configuration
        config = load_config("config.yaml")

        # Setup logging
        logger = setup_logging(config, cli_mode=cli_mode)
        if local_destination:
            logger.info("Starting backup process in LOCAL FILESYSTEM mode")
            logger.info(f"Destination: {local_destination}")
        elif dry_run:
            logger.info("Starting backup process in DRY RUN mode")
        else:
            logger.info("Starting rclone-copy backup process")

        logger.info(
            f"Configuration loaded with {len(config.backup_copy_list)} backup items"
        )

        # Filter backups that should run today (skip schedule filtering in local mode)
        if cli_mode:
            # Local mode: process all backup items (ignore schedule)
            scheduled_backups = config.backup_copy_list
            logger.info(
                "Local mode: processing all backup items (schedule and rclone_enabled ignored)"
            )
        else:
            # Rclone mode: filter by schedule
            scheduled_backups = ScheduleChecker.get_scheduled_backups(
                config.backup_copy_list
            )

            # Log information about rclone-disabled backups
            disabled_backups = [
                item for item in config.backup_copy_list if not item.rclone_enabled
            ]
            if disabled_backups:
                disabled_names = [item.name for item in disabled_backups]
                logger.info(
                    f"Skipping {len(disabled_backups)} rclone-disabled backups: {disabled_names}"
                )

            if not scheduled_backups:
                logger.info("No backups scheduled to run today")
                # Still send a notification if configured
                if config.email:
                    summary = "=== Rclone Backup Summary ===\n\nNo backups were scheduled to run today."
                    send_email_notification(config, summary, has_errors=False)
                # Send Uptime Kuma notification (only in rclone mode, not dry-run)
                if local_destination is None and not dry_run:
                    send_uptime_kuma_notification("up", "OK", logger)

                return 0

            logger.info(
                f"Found {len(scheduled_backups)} backups scheduled to run today"
            )

        # Initialize backup manager
        backup_manager = BackupManager(
            config, local_destination=local_destination, dry_run=dry_run
        )

        # Handle dry run mode
        if dry_run:
            return run_dry_run_mode(backup_manager, config, logger)

        # Perform pre-flight checks
        logger.info("Performing pre-flight checks...")
        preflight_errors = backup_manager.perform_preflight_checks(scheduled_backups)

        if preflight_errors:
            logger.critical("Pre-flight checks failed:")
            for error in preflight_errors:
                logger.critical(f"  - {error}")

            # Send error notification
            error_summary = "=== Rclone Backup - Pre-flight Check Failures ===\n\n"
            error_summary += "The following errors prevented backups from starting:\n\n"
            error_summary += "\n".join(f"• {error}" for error in preflight_errors)

            if config.email:
                send_email_notification(config, error_summary, has_errors=True)

            # Send Uptime Kuma notification (only in rclone mode, not dry-run)
            if local_destination is None and not dry_run:
                send_uptime_kuma_notification("down", "FAILED", logger)

            return 1

        logger.info("Pre-flight checks passed")

        # Execute backups
        results = []
        for backup_item in scheduled_backups:
            logger.info(f"Processing backup: {backup_item.name}")
            result = backup_manager.create_backup(backup_item)
            results.append(result)

        # Calculate total execution time
        total_execution_time = (datetime.now() - start_time).total_seconds()

        # Generate summary
        summary = format_backup_summary(results, total_execution_time)
        logger.info("\n" + summary)

        # Check if there were any errors
        has_errors = any(not result.success for result in results)

        # Send email notification
        if config.email:
            send_email_notification(config, summary, has_errors)

        # Return appropriate exit code
        if has_errors:
            logger.warning("Some backups failed - check logs for details")
            # Send Uptime Kuma notification (only in rclone mode, not dry-run)
            if local_destination is None and not dry_run:
                send_uptime_kuma_notification("down", "FAILED", logger)

            return 2
        else:
            logger.info("All backups completed successfully")
            # Send Uptime Kuma notification (only in rclone mode, not dry-run)
            if local_destination is None and not dry_run:
                send_uptime_kuma_notification("up", "OK", logger)

            return 0

    except FileNotFoundError as e:
        error_msg = f"Configuration file error: {e}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        if "logger" in locals():
            logger.critical(error_msg)
        # Send Uptime Kuma notification (only in rclone mode, not dry-run)
        if (
            "local_destination" in locals()
            and local_destination is None
            and "dry_run" in locals()
            and not dry_run
        ):
            send_uptime_kuma_notification("down", "FAILED", logger)

        return 1

    except ValueError as e:
        error_msg = f"Configuration validation error: {e}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        if "logger" in locals():
            logger.critical(error_msg)
        # Send Uptime Kuma notification (only in rclone mode, not dry-run)
        if (
            "local_destination" in locals()
            and local_destination is None
            and "dry_run" in locals()
            and not dry_run
        ):
            send_uptime_kuma_notification("down", "FAILED", logger)

        return 1

    except KeyboardInterrupt:
        error_msg = "Backup process interrupted by user"
        print(f"\nINTERRUPTED: {error_msg}", file=sys.stderr)
        if "logger" in locals():
            logger.warning(error_msg)
        # Send Uptime Kuma notification (only in rclone mode, not dry-run)
        if (
            "local_destination" in locals()
            and local_destination is None
            and "dry_run" in locals()
            and not dry_run
        ):
            send_uptime_kuma_notification("down", "FAILED", logger)

        return 130

    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        if "logger" in locals():
            logger.critical(error_msg, exc_info=True)
        # Send Uptime Kuma notification (only in rclone mode, not dry-run)
        if (
            "local_destination" in locals()
            and local_destination is None
            and "dry_run" in locals()
            and not dry_run
        ):
            send_uptime_kuma_notification("down", "FAILED", logger)

        return 1

    finally:
        if "logger" in locals():
            total_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Backup process completed in {total_time:.2f} seconds")


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)


def print_dry_run_summary(summary, detailed: bool = False) -> None:
    """Print formatted dry run summary to console."""
    from src.backup_manager import estimate_transfer_time, format_duration, format_size

    print("╭─── Backup Dry Run Summary " + "─" * 40 + "╮")
    print("│" + " " * 64 + "│")
    print("│ 📊 OVERVIEW" + " " * 51 + "│")
    print(
        f"│   • Total backups: {summary.total_backups}"
        + " " * (49 - len(str(summary.total_backups)))
        + "│"
    )
    print(
        f"│   • Total files: {summary.total_files:,}"
        + " " * (51 - len(f"{summary.total_files:,}"))
        + "│"
    )
    print(
        f"│   • Total size: {format_size(summary.total_size)}"
        + " " * (52 - len(format_size(summary.total_size)))
        + "│"
    )

    # Estimate transfer time
    if summary.total_size > 0:
        dest_type = (
            "local"
            if any(
                "/mnt" in r.destination or "/home" in r.destination
                for r in summary.results
                if r.success
            )
            else "remote"
        )
        est_time = estimate_transfer_time(summary.total_size, dest_type)
        print(
            f"│   • Estimated time: {format_duration(est_time)}"
            + " " * (48 - len(format_duration(est_time)))
            + "│"
        )

    print("│" + " " * 64 + "│")
    print("│ 📁 BACKUP DETAILS" + " " * 47 + "│")

    for result in summary.results:
        status = "✅" if result.success else "❌"
        print(
            f"│   {result.backup_name} ({status})"
            + " " * (59 - len(result.backup_name))
            + "│"
        )
        if result.success:
            size_info = f"{result.total_files} files, {format_size(result.total_size)}"
            dest_short = (
                result.destination.split("/")[-1]
                if "/" in result.destination
                else result.destination
            )
            print(
                f"│     └─ {size_info} → {dest_short}"
                + " " * (59 - len(f"{size_info} → {dest_short}"))
                + "│"
            )
        else:
            print(f"│     └─ Error: {result.error_message[:40]}..." + " " * (15) + "│")

    print("│" + " " * 64 + "│")
    print("╰" + "─" * 64 + "╯")

    if detailed and summary.total_backups > 0:
        print("\n📋 DETAILED FILE ANALYSIS")
        for result in summary.results:
            if result.success:
                print_detailed_file_list(result)


def print_detailed_file_list(result) -> None:
    """Print detailed file listing for a backup."""
    from src.backup_manager import format_size

    print(f"\n📁 {result.backup_name} → {result.destination}")
    print(
        f"Files to copy ({result.total_files} total, {format_size(result.total_size)}):"
    )

    if result.filtered_files:
        print("┌" + "─" * 50 + "┬" + "─" * 10 + "┐")
        print("│" + "File Path".ljust(50) + "│" + "Size".ljust(10) + "│")
        print("├" + "─" * 50 + "┼" + "─" * 10 + "┤")

        # Show first 10 files
        for i, file_path in enumerate(result.filtered_files[:10]):
            if file_path.exists():
                size = format_size(file_path.stat().st_size)
                path_str = str(file_path)
                if len(path_str) > 48:
                    path_str = "..." + path_str[-45:]
                print("│" + path_str.ljust(50) + "│" + size.ljust(10) + "│")

        if len(result.filtered_files) > 10:
            remaining = len(result.filtered_files) - 10
            print(
                "│" + f"... and {remaining} more files".ljust(50) + "│" + " " * 10 + "│"
            )

        print("└" + "─" * 50 + "┴" + "─" * 10 + "┘")

    if result.excluded_files:
        print(f"\nExcluded files ({len(result.excluded_files)} total):")
        for file_path in result.excluded_files[:5]:  # Show first 5 excluded files
            print(f"• {file_path}")
        if len(result.excluded_files) > 5:
            print(f"• ... and {len(result.excluded_files) - 5} more excluded files")


def log_dry_run_summary(summary, logger) -> None:
    """Log dry run results in structured format for cron jobs."""
    from src.backup_manager import estimate_transfer_time, format_duration, format_size

    logger.info("=== DRY RUN SUMMARY ===")
    logger.info(f"Total backups: {summary.total_backups}")
    logger.info(f"Successful analyses: {summary.successful_backups}")
    logger.info(f"Failed analyses: {summary.failed_backups}")
    logger.info(f"Total files: {summary.total_files:,}")
    logger.info(f"Total size: {format_size(summary.total_size)}")

    if summary.total_size > 0:
        dest_type = (
            "local"
            if any(
                "/mnt" in r.destination or "/home" in r.destination
                for r in summary.results
                if r.success
            )
            else "remote"
        )
        est_time = estimate_transfer_time(summary.total_size, dest_type)
        logger.info(f"Estimated duration: {format_duration(est_time)}")

    logger.info("=== INDIVIDUAL BACKUP ANALYSIS ===")
    for result in summary.results:
        if result.success:
            logger.info(
                f"✅ {result.backup_name}: {result.total_files} files, "
                f"{format_size(result.total_size)} → {result.destination}"
            )
        else:
            logger.error(f"❌ {result.backup_name}: {result.error_message}")
