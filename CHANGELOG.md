# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2025-09-08

### Added
- **Uptime Kuma Integration**: Built-in health monitoring with push notifications
  - Smart monitoring that only tracks rclone mode backups (cloud storage operations)
  - HTTP GET requests to Uptime Kuma push monitor endpoint
  - Success/failure status mapping based on backup results
  - Automatic retry logic with 2-minute delay on notification failures
  - Error isolation - notification failures don't affect backup operations
  - Configurable monitor ID via code modification

### Changed
- **Documentation**: Updated README.md with comprehensive Uptime Kuma integration guide
  - Added setup instructions for Uptime Kuma monitoring
  - Updated feature list and requirements
  - Added notification behavior explanations for all modes
  - Included troubleshooting section for Uptime Kuma connectivity
  - Added performance tips for proactive monitoring

### Technical Details
- **Notification Behavior**:
  - ✅ **Rclone mode** (`python main.py`): Sends notifications
  - ❌ **Local filesystem mode** (`python main.py /path`): Skips notifications  
  - ❌ **Dry-run mode** (`python main.py --dry-run`): Skips notifications
- **Status Mapping**:
  - Success (`return 0`): `status=up&msg=OK`
  - Configuration errors (`return 1`): `status=down&msg=FAILED`
  - Backup failures (`return 2`): `status=down&msg=FAILED`
- **Push URL Format**: `http://localhost:3001/api/push/MhyfEdOgdA?status=up&msg=OK&ping=`

## [1.0.0] - 2024-XX-XX

### Added
- Initial release with core backup functionality
- Dual backup modes (rclone remote storage and local filesystem)
- Cron-based scheduling with flexible configuration
- Multiple backup sources with individual settings
- Email notifications with comprehensive summaries
- Pre-flight checks and error handling
- Retention management and cleanup
- Comprehensive logging system

