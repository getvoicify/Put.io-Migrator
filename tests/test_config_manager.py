import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, mock_open
import toml

from putio_migrator.config_manager import ConfigManager, ConfigValidationError


class TestConfigManager:
    
    def test_config_loads_from_toml_file(self):
        """Test loading configuration from TOML file"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_data = {
                "putio": {
                    "oauth_token": "test_token_123",
                    "api_base_url": "https://api.put.io/v2"
                },
                "destination": {
                    "base_path": temp_dir,
                    "preserve_structure": True
                },
                "download": {
                    "connections": 4,
                    "timeout": 30,
                    "retry_limit": 3
                }
            }
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
                toml.dump(config_data, f)
                config_file = f.name
            
            try:
                config = ConfigManager(config_file)
                assert config.putio_oauth_token == "test_token_123"
                assert config.putio_api_base_url == "https://api.put.io/v2"
                assert config.destination_base_path == temp_dir
                assert config.destination_preserve_structure is True
                assert config.download_connections == 4
                assert config.download_timeout == 30
                assert config.download_retry_limit == 3
            finally:
                os.unlink(config_file)

    def test_config_validation_fails_for_missing_token(self):
        """Test validation fails when OAuth token is missing"""
        config_data = {
            "destination": {
                "base_path": "/mnt/nas/downloads"
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            toml.dump(config_data, f)
            config_file = f.name
        
        try:
            with pytest.raises(ConfigValidationError, match="OAuth token is required"):
                ConfigManager(config_file)
        finally:
            os.unlink(config_file)

    def test_config_validation_fails_for_missing_destination(self):
        """Test validation fails when destination path is missing"""
        config_data = {
            "putio": {
                "oauth_token": "test_token_123"
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            toml.dump(config_data, f)
            config_file = f.name
        
        try:
            with pytest.raises(ConfigValidationError, match="Destination base path is required"):
                ConfigManager(config_file)
        finally:
            os.unlink(config_file)

    def test_config_creates_sample_when_missing(self):
        """Test sample config creation when file doesn't exist"""
        with tempfile.TemporaryDirectory() as temp_dir:
            non_existent_file = os.path.join(temp_dir, "non_existent_config.toml")
            
            with patch('sys.exit') as mock_exit:
                mock_exit.side_effect = SystemExit(0)
                
                with pytest.raises(SystemExit):
                    ConfigManager(non_existent_file)
                
                mock_exit.assert_called_once_with(0)
                
                # Verify sample config was created
                assert Path(non_existent_file).exists()

    def test_config_uses_defaults_for_optional_values(self):
        """Test that default values are used for optional configuration"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_data = {
                "putio": {
                    "oauth_token": "test_token_123"
                },
                "destination": {
                    "base_path": temp_dir
                }
            }
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
                toml.dump(config_data, f)
                config_file = f.name
            
            try:
                config = ConfigManager(config_file)
                assert config.putio_api_base_url == "https://api.put.io/v2"
                assert config.destination_preserve_structure is True
                assert config.download_connections == 4
                assert config.download_timeout == 30
                assert config.download_retry_limit == 3
                assert config.logging_level == "INFO"
            finally:
                os.unlink(config_file)

    def test_config_validates_numeric_ranges(self):
        """Test validation of numeric configuration values"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_data = {
                "putio": {"oauth_token": "test_token_123"},
                "destination": {"base_path": temp_dir},
                "download": {"connections": 0}  # Invalid: should be >= 1
            }
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
                toml.dump(config_data, f)
                config_file = f.name
            
            try:
                with pytest.raises(ConfigValidationError, match="Download connections must be between 1 and 16"):
                    ConfigManager(config_file)
            finally:
                os.unlink(config_file)

    def test_config_validates_path_existence(self):
        """Test validation of destination path existence"""
        config_data = {
            "putio": {"oauth_token": "test_token_123"},
            "destination": {"base_path": "/non/existent/path"}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            toml.dump(config_data, f)
            config_file = f.name
        
        try:
            with pytest.raises(ConfigValidationError, match="Destination path does not exist"):
                ConfigManager(config_file)
        finally:
            os.unlink(config_file)