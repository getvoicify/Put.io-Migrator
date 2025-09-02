"""Configuration management for Put.io to NAS migration tool."""

import sys
import toml
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


class ConfigManager:
    """Manages TOML configuration loading and validation."""
    
    # Default configuration values
    DEFAULTS = {
        "putio": {
            "api_base_url": "https://api.put.io/v2"
        },
        "destination": {
            "preserve_structure": True
        },
        "download": {
            "connections": 4,
            "timeout": 30,
            "retry_limit": 3
        },
        "filters": {
            "max_file_size_gb": None,
            "allowed_extensions": None,
            "blocked_extensions": None
        },
        "behavior": {
            "auto_confirm": False,
            "cleanup_after_download": False,
            "rescan_on_startup": True
        },
        "state": {
            "file_path": "migration_state.json",
            "save_frequency_seconds": 30
        },
        "logging": {
            "level": "INFO",
            "file_path": None
        },
        "advanced": {
            "api_requests_per_second": 5,
            "user_agent": "putio-migrator/0.1.0",
            "use_fallback_downloader": True
        }
    }
    
    def __init__(self, config_path: str):
        """Initialize configuration manager.
        
        Args:
            config_path: Path to TOML configuration file
            
        Raises:
            ConfigValidationError: If configuration is invalid
            SystemExit: If config file doesn't exist and sample is created
        """
        self.config_path = Path(config_path)
        
        if not self.config_path.exists():
            self._create_sample_config()
            print(f"Sample configuration created at {config_path}")
            print("Please edit the configuration file and run again.")
            sys.exit(0)
        
        self._load_config()
        self._validate_config()
    
    def _load_config(self):
        """Load configuration from TOML file."""
        with open(self.config_path, 'r') as f:
            self._raw_config = toml.load(f)
        
        # Apply defaults for missing sections
        for section_name, section_defaults in self.DEFAULTS.items():
            if section_name not in self._raw_config:
                self._raw_config[section_name] = {}
            
            for key, default_value in section_defaults.items():
                if key not in self._raw_config[section_name]:
                    self._raw_config[section_name][key] = default_value
    
    def _validate_config(self):
        """Validate configuration values."""
        # Required fields
        if not self._raw_config.get("putio", {}).get("oauth_token"):
            raise ConfigValidationError("OAuth token is required in [putio] section")
        
        if not self._raw_config.get("destination", {}).get("base_path"):
            raise ConfigValidationError("Destination base path is required in [destination] section")
        
        # Validate destination path exists
        dest_path = Path(self._raw_config["destination"]["base_path"])
        if not dest_path.exists():
            raise ConfigValidationError(f"Destination path does not exist: {dest_path}")
        
        # Validate numeric ranges
        connections = self._raw_config["download"]["connections"]
        if not (1 <= connections <= 16):
            raise ConfigValidationError("Download connections must be between 1 and 16")
        
        timeout = self._raw_config["download"]["timeout"]
        if timeout <= 0:
            raise ConfigValidationError("Download timeout must be positive")
        
        retry_limit = self._raw_config["download"]["retry_limit"]
        if retry_limit < 0:
            raise ConfigValidationError("Download retry limit must be non-negative")
    
    def _create_sample_config(self):
        """Create sample configuration file."""
        sample_config = {
            "putio": {
                "oauth_token": "YOUR_PUTIO_OAUTH_TOKEN_HERE",
                "api_base_url": "https://api.put.io/v2"
            },
            "destination": {
                "base_path": "/path/to/your/nas/downloads",
                "preserve_structure": True
            },
            "download": {
                "connections": 4,
                "timeout": 30,
                "retry_limit": 3
            },
            "filters": {
                "max_file_size_gb": None,
                "allowed_extensions": ["mp4", "mkv", "avi", "mp3", "flac"],
                "blocked_extensions": ["tmp", "part"]
            },
            "behavior": {
                "auto_confirm": False,
                "cleanup_after_download": False,
                "rescan_on_startup": True
            },
            "state": {
                "file_path": "migration_state.json",
                "save_frequency_seconds": 30
            },
            "logging": {
                "level": "INFO",
                "file_path": "migration.log"
            },
            "advanced": {
                "api_requests_per_second": 5,
                "user_agent": "putio-migrator/0.1.0",
                "use_fallback_downloader": True
            }
        }
        
        with open(self.config_path, 'w') as f:
            toml.dump(sample_config, f)
    
    # Property accessors for easy access to configuration values
    @property
    def putio_oauth_token(self) -> str:
        return self._raw_config["putio"]["oauth_token"]
    
    @property
    def putio_api_base_url(self) -> str:
        return self._raw_config["putio"]["api_base_url"]
    
    @property
    def destination_base_path(self) -> str:
        return self._raw_config["destination"]["base_path"]
    
    @property
    def destination_preserve_structure(self) -> bool:
        return self._raw_config["destination"]["preserve_structure"]
    
    @property
    def download_connections(self) -> int:
        return self._raw_config["download"]["connections"]
    
    @property
    def download_timeout(self) -> int:
        return self._raw_config["download"]["timeout"]
    
    @property
    def download_retry_limit(self) -> int:
        return self._raw_config["download"]["retry_limit"]
    
    @property
    def logging_level(self) -> str:
        return self._raw_config["logging"]["level"]
    
    @property
    def state_file_path(self) -> str:
        return self._raw_config["state"]["file_path"]
    
    @property
    def state_save_frequency(self) -> int:
        return self._raw_config["state"]["save_frequency_seconds"]