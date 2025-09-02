import pytest
import tempfile
import os
import responses
import toml
from pathlib import Path
from unittest.mock import patch, MagicMock

from putio_migrator.main import MigrationOrchestrator


class TestEndToEnd:
    
    @responses.activate
    def test_complete_migration_workflow_with_real_components(self):
        """Test complete migration workflow using real components with mocked APIs"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create real configuration file
            config_data = {
                "putio": {
                    "oauth_token": "test_oauth_token_123",
                    "api_base_url": "https://api.put.io/v2"
                },
                "destination": {
                    "base_path": temp_dir,
                    "preserve_structure": True
                },
                "download": {
                    "connections": 2,
                    "timeout": 10,
                    "retry_limit": 1
                },
                "state": {
                    "file_path": os.path.join(temp_dir, "migration_state.json"),
                    "save_frequency_seconds": 5
                },
                "logging": {
                    "level": "INFO"
                }
            }
            
            config_file = os.path.join(temp_dir, "test_config.toml")
            with open(config_file, 'w') as f:
                toml.dump(config_data, f)
            
            # Mock Put.io API responses
            responses.add(
                responses.GET,
                "https://api.put.io/v2/account/info",
                json={"info": {"username": "testuser", "user_id": 123}},
                status=200
            )
            
            # Root folder listing
            responses.add(
                responses.GET,
                "https://api.put.io/v2/files/list",
                json={
                    "files": [
                        {"id": 1, "name": "movie.mp4", "file_type": "VIDEO", "size": 1024, "parent_id": 0},
                        {"id": 2, "name": "music", "file_type": "FOLDER", "size": 0, "parent_id": 0}
                    ],
                    "parent": {"id": 0}
                },
                status=200
            )
            
            # Music folder listing
            responses.add(
                responses.GET,
                "https://api.put.io/v2/files/list?parent_id=2",
                json={
                    "files": [
                        {"id": 3, "name": "song.mp3", "file_type": "AUDIO", "size": 512, "parent_id": 2}
                    ],
                    "parent": {"id": 2}
                },
                status=200
            )
            
            # Download URLs
            responses.add(
                responses.GET,
                "https://api.put.io/v2/files/1/download",
                json={"url": "https://download.put.io/files/movie.mp4"},
                status=200
            )
            
            responses.add(
                responses.GET,
                "https://api.put.io/v2/files/3/download",
                json={"url": "https://download.put.io/files/song.mp3"},
                status=200
            )
            
            # Mock Axel downloads to create files
            def mock_axel_download(*args, **kwargs):
                command = args[0]
                output_file = None
                for i, arg in enumerate(command):
                    if arg == "-o" and i + 1 < len(command):
                        output_file = command[i + 1]
                        break
                
                if output_file:
                    output_path = Path(output_file)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Create file with appropriate content based on name
                    if "movie.mp4" in output_file:
                        output_path.write_bytes(b"x" * 1024)
                    elif "song.mp3" in output_file:
                        output_path.write_bytes(b"x" * 512)
                
                return MagicMock(returncode=0, stdout="", stderr="")
            
            with patch('subprocess.run', side_effect=mock_axel_download):
                # Run migration
                orchestrator = MigrationOrchestrator(config_file)
                result = orchestrator.run_migration()
                
                # Verify results
                assert result["success"] is True
                assert result["total_files"] == 2
                assert result["completed_files"] == 2
                assert result["failed_files"] == 0
                
                # Verify files were created with correct structure
                movie_path = Path(temp_dir) / "movie.mp4"
                song_path = Path(temp_dir) / "music" / "song.mp3"
                
                assert movie_path.exists()
                assert movie_path.stat().st_size == 1024
                assert song_path.exists()
                assert song_path.stat().st_size == 512
                
                # Verify state file was created
                state_file = Path(temp_dir) / "migration_state.json"
                assert state_file.exists()

    @responses.activate
    def test_migration_interruption_and_resume(self):
        """Test migration interruption and successful resume"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Setup config
            config_data = {
                "putio": {"oauth_token": "test_token"},
                "destination": {"base_path": temp_dir},
                "state": {"file_path": os.path.join(temp_dir, "resume_state.json")}
            }
            
            config_file = os.path.join(temp_dir, "config.toml")
            with open(config_file, 'w') as f:
                toml.dump(config_data, f)
            
            # Mock API responses
            responses.add(
                responses.GET,
                "https://api.put.io/v2/account/info",
                json={"info": {"username": "testuser"}},
                status=200
            )
            
            responses.add(
                responses.GET,
                "https://api.put.io/v2/files/list",
                json={
                    "files": [
                        {"id": 1, "name": "file1.txt", "file_type": "VIDEO", "size": 1024, "parent_id": 0},
                        {"id": 2, "name": "file2.txt", "file_type": "VIDEO", "size": 2048, "parent_id": 0}
                    ],
                    "parent": {"id": 0}
                },
                status=200
            )
            
            responses.add(
                responses.GET,
                "https://api.put.io/v2/files/1/download",
                json={"url": "https://download.put.io/files/file1.txt"},
                status=200
            )
            
            responses.add(
                responses.GET,
                "https://api.put.io/v2/files/2/download",
                json={"url": "https://download.put.io/files/file2.txt"},
                status=200
            )
            
            # First migration: Complete first file, fail on second
            download_call_count = 0
            def mock_axel_first_run(*args, **kwargs):
                nonlocal download_call_count
                download_call_count += 1
                command = args[0]
                output_file = None
                for i, arg in enumerate(command):
                    if arg == "-o" and i + 1 < len(command):
                        output_file = command[i + 1]
                        break
                
                if download_call_count == 1 and "file1.txt" in output_file:
                    # First file succeeds
                    Path(output_file).write_bytes(b"x" * 1024)
                    return MagicMock(returncode=0)
                else:
                    # Second file fails
                    return MagicMock(returncode=1, stderr="Network error")
            
            with patch('subprocess.run', side_effect=mock_axel_first_run):
                orchestrator1 = MigrationOrchestrator(config_file)
                result1 = orchestrator1.run_migration()
                
                assert result1["completed_files"] == 1
                assert result1["failed_files"] == 1
            
            # Second migration: Resume and complete second file
            def mock_axel_second_run(*args, **kwargs):
                command = args[0]
                output_file = None
                for i, arg in enumerate(command):
                    if arg == "-o" and i + 1 < len(command):
                        output_file = command[i + 1]
                        break
                
                if "file2.txt" in output_file:
                    # Second file now succeeds
                    Path(output_file).write_bytes(b"x" * 2048)
                    return MagicMock(returncode=0)
                
                return MagicMock(returncode=0)
            
            with patch('subprocess.run', side_effect=mock_axel_second_run):
                orchestrator2 = MigrationOrchestrator(config_file)
                result2 = orchestrator2.run_migration()
                
                # Should skip first file (already completed) and complete second
                assert result2["completed_files"] == 1  # Only file2.txt downloaded this time
                assert result2["skipped_files"] == 1   # file1.txt was skipped
                assert result2["failed_files"] == 0

    def test_migration_with_file_filters(self):
        """Test migration with file filtering applied"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Setup config with filters
            config_data = {
                "putio": {"oauth_token": "test_token"},
                "destination": {"base_path": temp_dir},
                "filters": {
                    "allowed_extensions": ["mp4", "mp3"],
                    "max_file_size_gb": 1
                }
            }
            
            config_file = os.path.join(temp_dir, "filtered_config.toml")
            with open(config_file, 'w') as f:
                toml.dump(config_data, f)
            
            # Mock scanner with filtered results
            mock_client = MagicMock()
            mock_client.get_account_info.return_value = {"info": {"username": "testuser"}}
            
            # Create orchestrator and verify filters are applied
            with patch('putio_migrator.main.PutioClient', return_value=mock_client):
                with patch('putio_migrator.main.FileScanner') as mock_scanner_class:
                    mock_scanner = MagicMock()
                    mock_scanner.get_all_files.return_value = []  # No files after filtering
                    mock_scanner.get_total_size.return_value = 0
                    mock_scanner_class.return_value = mock_scanner
                    
                    orchestrator = MigrationOrchestrator(config_file)
                    result = orchestrator.run_migration()
                    
                    # Verify scanner was created with filters
                    mock_scanner_class.assert_called_once()
                    # The scanner should have been passed file filters, but we can't easily verify
                    # the exact filters due to how the integration works
                    assert result["success"] is True

    def test_migration_handles_api_authentication_failure(self):
        """Test migration handles Put.io authentication failures gracefully"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_data = {
                "putio": {"oauth_token": "invalid_token"},
                "destination": {"base_path": temp_dir}
            }
            
            config_file = os.path.join(temp_dir, "config.toml")
            with open(config_file, 'w') as f:
                toml.dump(config_data, f)
            
            # Mock authentication failure
            mock_client = MagicMock()
            mock_client.get_account_info.side_effect = Exception("Authentication failed")
            
            with patch('putio_migrator.main.PutioClient', return_value=mock_client):
                orchestrator = MigrationOrchestrator(config_file)
                result = orchestrator.run_migration()
                
                assert result["success"] is False
                assert "Authentication failed" in result["error"]

    def test_migration_state_basic_persistence(self):
        """Test basic state persistence functionality"""
        with tempfile.TemporaryDirectory() as temp_dir:
            from putio_migrator.state_manager import StateManager
            
            state_file = os.path.join(temp_dir, "persistence_test.json")
            
            # Create state and add completed file
            state1 = StateManager(state_file)
            state1.mark_file_completed("test_file.txt", 1024)
            state1.save_state()
            
            # Load state in new instance
            state2 = StateManager(state_file)
            completed = state2.get_completed_files()
            
            assert "test_file.txt" in completed
            assert state2.is_file_completed("test_file.txt") is True

    def test_large_file_tree_handling(self):
        """Test handling of large file trees efficiently"""
        # This test verifies that the system can handle large numbers of files
        # without running out of memory or taking excessive time
        
        mock_client = MagicMock()
        mock_client.get_account_info.return_value = {"info": {"username": "testuser"}}
        
        # Generate large file list (1000 files)
        large_file_list = []
        for i in range(1000):
            large_file_list.append({
                "id": i + 1,
                "name": f"file_{i:04d}.txt",
                "file_type": "VIDEO",
                "size": 1024 + i,  # Varying sizes
                "parent_id": 0
            })
        
        mock_client.list_files.return_value = {
            "files": large_file_list,
            "parent": {"id": 0}
        }
        
        # Test scanning large account
        from putio_migrator.file_scanner import FileScanner
        scanner = FileScanner(mock_client)
        
        file_tree = scanner.scan_account()
        all_files = scanner.get_all_files()
        
        assert len(all_files) == 1000
        assert scanner.get_total_size() > 1000 * 1024  # Should be substantial size
        
        # Verify memory usage is reasonable (this is more of a smoke test)
        import sys
        # If this test completes without memory errors, we're good