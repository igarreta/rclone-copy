"""Core backup management functionality using rclone."""

import json
import logging
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from python_utils.filesystem_utils import (
    calculate_total_size,
    get_files_modified_within_days,
    is_directory_accessible,
)

from .config import AppConfig, BackupItem


class BackupResult:
    """Result of a backup operation."""

    def __init__(
        self,
        backup_name: str,
        success: bool,
        bytes_transferred: int = 0,
        error_message: str = "",
        execution_time: float = 0.0,
        latest_file_date: Optional[datetime] = None,
    ):
        self.backup_name = backup_name
        self.success = success
        self.bytes_transferred = bytes_transferred
        self.error_message = error_message
        self.execution_time = execution_time
        self.latest_file_date = latest_file_date



class DryRunResult:
    """Result of a dry run operation."""

    def __init__(
        self,
        backup_name: str,
        source_dir: str,
        destination: str,
        total_files: int = 0,
        total_size: int = 0,
        filtered_files: Optional[List[Path]] = None,
        excluded_files: Optional[List[Path]] = None,
        error_message: str = "",
        success: bool = True,
    ):
        self.backup_name = backup_name
        self.source_dir = source_dir
        self.destination = destination
        self.total_files = total_files
        self.total_size = total_size
        self.filtered_files = filtered_files or []
        self.excluded_files = excluded_files or []
        self.error_message = error_message
        self.success = success


class DryRunSummary:
    """Summary of all dry run operations."""

    def __init__(
        self,
        results: Optional[List[DryRunResult]] = None,
    ):
        self.results = results or []

    @property
    def total_backups(self) -> int:
        """Total number of backup operations."""
        return len(self.results)

    @property
    def successful_backups(self) -> int:
        """Number of successful backup analyses."""
        return sum(1 for r in self.results if r.success)

    @property
    def failed_backups(self) -> int:
        """Number of failed backup analyses."""
        return sum(1 for r in self.results if not r.success)

    @property
    def total_files(self) -> int:
        """Total number of files across all backups."""
        return sum(r.total_files for r in self.results if r.success)

    @property
    def total_size(self) -> int:
        """Total size in bytes across all backups."""
        return sum(r.total_size for r in self.results if r.success)

    def add_result(self, result: DryRunResult) -> None:
        """Add a dry run result to the summary."""
        self.results.append(result)


def analyze_backup_files(
    source_dir: str, 
    max_age_days: int = 0,
    max_size_bytes: int = 0
) -> Tuple[List[Path], List[Path], int]:
    """
    Analyze files that would be included in backup.
    
    Args:
        source_dir: Source directory path
        max_age_days: Maximum age of files in days (0 = no limit)
        max_size_bytes: Maximum total backup size (0 = no limit)
    
    Returns:
        - files_to_copy: List of files that pass filters
        - excluded_files: List of files excluded by filters
        - total_size: Total size of files to copy
    """
    source_path = Path(source_dir)
    if not source_path.exists() or not source_path.is_dir():
        return [], [], 0
        
    files_to_copy = []
    excluded_files = []
    total_size = 0
    current_backup_size = 0
    
    # Get cutoff date for max_age filter
    cutoff_date = None
    if max_age_days > 0:
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
    
    try:
        # Walk through all files in source directory
        for file_path in source_path.rglob('*'):
            if file_path.is_file():
                try:
                    file_stat = file_path.stat()
                    file_size = file_stat.st_size
                    file_mtime = datetime.fromtimestamp(file_stat.st_mtime)
                    
                    # Check age filter
                    if cutoff_date and file_mtime < cutoff_date:
                        excluded_files.append(file_path)
                        continue
                    
                    # Check size limit
                    if max_size_bytes > 0 and (current_backup_size + file_size) > max_size_bytes:
                        excluded_files.append(file_path)
                        continue
                    
                    # File passes all filters
                    files_to_copy.append(file_path)
                    total_size += file_size
                    current_backup_size += file_size
                    
                except (OSError, PermissionError):
                    # Skip files we can't access
                    excluded_files.append(file_path)
                    continue
                    
    except (OSError, PermissionError) as e:
        # Handle directory access errors
        logging.getLogger(__name__).warning(f"Cannot access directory {source_dir}: {e}")
        return [], [], 0
    
    return files_to_copy, excluded_files, total_size


