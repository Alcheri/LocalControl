# Changelog

All notable changes to LocalControl will be documented in this file.

## [Unreleased]

### Added

- Added an optional TCP listener for local testing tools, disabled by default.
- Added configuration for the TCP listener host, port, and non-loopback binding
  override.
- Added regression tests for TCP loopback binding and non-loopback rejection.
- Added beta GUI binaries for Linux and Windows.

### Changed

- The optional TCP listener now retries briefly when rebinding during plugin
  reload.

### Security

- The optional TCP listener is loopback-only by default because TCP access is
  equivalent to owner-level LocalControl access.

## [1.1.0] - 2026-04-25

### Added

- Added owner-only socket permission enforcement for `.localcontrol.sock`.
- Added per-client socket timeouts for idle local connections.
- Added serialised LocalControl dispatch while Limnoria reply capture is active.
- Added safe request logging by default with command name and argument count.
- Added `socketRequestFullCommandLogging` for opt-in redacted full command logs.
- Added regression tests for socket permissions, idle timeouts, dispatch locking,
  and redacted logging.

### Changed

- Request logs now record `status=ok` for successful requests instead of using
  reply text as the log status.
- Full command text is no longer logged unless explicitly enabled.

### Security

- Reduced the risk of accidental local command exposure through bot logs.
- Reduced the risk of idle local clients holding handler threads indefinitely.
- Reduced the risk of concurrent LocalControl requests racing shared IRC send
  and queue hooks.

## [1.0.0]

### Added

- Initial stable release of the LocalControl Limnoria plugin.
- Added a local UNIX-socket control interface for Limnoria commands.
- Added the `botctl` command-line client.
- Added setup, usage, troubleshooting, and multi-bot wrapper documentation.
