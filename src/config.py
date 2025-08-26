"""Configuration management for rclone-copy backup system."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

import yaml
from croniter import croniter
from pydantic import BaseModel, Field, field_validator, model_validator

from python_utils.size_utils import parse_size_to_bytes


class ChecksConfig(BaseModel):
    """System checks configuration."""

    min_free_space: str = Field(
        default="200GB", description="Minimum free space required on remote storage"
    )

    @field_validator("min_free_space")
    @classmethod
    def validate_min_free_space(cls, v: str) -> str:
        """Validate the min_free_space format."""
        try:
            parse_size_to_bytes(v)
            return v
        except Exception as e:
            raise ValueError(f"Invalid size format for min_free_space: {e}")


class BackupItem(BaseModel):
    """Configuration for a single backup item."""

    name: str = Field(description="Short name/identifier for the backup")
    source_dir: str = Field(description="Path to the source directory")
    rclone_path: str = Field(description="Path to the rclone directory")
    max_size: str = Field(
        default="1GB", description="Maximum size for the backup using KB/MB/GB format"
    )
    max_age: int = Field(
        default=0, ge=0, description="Maximum age in days of the files to be copied"
    )
    schedule: str = Field(
        default="* * * * 1",
        description="Cron-like schedule: 'minute hour day-of-month month day-of-week'",
    )
    retention: int = Field(
        default=2, ge=1, description="Number of backup copies to keep"
    )
    rclone_enabled: bool = Field(
        default=True,
        description="Whether this backup should run in rclone mode (always runs in local mode)"
    )

    @field_validator("max_size")
    @classmethod
    def validate_max_size(cls, v: str) -> str:
        """Validate the max_size format."""
        try:
            parse_size_to_bytes(v)
            return v
        except Exception as e:
            raise ValueError(f"Invalid size format for max_size: {e}")

    @field_validator("schedule")
    @classmethod
    def validate_schedule(cls, v: str) -> str:
        """Validate the cron schedule format."""
        # Remove extra whitespace and split
        schedule_parts = v.strip().split()

        if len(schedule_parts) != 5:
            raise ValueError(
                "Schedule must have 5 fields: 'minute hour day-of-month month day-of-week'"
            )

        # Validate cron syntax using croniter
        try:
            # Create a test cron expression to validate syntax
            croniter(v)
            return v
        except Exception as e:
            raise ValueError(f"Invalid cron schedule format: {e}")

    @field_validator("source_dir")
    @classmethod
    def validate_source_dir(cls, v: str) -> str:
        """Validate source directory path."""
        if not v.startswith("/"):
            raise ValueError("source_dir must be an absolute path")
        return v

    @field_validator("rclone_path")
    @classmethod
    def validate_rclone_path(cls, v: str) -> str:
        """Validate rclone path format."""
        # Skip validation in local mode - this will be checked at runtime
        # The validation is conditional because we don't know the mode at config load time
        return v

    @property
    def max_size_bytes(self) -> int:
        """Get max_size as bytes."""
        return parse_size_to_bytes(self.max_size)

    @property
    def remote_name(self) -> str:
        """Extract remote name from rclone_path."""
        return self.rclone_path.split(":")[0]


class AppConfig(BaseModel):
    """Main application configuration."""

    email: List[str] = Field(
        default_factory=list, description="List of emails to send notifications to"
    )
    log_level: str = Field(
        default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    log_file: str = Field(
        default="log/rclone_copy.log",
        description="Path to log file relative to project root",
    )
    checks: ChecksConfig = Field(default_factory=ChecksConfig)
    backup_copy_list: List[BackupItem] = Field(
        description="List of directories to copy to remote storage"
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"log_level must be one of: {', '.join(valid_levels)}")
        return v_upper

    @field_validator("email")
    @classmethod
    def validate_email_list(cls, v: List[str]) -> List[str]:
        """Validate email addresses."""
        email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
        for email in v:
            if not email_pattern.match(email):
                raise ValueError(f"Invalid email format: {email}")
        return v

    @model_validator(mode="after")
    def validate_backup_names_unique(self) -> AppConfig:
        """Ensure backup names are unique."""
        names = [item.name for item in self.backup_copy_list]
        if len(names) != len(set(names)):
            raise ValueError("Backup names must be unique")
        return self

    @property
    def min_free_space_bytes(self) -> int:
        """Get minimum free space as bytes."""
        return parse_size_to_bytes(self.checks.min_free_space)


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """Load and validate configuration from YAML file."""
    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        if config_data is None:
            raise ValueError("Configuration file is empty")

        return AppConfig(**config_data)

    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML format in config file: {e}")
    except Exception as e:
        raise ValueError(f"Configuration validation error: {e}")