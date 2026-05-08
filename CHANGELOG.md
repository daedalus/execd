# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-07

### Added
- Initial release
- HTTP REST API server with task execution endpoints
- Python client library for server interaction
- POST /tasks - Submit tasks
- GET /tasks/{id} - Get task status and result
- DELETE /tasks/{id} - Cancel/remove tasks
- In-memory task storage with unique task IDs
- Comprehensive test suite with 80%+ coverage

[0.1.0]: https://github.com/daedalus/execd/releases/tag/v0.1.0