def estimate_transfer_time(total_size: int, destination_type: str = "remote") -> float:
    """
    Estimate transfer time based on size and destination type.
    
    Args:
        total_size: Total size in bytes
        destination_type: "remote" or "local"
        
    Returns:
        Estimated time in seconds
    """
    if total_size == 0:
        return 0.0
    
    # Transfer rate estimates (bytes per second)
    if destination_type == "local":
        # Local disk transfer (SSD/HDD average)
        rate_bps = 50 * 1024 * 1024  # 50 MB/s
    else:
        # Remote transfer (internet upload)
        rate_bps = 5 * 1024 * 1024   # 5 MB/s (conservative estimate)
    
    return total_size / rate_bps


def format_size(size_bytes: int) -> str:
    """Format byte size in human-readable format."""
    if size_bytes == 0:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            if unit == 'B':
                return f"{size_bytes} {unit}"
            else:
                return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    
    return f"{size_bytes:.1f} PB"


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.0f}m {seconds % 60:.0f}s"
    else:
        hours = seconds / 3600
        minutes = (seconds % 3600) / 60
        return f"{hours:.0f}h {minutes:.0f}m"

class RcloneManager:
    """Handles rclone operations and validations."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def validate_rclone_installation(self) -> bool:
        """Check if rclone is installed and accessible."""
        try:
            result = subprocess.run(
                ["rclone", "version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            return False

    def get_remote_info(self, remote_name: str) -> Optional[Dict]:
        """Get information about a remote using 'rclone about'."""
        try:
            result = subprocess.run(
                ["rclone", "about", f"{remote_name}:", "--json"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                self.logger.error(
                    f"rclone about failed for remote '{remote_name}': {result.stderr}"
                )
                return None

        except (subprocess.TimeoutExpired, json.JSONDecodeError, subprocess.SubprocessError) as e:
            self.logger.error(f"Error getting remote info for '{remote_name}': {e}")
            return None

    def check_remote_space(self, remote_name: str) -> bool:
        """Check if remote has sufficient free space."""
        remote_info = self.get_remote_info(remote_name)
        if not remote_info:
            return False

        free_space = remote_info.get("free", 0)
        required_space = self.config.min_free_space_bytes

        if free_space < required_space:
            self.logger.warning(
                f"Remote '{remote_name}' has insufficient space: "
                f"{free_space} bytes available, {required_space} bytes required"
            )
            return False

        return True

    def copy_to_remote(
        self, source_dir: str, destination: str, max_age_days: int = 0
    ) -> Tuple[bool, int, str]:
        """
        Copy files from source to remote destination using rclone.

        Returns:
            Tuple of (success, bytes_transferred, error_message)
        """
        try:
            # Build rclone command
            cmd = [
                "rclone",
                "copy",
                source_dir,
                destination,
                "--progress",
                "--stats-one-line",
                "--stats=1s",
                "--create-empty-src-dirs",
            ]

            # Add age filter if specified
            if max_age_days > 0:
                cmd.extend(["--max-age", f"{max_age_days}d"])

            self.logger.info(f"Running rclone command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout
            )

            if result.returncode == 0:
                # Parse output to get bytes transferred
                bytes_transferred = self._parse_rclone_output(result.stderr)
                return True, bytes_transferred, ""
            else:
                error_msg = f"rclone copy failed: {result.stderr}"
                self.logger.error(error_msg)
                return False, 0, error_msg

        except subprocess.TimeoutExpired:
            error_msg = "rclone copy operation timed out"
            self.logger.error(error_msg)
            return False, 0, error_msg
        except subprocess.SubprocessError as e:
            error_msg = f"rclone copy subprocess error: {e}"
            self.logger.error(error_msg)
            return False, 0, error_msg

    def _parse_rclone_output(self, output: str) -> int:
        """Parse rclone output to extract bytes transferred."""
        # Look for lines like "Transferred: 1.234 MiB / 1.234 MiB, 100%, 0 B/s, ETA -"
        bytes_transferred = 0
        for line in output.split("\n"):
            if "Transferred:" in line:
                try:
                    # Extract the transferred amount
                    parts = line.split("Transferred:")[1].split("/")[0].strip()
                    # This is a simplified parser - in practice, you might want more robust parsing
                    if "MiB" in parts:
                        amount = float(parts.replace("MiB", "").strip())
                        bytes_transferred = int(amount * 1024 * 1024)
                    elif "GiB" in parts:
                        amount = float(parts.replace("GiB", "").strip())
                        bytes_transferred = int(amount * 1024 * 1024 * 1024)
                    elif "KiB" in parts:
                        amount = float(parts.replace("KiB", "").strip())
                        bytes_transferred = int(amount * 1024)
                    elif "B" in parts:
                        bytes_transferred = int(parts.replace("B", "").strip())
                except (ValueError, IndexError):
                    continue
        return bytes_transferred

    def list_remote_directories(self, remote_path: str) -> List[str]:
        """List directories in a remote path."""
        try:
            result = subprocess.run(
                ["rclone", "lsd", remote_path],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                directories = []
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        # Parse directory name from rclone lsd output
                        parts = line.split()
                        if parts:
                            directories.append(parts[-1])
                return directories
            else:
                self.logger.error(
                    f"rclone lsd failed for '{remote_path}': {result.stderr}"
                )
                return []

        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            self.logger.error(f"Error listing remote directories '{remote_path}': {e}")
            return []

    def delete_remote_directory(self, remote_path: str) -> bool:
        """Delete a remote directory."""
        try:
            result = subprocess.run(
                ["rclone", "purge", remote_path],
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode == 0:
                self.logger.info(f"Successfully deleted remote directory: {remote_path}")
                return True
            else:
                self.logger.error(
                    f"Failed to delete remote directory '{remote_path}': {result.stderr}"
                )
                return False

        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            self.logger.error(f"Error deleting remote directory '{remote_path}': {e}")
            return False


class LocalBackupManager:
    """Handles local filesystem backup operations."""

    def __init__(self, config: AppConfig, destination_path: str):
        self.config = config
        self.destination_path = Path(destination_path)
        self.logger = logging.getLogger(__name__)

    def validate_destination(self) -> bool:
        """Check if destination directory is writable."""
        try:
            # Ensure destination exists
            self.destination_path.mkdir(parents=True, exist_ok=True)
            
            # Test write permissions
            test_file = self.destination_path / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            
            return True
        except (OSError, PermissionError) as e:
            self.logger.error(f"Destination path not writable: {e}")
            return False

    def copy_to_local(
        self, source_dir: str, destination: str, max_age_days: int = 0
    ) -> Tuple[bool, int, str]:
        """
        Copy files from source to local destination.

        Returns:
            Tuple of (success, bytes_transferred, error_message)
        """
        try:
            source_path = Path(source_dir)
            dest_path = Path(destination)
            
            if not source_path.exists():
                return False, 0, f"Source directory does not exist: {source_dir}"

            # Get files to backup based on age criteria
            if max_age_days > 0:
                files_to_backup = [file_path for file_path, _, _ in get_files_modified_within_days(source_dir, max_age_days)]
            else:
                # Get all files recursively
                files_to_backup = [
                    str(p) for p in source_path.rglob("*") if p.is_file()
                ]

            if not files_to_backup:
                self.logger.warning(f"No files found to backup from {source_dir}")
                return True, 0, ""

            # Calculate total bytes to transfer
            total_bytes = calculate_total_size(files_to_backup)
            
            # Create destination directory
            dest_path.mkdir(parents=True, exist_ok=True)
            
            # Copy files while preserving structure
            bytes_transferred = 0
            for file_path in files_to_backup:
                src_file = Path(file_path)
                
                # Calculate relative path from source
                rel_path = src_file.relative_to(source_path)
                dest_file = dest_path / rel_path
                
                # Create parent directories
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy file
                shutil.copy2(src_file, dest_file)
                bytes_transferred += src_file.stat().st_size
                
            self.logger.info(f"Copied {len(files_to_backup)} files ({bytes_transferred} bytes)")
            return True, bytes_transferred, ""

        except Exception as e:
            error_msg = f"Local copy failed: {e}"
            self.logger.error(error_msg)
            return False, 0, error_msg

    def list_local_directories(self, path: str) -> List[str]:
        """List directories in a local path."""
        try:
            local_path = Path(path)
            if not local_path.exists():
                return []
            
            return [d.name for d in local_path.iterdir() if d.is_dir()]
        except Exception as e:
            self.logger.error(f"Error listing local directories '{path}': {e}")
            return []

    def delete_local_directory(self, path: str) -> bool:
        """Delete a local directory."""
        try:
            local_path = Path(path)
            if local_path.exists():
                shutil.rmtree(local_path)
                self.logger.info(f"Successfully deleted local directory: {path}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error deleting local directory '{path}': {e}")
            return False


class BackupManager:
    """Main backup management class."""

    def __init__(self, config: AppConfig, local_destination: Optional[str] = None, dry_run: bool = False):
        self.config = config
        self.local_destination = local_destination
        self.is_local_mode = local_destination is not None
        self.dry_run = dry_run
        
        if self.is_local_mode:
            self.local_manager = LocalBackupManager(config, local_destination)
            self.rclone = None
        else:
            self.rclone = RcloneManager(config)
            self.local_manager = None
            
        self.logger = logging.getLogger(__name__)

    def perform_preflight_checks(self, backup_list: List[BackupItem]) -> List[str]:
        """
        Perform pre-flight checks before starting backups.

        Returns:
            List of error messages (empty if all checks pass)
        """
        errors = []

        if self.is_local_mode:
            # Local mode checks
            if not self.local_manager.validate_destination():
                errors.append(f"Local destination not accessible or writable: {self.local_destination}")
        else:
            # Rclone mode checks
            if not self.rclone.validate_rclone_installation():
                errors.append("rclone is not installed or not accessible")
                return errors  # Can't continue without rclone

            # Validate rclone paths contain remote names
            for backup_item in backup_list:
                if ":" not in backup_item.rclone_path:
                    errors.append(
                        f"Backup '{backup_item.name}' rclone_path must include a remote name (e.g., 'remote:/path')"
                    )

            # Check remote storage space (skip in local mode as requested)
            checked_remotes = set()
            for backup_item in backup_list:
                if ":" in backup_item.rclone_path:  # Only if valid format
                    remote_name = backup_item.remote_name
                    if remote_name not in checked_remotes:
                        if not self.rclone.check_remote_space(remote_name):
                            errors.append(
                                f"Remote '{remote_name}' has insufficient free space or is not accessible"
                            )
                        checked_remotes.add(remote_name)

        # Check source directories (common to both modes)
        for backup_item in backup_list:
            if not is_directory_accessible(backup_item.source_dir):
                errors.append(
                    f"Source directory not accessible for backup '{backup_item.name}': {backup_item.source_dir}"
                )

        # Check source directory sizes
        for backup_item in backup_list:
            try:
                if is_directory_accessible(backup_item.source_dir):
                    # Get files within age criteria
                    files_to_backup = get_files_modified_within_days(
                        backup_item.source_dir, backup_item.max_age
                    )
                    total_size = calculate_total_size(files_to_backup)

                    if total_size > backup_item.max_size_bytes:
                        errors.append(
                            f"Backup '{backup_item.name}' size exceeds limit: "
                            f"{total_size} bytes (limit: {backup_item.max_size_bytes} bytes)"
                        )
            except Exception as e:
                errors.append(
                    f"Error calculating size for backup '{backup_item.name}': {e}"
                )

        return errors

    def create_backup(self, backup_item: BackupItem) -> BackupResult:
        """Create a single backup."""
        start_time = datetime.now()
        self.logger.info(f"Starting backup: {backup_item.name}")

        try:
            # Create timestamped destination directory
            timestamp = start_time.strftime("%Y-%m-%d_%H-%M")
            
            if self.is_local_mode:
                # Local filesystem backup
                dest_path = Path(self.local_destination) / f"{backup_item.name}_{timestamp}"
                destination = str(dest_path)
                
                # Perform the backup
                success, bytes_transferred, error_message = self.local_manager.copy_to_local(
                    backup_item.source_dir, destination, backup_item.max_age
                )
            else:
                # Rclone backup
                destination = f"{backup_item.rclone_path}_{timestamp}"
                
                # Perform the backup
                success, bytes_transferred, error_message = self.rclone.copy_to_remote(
                    backup_item.source_dir, destination, backup_item.max_age
                )

            # Get latest file date if backup was successful
            latest_file_date = None
            if success and is_directory_accessible(backup_item.source_dir):
                try:
                    files_to_backup = get_files_modified_within_days(
                        backup_item.source_dir, backup_item.max_age
                    )
                    if files_to_backup:
                        # Get the most recent modification time
                        latest_file_date = max(
                            Path(f).stat().st_mtime for f in files_to_backup
                        )
                        latest_file_date = datetime.fromtimestamp(latest_file_date)
                except Exception as e:
                    self.logger.warning(
                        f"Could not determine latest file date for {backup_item.name}: {e}"
                    )

            execution_time = (datetime.now() - start_time).total_seconds()

            result = BackupResult(
                backup_name=backup_item.name,
                success=success,
                bytes_transferred=bytes_transferred,
                error_message=error_message,
                execution_time=execution_time,
                latest_file_date=latest_file_date,
            )

            if success:
                self.logger.info(
                    f"Backup '{backup_item.name}' completed successfully: "
                    f"{bytes_transferred} bytes transferred in {execution_time:.2f}s"
                )
                # Perform cleanup
                self._cleanup_old_backups(backup_item)
            else:
                self.logger.error(f"Backup '{backup_item.name}' failed: {error_message}")

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_message = f"Unexpected error during backup: {e}"
            self.logger.error(error_message)

            return BackupResult(
                backup_name=backup_item.name,
                success=False,
                error_message=error_message,
                execution_time=execution_time,
            )

    def _cleanup_old_backups(self, backup_item: BackupItem) -> None:
        """Clean up old backup directories based on retention policy."""
        try:
            if self.is_local_mode:
                # Local filesystem cleanup
                parent_path = Path(self.local_destination)
                backup_name = backup_item.name
                
                existing_dirs = self.local_manager.list_local_directories(str(parent_path))
                
                # Filter directories that match this backup
                backup_dirs = []
                for dir_name in existing_dirs:
                    if dir_name.startswith(f"{backup_name}_") and len(dir_name) > len(backup_name) + 1:
                        # Validate timestamp format
                        timestamp_part = dir_name[len(backup_name) + 1:]
                        try:
                            datetime.strptime(timestamp_part, "%Y-%m-%d_%H-%M")
                            backup_dirs.append((dir_name, timestamp_part))
                        except ValueError:
                            continue

                # Sort by timestamp (newest first)
                backup_dirs.sort(key=lambda x: x[1], reverse=True)

                # Delete old backups beyond retention limit
                if len(backup_dirs) > backup_item.retention:
                    dirs_to_delete = backup_dirs[backup_item.retention:]
                    for dir_name, _ in dirs_to_delete:
                        full_path = str(parent_path / dir_name)
                        self.logger.info(f"Deleting old backup: {full_path}")
                        self.local_manager.delete_local_directory(full_path)
                        
            else:
                # Rclone cleanup (original logic)
                base_path = backup_item.rclone_path.rsplit("_", 1)[0]  # Remove any existing timestamp
                parent_path = "/".join(base_path.split("/")[:-1])
                backup_name = base_path.split("/")[-1]

                existing_dirs = self.rclone.list_remote_directories(parent_path)

                # Filter directories that match this backup
                backup_dirs = []
                for dir_name in existing_dirs:
                    if dir_name.startswith(f"{backup_name}_") and len(dir_name) > len(backup_name) + 1:
                        # Validate timestamp format
                        timestamp_part = dir_name[len(backup_name) + 1:]
                        try:
                            datetime.strptime(timestamp_part, "%Y-%m-%d_%H-%M")
                            backup_dirs.append((dir_name, timestamp_part))
                        except ValueError:
                            continue

                # Sort by timestamp (newest first)
                backup_dirs.sort(key=lambda x: x[1], reverse=True)

                # Delete old backups beyond retention limit
                if len(backup_dirs) > backup_item.retention:
                    dirs_to_delete = backup_dirs[backup_item.retention:]
                    for dir_name, _ in dirs_to_delete:
                        full_path = f"{parent_path}/{dir_name}"
                        self.logger.info(f"Deleting old backup: {full_path}")
                        self.rclone.delete_remote_directory(full_path)

        except Exception as e:
            self.logger.warning(f"Error during cleanup for backup '{backup_item.name}': {e}")
    def create_backup_dry_run(self, backup_item: BackupItem) -> DryRunResult:
        """Perform dry run analysis for a backup item."""
        self.logger.info(f"Analyzing backup: {backup_item.name}")
        
        try:
            # Create timestamped destination directory name
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
            
            if self.is_local_mode:
                destination = f"{self.local_destination}/{backup_item.name}_{timestamp}"
                destination_type = "local"
            else:
                destination = f"{backup_item.rclone_path}_{timestamp}"
                destination_type = "remote"
            
            # Analyze files that would be copied
            files_to_copy, excluded_files, total_size = analyze_backup_files(
                backup_item.source_dir,
                backup_item.max_age,
                backup_item.max_size_bytes
            )
            
            total_files = len(files_to_copy)
            
            self.logger.info(
                f"Analysis complete for '{backup_item.name}': "
                f"{total_files} files, {format_size(total_size)}"
            )
            
            return DryRunResult(
                backup_name=backup_item.name,
                source_dir=backup_item.source_dir,
                destination=destination,
                total_files=total_files,
                total_size=total_size,
                filtered_files=files_to_copy,
                excluded_files=excluded_files,
                success=True
            )
            
        except Exception as e:
            error_msg = f"Dry run analysis failed: {e}"
            self.logger.error(f"Error analyzing backup '{backup_item.name}': {error_msg}")
            
            return DryRunResult(
                backup_name=backup_item.name,
                source_dir=backup_item.source_dir,
                destination="",
                success=False,
                error_message=error_msg
            )

    def run_all_backups_dry_run(self, backup_list: List[BackupItem]) -> DryRunSummary:
        """Run dry run analysis for all backup items."""
        self.logger.info(f"Starting dry run analysis for {len(backup_list)} backups")
        
        summary = DryRunSummary()
        
        for backup_item in backup_list:
            result = self.create_backup_dry_run(backup_item)
            summary.add_result(result)
        
        self.logger.info(
            f"Dry run analysis complete: {summary.successful_backups} successful, "
            f"{summary.failed_backups} failed, {format_size(summary.total_size)} total"
        )
        
        return summary
