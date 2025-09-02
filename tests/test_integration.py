import pytest
import tempfile
import json
import os
import responses
from pathlib import Path
from unittest.mock import patch, MagicMock

from putio_migrator.config_manager import ConfigManager
from putio_migrator.state_manager import StateManager
from putio_migrator.putio_client import PutioClient
from putio_migrator.file_scanner import FileScanner
from putio_migrator.download_manager import DownloadManager


class TestIntegration:
    
    def test_config_and_state_integration(self):
        """Test configuration and state management work together"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create config file
            config_data = {
                "putio": {"oauth_token": "test_token"},
                "destination": {"base_path": temp_dir},
                "state": {"file_path": "integration_test_state.json"}
            }
            
            config_file = os.path.join(temp_dir, "config.toml")
            with open(config_file, 'w') as f:
                import toml
                toml.dump(config_data, f)
            
            # Initialize config and state
            config = ConfigManager(config_file)
            state = StateManager(config.state_file_path)
            
            # Add some state data
            state.mark_file_completed("/test/file1.txt", 1024)
            state.save_state()
            
            # Reload state and verify persistence
            state2 = StateManager(config.state_file_path)
            completed = state2.get_completed_files()
            assert "/test/file1.txt" in completed
            assert completed["/test/file1.txt"].total_bytes == 1024

    @responses.activate
    def test_putio_client_and_scanner_integration(self):
        """Test Put.io client and file scanner working together"""
        # Mock Put.io API responses
        responses.add(
            responses.GET,
            "https://api.put.io/v2/files/list",
            json={
                "files": [
                    {"id": 1, "name": "file1.txt", "file_type": "VIDEO", "size": 1024, "parent_id": 0},
                    {"id": 2, "name": "folder1", "file_type": "FOLDER", "size": 0, "parent_id": 0}
                ],
                "parent": {"id": 0}
            },
            status=200
        )
        
        responses.add(
            responses.GET,
            "https://api.put.io/v2/files/list?parent_id=2",
            json={
                "files": [
                    {"id": 3, "name": "nested_file.txt", "file_type": "VIDEO", "size": 2048, "parent_id": 2}
                ],
                "parent": {"id": 2}
            },
            status=200
        )
        
        # Test integration
        client = PutioClient("test_token")
        scanner = FileScanner(client)
        
        file_tree = scanner.scan_account()
        all_files = scanner.get_all_files()
        
        # Verify structure
        assert len(all_files) == 2  # Two files (not counting folder)
        assert any(f.name == "file1.txt" for f in all_files)
        assert any(f.name == "nested_file.txt" for f in all_files)
        assert scanner.get_total_size() == 3072  # 1024 + 2048

    def test_scanner_and_download_manager_integration(self):
        """Test file scanner and download manager integration"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock client
            mock_client = MagicMock()
            mock_client.list_files.return_value = {
                "files": [
                    {"id": 1, "name": "test_file.txt", "file_type": "VIDEO", "size": 1024, "parent_id": 0}
                ],
                "parent": {"id": 0}
            }
            
            # Scan files
            scanner = FileScanner(mock_client)
            file_tree = scanner.scan_account()
            all_files = scanner.get_all_files()
            
            # Set up download manager
            download_manager = DownloadManager(destination_path=temp_dir)
            
            # Mock successful download by creating the file
            test_file = all_files[0]
            target_path = Path(temp_dir) / test_file.name
            target_path.write_bytes(b"x" * 1024)
            
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                
                result = download_manager.download_file(test_file, "https://example.com/file.txt")
                
                assert result.success is True
                assert result.already_existed is True  # File was pre-created

    def test_state_and_download_integration(self):
        """Test state manager and download manager integration"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Initialize state
            state_file = os.path.join(temp_dir, "test_state.json")
            state = StateManager(state_file)
            
            # Initialize download manager
            download_manager = DownloadManager(destination_path=temp_dir)
            
            # Create test file
            from putio_migrator.file_scanner import FileTreeNode
            file_node = FileTreeNode(
                name="test_file.txt",
                file_id=123,
                size=1024,
                is_folder=False,
                parent_id=0,
                full_path="test_file.txt"
            )
            
            # Mark file as in progress
            state.mark_file_in_progress(file_node.full_path, file_node.size, 512)
            
            # Simulate successful download
            target_file = Path(temp_dir) / file_node.name
            target_file.write_bytes(b"x" * 1024)
            
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                
                result = download_manager.download_file(file_node, "https://example.com/file.txt")
                
                if result.success:
                    state.mark_file_completed(file_node.full_path, file_node.size)
                
                # Verify state was updated
                completed = state.get_completed_files()
                assert file_node.full_path in completed

    @responses.activate  
    def test_putio_client_error_handling_integration(self):
        """Test Put.io client error handling with scanner"""
        # Mock API error
        responses.add(
            responses.GET,
            "https://api.put.io/v2/files/list",
            json={"error": "Server error"},
            status=500
        )
        
        # After retry, return successful response
        responses.add(
            responses.GET,
            "https://api.put.io/v2/files/list",
            json={"files": [], "parent": {"id": 0}},
            status=200
        )
        
        client = PutioClient("test_token", retry_limit=1)
        scanner = FileScanner(client)
        
        # Should successfully scan after retry
        file_tree = scanner.scan_account()
        assert file_tree.name == "root"
        assert len(file_tree.children) == 0

    def test_file_filtering_integration(self):
        """Test file filtering across scanner and config"""
        mock_client = MagicMock()
        mock_client.list_files.return_value = {
            "files": [
                {"id": 1, "name": "video.mp4", "file_type": "VIDEO", "size": 1024, "parent_id": 0},
                {"id": 2, "name": "archive.zip", "file_type": "ARCHIVE", "size": 2048, "parent_id": 0},
                {"id": 3, "name": "document.txt", "file_type": "TEXT", "size": 512, "parent_id": 0},
                {"id": 4, "name": "huge_file.mkv", "file_type": "VIDEO", "size": 5 * 1024 * 1024 * 1024, "parent_id": 0}  # 5GB
            ],
            "parent": {"id": 0}
        }
        
        # Test with filters
        filters = {
            "allowed_extensions": ["mp4", "txt"],
            "max_file_size_gb": 2  # 2GB limit
        }
        
        scanner = FileScanner(mock_client, file_filters=filters)
        file_tree = scanner.scan_account()
        all_files = scanner.get_all_files()
        
        # Should only include mp4 and txt files under 2GB
        assert len(all_files) == 2
        file_names = [f.name for f in all_files]
        assert "video.mp4" in file_names
        assert "document.txt" in file_names
        assert "archive.zip" not in file_names  # Wrong extension
        assert "huge_file.mkv" not in file_names  # Too large

    def test_resumable_download_integration(self):
        """Test resumable download workflow with state management"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Setup state and download manager
            state_file = os.path.join(temp_dir, "resume_test_state.json")
            state = StateManager(state_file)
            download_manager = DownloadManager(destination_path=temp_dir)
            
            from putio_migrator.file_scanner import FileTreeNode
            file_node = FileTreeNode(
                name="large_file.txt",
                file_id=456,
                size=2048,
                is_folder=False,
                parent_id=0,
                full_path="large_file.txt"
            )
            
            # Simulate partial download
            partial_file = Path(temp_dir) / file_node.name
            partial_file.write_bytes(b"x" * 1024)  # Half downloaded
            
            # Mark as in progress
            state.mark_file_in_progress(file_node.full_path, file_node.size, 1024)
            state.save_state()
            
            # Verify partial download size is tracked
            partial_size = download_manager.get_partial_download_size(partial_file)
            assert partial_size == 1024
            
            # Complete the download by extending the file to full size
            with open(partial_file, 'ab') as f:
                f.write(b"y" * 1024)  # Complete file to 2048 bytes
            
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                
                result = download_manager.download_file(file_node, "https://example.com/file.txt")
                
                if result.success:
                    state.mark_file_completed(file_node.full_path, file_node.size)
                
                # Verify completion
                completed = state.get_completed_files()
                assert file_node.full_path in completed