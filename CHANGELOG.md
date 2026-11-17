# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-11-16
### Added
- get_status, start, stop, get_result, get_history, get_config, update_config
  and get_links: measurements per interface with their progress, schedules and
  history, over librespeed-common's ubus interface
- descriptions of every action and field in the schema, and an API reference
  in the README

### Changed
- measurements, schedules and history are librespeed-common's, shared with
  luci-app-librespeed

### Removed
- get_settings, update_settings, get_data and measure; the reForis LibreSpeed
  plugin 2.0 uses the actions above
- turris-librespeed and the module's own result files, and the
  python-dateutil dependency

## [1.3.0] - 2026-07-02
### Added
- added entry point to properly register as foris-controller-module

## [1.2.0] - 2026-04-30
### Added
- Use custom server list remote file for librespeed-cli

## [1.1.0] - 2024-05-23
### Added
- make it possible to pick the server with uci option

## [1.0.0] - 2024-05-23
### Changed
- build project using hatchling
- dependencies updates

## [0.1.0] - 2023-06-08
### Added
- initial version
