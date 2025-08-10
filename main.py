#!/usr/bin/env python3
"""
rclone-copy: Secondary backup copy using rclone with cron-based scheduling.

Main entry point for the backup application.
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from python_utils.email_utils import EmailNotifier, send_backup_notification
from python_utils.logging_utils import setup_backup_logging

from src.backup_manager import BackupManager, BackupResult
from src.config import AppConfig, load_config
from src.schedule_checker import ScheduleChecker


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
        formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
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


def format_backup_summary(results: List[BackupResult], total_execution_time: float) -> str:
    """Format backup results into a readable summary."""
    summary = []
    summary.append("=== Rclone Backup Summary ===\n")

    successful_count = sum(1 for r in results if r.success)
    failed_count = len(results) - successful_count
    total_bytes = sum(r.bytes_transferred for r in results if r.success)

    summary.append(f"Total backups processed: {len(results)}")
    summary.append(f"Successful: {successful_count}")
    summary.append(f"Failed: {failed_count}")
    summary.append(f"Total bytes transferred: {total_bytes:,} bytes ({total_bytes / (1024**3):.2f} GB)")
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
                summary.append(f"  Latest file date: {result.latest_file_date.strftime('%Y-%m-%d %H:%M:%S')}")
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
            to_emails=config.email,
            subject=subject,
            backup_summary=summary,
            has_errors=has_errors,
        )

        logging.info(f"Email notification sent to: {', '.join(config.email)}")

    except Exception as e:
        logging.error(f"Failed to send email notification: {e}")


def parse_arguments() -> Optional[str]:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Backup files using rclone or local filesystem",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                           # Run with rclone (cron mode)
  python main.py /path/to/backup/dest      # Run with local filesystem backup
        """,
    )
    
    parser.add_argument(
        "destination",
        nargs="?",
        help="Local filesystem destination path (enables local backup mode)",
    )
    
    args = parser.parse_args()
    return args.destination


def main() -> int:
    """Main application entry point."""
    start_time = datetime.now()

    try:
        # Parse command line arguments
        local_destination = parse_arguments()
        cli_mode = local_destination is not None
        
        # Load configuration
        config = load_config("config.yaml")

        # Setup logging
        logger = setup_logging(config, cli_mode=cli_mode)
        if cli_mode:
            logger.info(f"Starting backup process in LOCAL FILESYSTEM mode")
            logger.info(f"Destination: {local_destination}")
        else:
            logger.info("Starting rclone-copy backup process")
            
        logger.info(f"Configuration loaded with {len(config.backup_copy_list)} backup items")

        # Filter backups that should run today (skip schedule filtering in local mode)
        if cli_mode:
            # Local mode: process all backup items (ignore schedule)
            scheduled_backups = config.backup_copy_list
            logger.info(f"Local mode: processing all {len(scheduled_backups)} backup items (schedule ignored)")
        else:
            # Rclone mode: filter by schedule
            scheduled_backups = ScheduleChecker.get_scheduled_backups(config.backup_copy_list)
            
            if not scheduled_backups:
                logger.info("No backups scheduled to run today")
                # Still send a notification if configured
                if config.email:
                    summary = "=== Rclone Backup Summary ===\n\nNo backups were scheduled to run today."
                    send_email_notification(config, summary, has_errors=False)
                return 0

            logger.info(f"Found {len(scheduled_backups)} backups scheduled to run today")

        # Initialize backup manager
        backup_manager = BackupManager(config, local_destination=local_destination)

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
            return 2
        else:
            logger.info("All backups completed successfully")
            return 0

    except FileNotFoundError as e:
        error_msg = f"Configuration file error: {e}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        if 'logger' in locals():
            logger.critical(error_msg)
        return 1

    except ValueError as e:
        error_msg = f"Configuration validation error: {e}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        if 'logger' in locals():
            logger.critical(error_msg)
        return 1

    except KeyboardInterrupt:
        error_msg = "Backup process interrupted by user"
        print(f"\nINTERRUPTED: {error_msg}", file=sys.stderr)
        if 'logger' in locals():
            logger.warning(error_msg)
        return 130

    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        if 'logger' in locals():
            logger.critical(error_msg, exc_info=True)
        return 1

    finally:
        if 'logger' in locals():
            total_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Backup process completed in {total_time:.2f} seconds")


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)