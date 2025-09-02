import pytest
import tempfile
import subprocess
import requests
from pathlib import Path
from unittest.mock import patch, MagicMock

from putio_migrator.download_manager import DownloadManager, DownloadError
from putio_migrator.file_scanner import FileTreeNode
from putio_migrator.main import main


class TestAdditionalCoverage:
    """Additional tests to improve coverage of edge cases."""
    
    def test_download_manager_fallback_request_error(self):
        """Test download manager fallback handling request errors"""
        with tempfile.TemporaryDirectory() as temp_dir:
            download_manager = DownloadManager(destination_path=temp_dir, use_fallback=True)
            
            file_node = FileTreeNode(
                name="test_file.txt",
                file_id=123,
                size=1024,
                is_folder=False,
                parent_id=0,
                full_path="test_file.txt"
            )
            
            # Mock Axel failure and requests failure
            with patch('subprocess.run') as mock_run:
                mock_run.side_effect = FileNotFoundError("axel not found")
                
                with patch('requests.get') as mock_get:
                    mock_get.side_effect = requests.exceptions.ConnectionError("Connection failed")
                    
                    with pytest.raises(DownloadError, match="Connection failed"):
                        download_manager.download_file(file_node, "https://example.com/file.txt")

    def test_download_manager_fallback_file_not_exist_after_download(self):
        """Test fallback download when file doesn't exist after download"""
        with tempfile.TemporaryDirectory() as temp_dir:
            download_manager = DownloadManager(destination_path=temp_dir, use_fallback=True)
            
            file_node = FileTreeNode(
                name="test_file.txt",
                file_id=123,
                size=1024,
                is_folder=False,
                parent_id=0,
                full_path="test_file.txt"
            )
            
            with patch('subprocess.run') as mock_run:
                mock_run.side_effect = FileNotFoundError("axel not found")
                
                with patch('requests.get') as mock_get:
                    mock_response = MagicMock()
                    mock_response.iter_content.return_value = [b"test_content"]
                    mock_response.__enter__ = lambda x: mock_response
                    mock_response.__exit__ = lambda x, y, z, a: None
                    mock_get.return_value = mock_response
                    
                    with patch('builtins.open', MagicMock()):
                        with patch('pathlib.Path.exists', return_value=False):
                            with pytest.raises(DownloadError, match="Downloaded file does not exist"):
                                download_manager.download_file(file_node, "https://example.com/file.txt")

    def test_file_scanner_print_tree(self):
        """Test file scanner tree printing functionality"""
        mock_client = MagicMock()
        mock_client.list_files.return_value = {
            "files": [
                {"id": 1, "name": "file1.txt", "file_type": "VIDEO", "size": 1024, "parent_id": 0},
                {"id": 2, "name": "folder1", "file_type": "FOLDER", "size": 0, "parent_id": 0}
            ],
            "parent": {"id": 0}
        }
        
        from putio_migrator.file_scanner import FileScanner
        scanner = FileScanner(mock_client)
        tree = scanner.scan_account()
        
        with patch('builtins.print') as mock_print:
            scanner.print_tree(tree)
            assert mock_print.called

    def test_main_with_exception_handling(self):
        """Test main function exception handling"""
        with patch('sys.argv', ['putio-migrator', '--config', 'nonexistent.toml']):
            with patch('putio_migrator.main.MigrationOrchestrator') as mock_orchestrator:
                mock_orchestrator.side_effect = Exception("Configuration error")
                
                with patch('builtins.print') as mock_print:
                    with patch('sys.exit') as mock_exit:
                        main()
                        
                        mock_exit.assert_called_once_with(1)
                        # Verify error was printed
                        printed_calls = [str(call) for call in mock_print.call_args_list]
                        assert any("Fatal error" in call for call in printed_calls)

    def test_config_manager_path_validation_edge_cases(self):
        """Test edge cases in configuration path validation"""
        from putio_migrator.config_manager import ConfigManager, ConfigValidationError
        import toml
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test negative timeout
            config_data = {
                "putio": {"oauth_token": "test_token"},
                "destination": {"base_path": temp_dir},
                "download": {"timeout": -5}
            }
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
                toml.dump(config_data, f)
                config_file = f.name
            
            try:
                with pytest.raises(ConfigValidationError, match="Download timeout must be positive"):
                    ConfigManager(config_file)
            finally:
                import os
                os.unlink(config_file)

    def test_state_manager_file_state_initialization(self):
        """Test FileState initialization with default values"""
        from putio_migrator.state_manager import FileState
        
        # Test with minimal parameters
        file_state = FileState(
            file_path="/test/file.txt",
            total_bytes=1024
        )
        
        assert file_state.file_path == "/test/file.txt"
        assert file_state.total_bytes == 1024
        assert file_state.downloaded_bytes == 0
        assert file_state.status == "pending"
        assert file_state.error_message is None
        assert file_state.retry_count == 0
        assert file_state.last_updated is not None  # Should be set automatically

    def test_putio_client_file_info_method(self):
        """Test Put.io client get_file_info method"""
        import responses
        
        @responses.activate
        def run_test():
            responses.add(
                responses.GET,
                "https://api.put.io/v2/files/123",
                json={"file": {"id": 123, "name": "test.txt", "size": 1024}},
                status=200
            )
            
            from putio_migrator.putio_client import PutioClient
            client = PutioClient("test_token")
            file_info = client.get_file_info(123)
            
            assert file_info["file"]["id"] == 123
            assert file_info["file"]["name"] == "test.txt"
        
        run_test()