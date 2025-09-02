import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock
from pathlib import Path

from putio_migrator.main import MigrationOrchestrator, main
from putio_migrator.file_scanner import FileTreeNode


class TestMigrationOrchestrator:
    
    def test_orchestrator_initialization(self):
        """Test orchestrator initializes with config file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            config_content = """
[putio]
oauth_token = "test_token"

[destination]
base_path = "/tmp"
"""
            f.write(config_content)
            config_file = f.name
        
        try:
            with patch('putio_migrator.main.ConfigManager') as mock_config_class:
                with patch('putio_migrator.main.StateManager') as mock_state_class:
                    with patch('putio_migrator.main.PutioClient') as mock_client_class:
                        # Setup mock config instance
                        mock_config = MagicMock()
                        mock_config.state_file_path = "test_state.json"
                        mock_config.state_save_frequency = 30
                        mock_config.putio_oauth_token = "test_token"
                        mock_config.putio_api_base_url = "https://api.put.io/v2"
                        mock_config.download_retry_limit = 3
                        mock_config.logging_level = "INFO"
                        mock_config_class.return_value = mock_config
                        
                        orchestrator = MigrationOrchestrator(config_file)
                        
                        assert orchestrator.config_path == config_file
                        mock_config_class.assert_called_once_with(config_file)
        finally:
            os.unlink(config_file)

    def test_orchestrator_performs_full_migration_workflow(self):
        """Test complete migration workflow orchestration"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Setup mocks
            mock_config = MagicMock()
            mock_config.putio_oauth_token = "test_token"
            mock_config.destination_base_path = temp_dir
            mock_config.state_file_path = "test_state.json"
            mock_config.state_save_frequency = 30
            mock_config.putio_api_base_url = "https://api.put.io/v2"
            mock_config.download_retry_limit = 3
            mock_config.logging_level = "INFO"
            mock_config.download_connections = 4
            mock_config.download_timeout = 30
            mock_config.destination_preserve_structure = True
            mock_config.state_file_path = "test_state.json"
            mock_config.state_save_frequency = 30
            mock_config.putio_api_base_url = "https://api.put.io/v2"
            mock_config.download_retry_limit = 3
            mock_config.logging_level = "INFO"
            mock_config.download_connections = 4
            mock_config.download_timeout = 30
            mock_config.destination_preserve_structure = True
            
            mock_state = MagicMock()
            mock_state.get_completed_files.return_value = {}
            mock_state.is_file_completed.return_value = False
            
            mock_client = MagicMock()
            mock_client.get_account_info.return_value = {"info": {"username": "testuser"}}
            mock_client.get_download_url.return_value = "https://download.put.io/files/test.txt"
            
            # Mock file tree with test files
            test_files = [
                FileTreeNode("file1.txt", 1, 1024, False, 0, "file1.txt"),
                FileTreeNode("file2.txt", 2, 2048, False, 0, "file2.txt")
            ]
            
            mock_scanner = MagicMock()
            mock_scanner.scan_account.return_value = FileTreeNode("root", 0, 0, True, -1, "")
            mock_scanner.get_all_files.return_value = test_files
            mock_scanner.get_total_size.return_value = 3072
            
            mock_download_manager = MagicMock()
            mock_download_manager.download_file.return_value = MagicMock(success=True)
            
            with patch('putio_migrator.main.ConfigManager', return_value=mock_config):
                with patch('putio_migrator.main.StateManager', return_value=mock_state):
                    with patch('putio_migrator.main.PutioClient', return_value=mock_client):
                        with patch('putio_migrator.main.FileScanner', return_value=mock_scanner):
                            with patch('putio_migrator.main.DownloadManager', return_value=mock_download_manager):
                                orchestrator = MigrationOrchestrator("test_config.toml")
                                result = orchestrator.run_migration()
                                
                                # Verify workflow steps
                                mock_scanner.scan_account.assert_called_once()
                                assert mock_download_manager.download_file.call_count == 2
                                assert result["success"] is True

    def test_orchestrator_skips_completed_files(self):
        """Test that orchestrator skips files already marked as completed"""
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_config = MagicMock()
            mock_config.putio_oauth_token = "test_token"
            mock_config.destination_base_path = temp_dir
            mock_config.state_file_path = "test_state.json"
            mock_config.state_save_frequency = 30
            mock_config.putio_api_base_url = "https://api.put.io/v2"
            mock_config.download_retry_limit = 3
            mock_config.logging_level = "INFO"
            mock_config.download_connections = 4
            mock_config.download_timeout = 30
            mock_config.destination_preserve_structure = True
            mock_config.state_file_path = "test_state.json"
            mock_config.state_save_frequency = 30
            mock_config.putio_api_base_url = "https://api.put.io/v2"
            mock_config.download_retry_limit = 3
            mock_config.logging_level = "INFO"
            mock_config.download_connections = 4
            mock_config.download_timeout = 30
            mock_config.destination_preserve_structure = True
            
            # Mock state with one completed file
            mock_state = MagicMock()
            mock_state.get_completed_files.return_value = {"file1.txt": MagicMock()}
            mock_state.is_file_completed.side_effect = lambda path: path == "file1.txt"
            
            test_files = [
                FileTreeNode("file1.txt", 1, 1024, False, 0, "file1.txt"),  # Already completed
                FileTreeNode("file2.txt", 2, 2048, False, 0, "file2.txt")   # Not completed
            ]
            
            mock_scanner = MagicMock()
            mock_scanner.get_all_files.return_value = test_files
            
            mock_download_manager = MagicMock()
            
            with patch('putio_migrator.main.ConfigManager', return_value=mock_config):
                with patch('putio_migrator.main.StateManager', return_value=mock_state):
                    with patch('putio_migrator.main.PutioClient'):
                        with patch('putio_migrator.main.FileScanner', return_value=mock_scanner):
                            with patch('putio_migrator.main.DownloadManager', return_value=mock_download_manager):
                                orchestrator = MigrationOrchestrator("test_config.toml")
                                orchestrator.run_migration()
                                
                                # Should only download file2.txt (file1.txt is already completed)
                                assert mock_download_manager.download_file.call_count == 1
                                downloaded_file = mock_download_manager.download_file.call_args[0][0]
                                assert downloaded_file.name == "file2.txt"

    def test_orchestrator_handles_download_failures(self):
        """Test orchestrator handles individual file download failures"""
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_config = MagicMock()
            mock_config.putio_oauth_token = "test_token"
            mock_config.destination_base_path = temp_dir
            mock_config.state_file_path = "test_state.json"
            mock_config.state_save_frequency = 30
            mock_config.putio_api_base_url = "https://api.put.io/v2"
            mock_config.download_retry_limit = 3
            mock_config.logging_level = "INFO"
            mock_config.download_connections = 4
            mock_config.download_timeout = 30
            mock_config.destination_preserve_structure = True
            
            mock_state = MagicMock()
            mock_state.get_completed_files.return_value = {}
            mock_state.is_file_completed.return_value = False
            mock_state.is_file_completed.return_value = False
            
            test_files = [
                FileTreeNode("file1.txt", 1, 1024, False, 0, "file1.txt")
            ]
            
            mock_scanner = MagicMock()
            mock_scanner.get_all_files.return_value = test_files
            
            # Mock download failure
            mock_download_result = MagicMock()
            mock_download_result.success = False
            mock_download_result.error_message = "Network error"
            
            mock_download_manager = MagicMock()
            mock_download_manager.download_file.return_value = mock_download_result
            
            with patch('putio_migrator.main.ConfigManager', return_value=mock_config):
                with patch('putio_migrator.main.StateManager', return_value=mock_state):
                    with patch('putio_migrator.main.PutioClient'):
                        with patch('putio_migrator.main.FileScanner', return_value=mock_scanner):
                            with patch('putio_migrator.main.DownloadManager', return_value=mock_download_manager):
                                orchestrator = MigrationOrchestrator("test_config.toml")
                                result = orchestrator.run_migration()
                                
                                # Should mark file as failed
                                mock_state.mark_file_failed.assert_called_once_with("file1.txt", "Network error")
                                assert result["failed_files"] == 1

    def test_main_function_with_config_argument(self):
        """Test main function with config file argument"""
        with patch('sys.argv', ['putio-migrator', '--config', 'test_config.toml']):
            with patch('putio_migrator.main.MigrationOrchestrator') as mock_orchestrator:
                mock_instance = MagicMock()
                mock_orchestrator.return_value = mock_instance
                mock_instance.run_migration.return_value = {"success": True}
                
                with patch('builtins.print') as mock_print:
                    main()
                    
                    mock_orchestrator.assert_called_once_with('test_config.toml')
                    mock_instance.run_migration.assert_called_once()

    def test_main_function_with_default_config(self):
        """Test main function uses default config file"""
        with patch('sys.argv', ['putio-migrator']):
            with patch('putio_migrator.main.MigrationOrchestrator') as mock_orchestrator:
                mock_instance = MagicMock()
                mock_orchestrator.return_value = mock_instance
                mock_instance.run_migration.return_value = {"success": True}
                
                main()
                
                mock_orchestrator.assert_called_once_with('config.toml')

    def test_orchestrator_progress_reporting(self):
        """Test progress reporting during migration"""
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_config = MagicMock()
            mock_config.putio_oauth_token = "test_token"
            mock_config.destination_base_path = temp_dir
            mock_config.state_file_path = "test_state.json"
            mock_config.state_save_frequency = 30
            mock_config.putio_api_base_url = "https://api.put.io/v2"
            mock_config.download_retry_limit = 3
            mock_config.logging_level = "INFO"
            mock_config.download_connections = 4
            mock_config.download_timeout = 30
            mock_config.destination_preserve_structure = True
            
            mock_state = MagicMock()
            mock_state.get_completed_files.return_value = {}
            mock_state.is_file_completed.return_value = False
            mock_state.is_file_completed.return_value = False
            
            test_files = [
                FileTreeNode("file1.txt", 1, 1024, False, 0, "file1.txt"),
                FileTreeNode("file2.txt", 2, 2048, False, 0, "file2.txt")
            ]
            
            mock_scanner = MagicMock()
            mock_scanner.get_all_files.return_value = test_files
            mock_scanner.get_total_size.return_value = 3072
            
            mock_download_manager = MagicMock()
            mock_download_manager.download_file.return_value = MagicMock(success=True)
            
            with patch('putio_migrator.main.ConfigManager', return_value=mock_config):
                with patch('putio_migrator.main.StateManager', return_value=mock_state):
                    with patch('putio_migrator.main.PutioClient'):
                        with patch('putio_migrator.main.FileScanner', return_value=mock_scanner):
                            with patch('putio_migrator.main.DownloadManager', return_value=mock_download_manager):
                                with patch('builtins.print') as mock_print:
                                    orchestrator = MigrationOrchestrator("test_config.toml")
                                    orchestrator.run_migration()
                                    
                                    # Verify progress was printed
                                    assert mock_print.called
                                    printed_text = " ".join([str(call) for call in mock_print.call_args_list])
                                    assert "progress" in printed_text.lower() or "migrating" in printed_text.lower()