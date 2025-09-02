# Put.io to NAS Migration Tool

A robust, resumable file migration tool that transfers files from Put.io to Network Attached Storage (NAS) while preserving folder structure. Built with Test-Driven Development (TDD) principles for reliability and maintainability.

## Features

- **Resumable Downloads**: Continue exactly where interrupted (files, partial downloads)
- **Folder Structure Preservation**: Maintains exact Put.io folder hierarchy
- **High-Speed Downloads**: Uses Axel for accelerated multi-connection downloads
- **Graceful Interruption Handling**: SIGINT/SIGTERM support with state saving
- **File Integrity Verification**: Ensures downloaded files match expected sizes
- **Comprehensive Filtering**: Filter by file extensions, sizes, and path patterns
- **Retry Logic**: Progressive backoff for failed downloads and API calls
- **State Persistence**: Survives crashes and restarts with JSON state files
- **TOML Configuration**: Flexible, human-readable configuration

## Installation

### Prerequisites

- Python 3.8 or higher
- Axel download accelerator (optional, will fallback to requests if not available)

```bash
# Install Axel (macOS)
brew install axel

# Install Axel (Ubuntu/Debian)
sudo apt-get install axel

# Install Axel (CentOS/RHEL)
sudo yum install axel
```

### Install the Migration Tool

```bash
git clone <repository-url>
cd putio-migrator
pip install -r requirements.txt
```

## Quick Start

1. **Run the tool to generate a sample configuration:**
   ```bash
   python -m putio_migrator.main
   ```

2. **Edit the generated `config.toml` file:**
   - Add your Put.io OAuth token
   - Set your NAS destination path
   - Configure download settings

3. **Run the migration:**
   ```bash
   python -m putio_migrator.main --config config.toml
   ```

## Configuration

The tool uses TOML configuration files. Run the tool once to generate a sample configuration, then edit it according to your needs.

### Required Configuration

```toml
[putio]
oauth_token = "YOUR_PUTIO_OAUTH_TOKEN_HERE"

[destination]
base_path = "/path/to/your/nas/downloads"
```

### Complete Configuration Example

See `examples/config.toml` for a complete configuration example with all available options.

## Usage

### Basic Migration
```bash
python -m putio_migrator.main --config config.toml
```

### Dry Run (Scan Only)
```bash
python -m putio_migrator.main --config config.toml --dry-run
```

### Custom Configuration File
```bash
python -m putio_migrator.main --config /path/to/custom/config.toml
```

## How It Works

1. **Authentication**: Verifies Put.io OAuth token
2. **Account Scanning**: Recursively scans your entire Put.io account
3. **State Loading**: Loads previous migration state (if exists)
4. **File Filtering**: Applies configured filters (extensions, size limits)
5. **Download Planning**: Determines which files need downloading
6. **Download Execution**: Downloads files using Axel with resume support
7. **State Persistence**: Continuously saves progress for resumability

## State Management

The tool maintains a JSON state file that tracks:
- Completed files and their sizes
- Failed files with error messages and retry counts
- Files currently in progress with partial download status
- Overall migration statistics and timestamps

State is automatically saved:
- Every 30 seconds during migration (configurable)
- After each file completion or failure
- When receiving interruption signals (SIGINT/SIGTERM)

## Error Handling

- **Network Issues**: Automatic retries with exponential backoff
- **API Rate Limits**: Respects Put.io rate limiting headers
- **Partial Downloads**: Automatically resumes using Axel's `-c` option
- **Corrupted State**: Gracefully handles and rebuilds from corrupted state files
- **Missing Dependencies**: Falls back to requests if Axel is unavailable

## Development

### Running Tests

```bash
# Run all tests
python -m pytest

# Run with coverage
python -m pytest --cov=putio_migrator --cov-report=html

# Run specific test module
python -m pytest tests/test_config_manager.py -v
```

### Test Structure

- **Unit Tests**: Test individual modules in isolation
- **Integration Tests**: Test module interactions
- **End-to-End Tests**: Test complete workflows

Current test coverage: >90% with 57+ tests covering all major functionality.

## Architecture

The tool follows a modular architecture with clear separation of concerns:

- `config_manager.py`: TOML configuration loading and validation
- `state_manager.py`: Persistent state management with signal handling
- `putio_client.py`: Put.io API client with retry logic and rate limiting
- `file_scanner.py`: Recursive account scanning and tree building
- `download_manager.py`: Axel integration with resume support
- `main.py`: Orchestration and user interface

## Contributing

This project was built using Test-Driven Development. When adding new features:

1. Write tests first that define the expected behavior
2. Implement minimal code to make tests pass
3. Refactor while keeping tests green
4. Ensure test coverage remains >90%

## License

[Add your license here]

## Support

For issues and feature requests, please create an issue in the repository.