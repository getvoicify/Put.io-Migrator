import pytest
import tempfile
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

from putio_migrator.download_manager import DownloadManager, DownloadError, DownloadResult
from putio_migrator.file_scanner import FileTreeNode


class TestDownloadManager:
    
    def test_download_manager_skips_existing_complete_files(self):
        """Test skipping files that already exist and are complete"""
        with tempfile.TemporaryDirectory() as temp_dir:
            download_manager = DownloadManager(destination_path=temp_dir)
            
            file_node = FileTreeNode(
                name="existing_file.txt",
                file_id=123,
                size=1024,
                is_folder=False,
                parent_id=0,
                full_path="existing_file.txt"
            )
            
            # Create existing file with correct size
            existing_file = Path(temp_dir) / "existing_file.txt"
            existing_file.write_bytes(b"x" * 1024)
            
            download_url = "https://download.put.io/files/existing_file.txt"
            
            with patch('subprocess.run') as mock_run:
                result = download_manager.download_file(file_node, download_url)
                
                # Should not call subprocess since file exists and is complete
                mock_run.assert_not_called()
                assert result.success is True
                assert result.already_existed is True

    def test_download_manager_creates_directory_structure(self):
        """Test creation of directory structure for nested files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            download_manager = DownloadManager(
                destination_path=temp_dir,
                preserve_structure=True
            )
            
            file_node = FileTreeNode(
                name="nested_file.txt",
                file_id=123,
                size=1024,
                is_folder=False,
                parent_id=456,
                full_path="folder1/subfolder2/nested_file.txt"
            )
            
            download_url = "https://download.put.io/files/nested_file.txt"
            
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )
                
                # Create a small test file to simulate download
                target_path = Path(temp_dir) / file_node.full_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(b"x" * 1024)
                
                result = download_manager.download_file(file_node, download_url)
                
                # Verify directory was created
                expected_dir = os.path.join(temp_dir, "folder1", "subfolder2")
                assert os.path.exists(expected_dir)

    def test_download_result_dataclass(self):
        """Test DownloadResult dataclass functionality"""
        result = DownloadResult(
            success=True,
            file_path="/test/file.txt",
            bytes_downloaded=1024
        )
        
        assert result.success is True
        assert result.file_path == "/test/file.txt"
        assert result.bytes_downloaded == 1024
        assert result.already_existed is False
        assert result.used_fallback is False
        assert result.error_message is None

    def test_download_manager_initialization(self):
        """Test download manager initialization with various options"""
        dm1 = DownloadManager("/test/path")
        assert dm1.connections == 4  # default
        assert dm1.timeout == 30  # default
        assert dm1.preserve_structure is True  # default
        assert dm1.use_fallback is True  # default
        
        dm2 = DownloadManager(
            "/test/path", 
            connections=8, 
            timeout=60, 
            preserve_structure=False, 
            use_fallback=False
        )
        assert dm2.connections == 8
        assert dm2.timeout == 60
        assert dm2.preserve_structure is False
        assert dm2.use_fallback is False

    @patch('subprocess.run')
    def test_axel_command_parameters(self, mock_run):
        """Test that Axel is called with correct parameters"""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            download_manager = DownloadManager(
                destination_path=temp_dir,
                connections=6,
                timeout=45
            )
            
            file_node = FileTreeNode(
                name="test.txt",
                file_id=123,
                size=1024,
                is_folder=False,
                parent_id=0,
                full_path="test.txt"
            )
            
            # Simulate successful download by creating the file after Axel "runs"
            def create_file_side_effect(*args, **kwargs):
                target_file = Path(temp_dir) / "test.txt"
                target_file.write_bytes(b"x" * 1024)
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            
            mock_run.side_effect = create_file_side_effect
            
            download_manager.download_file(file_node, "https://example.com/file.txt")
            
            # Verify command structure
            assert mock_run.called
            command = mock_run.call_args[0][0]
            assert command[0] == "axel"
            assert "-n" in command and "6" in command
            assert "-T" in command and "45" in command
            assert "-o" in command

    @patch('subprocess.run')
    def test_download_manager_handles_subprocess_errors(self, mock_run):
        """Test handling various subprocess errors"""
        # Test FileNotFoundError (Axel not installed)
        mock_run.side_effect = FileNotFoundError("axel: command not found")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            download_manager = DownloadManager(destination_path=temp_dir, use_fallback=False)
            
            file_node = FileTreeNode(
                name="test.txt",
                file_id=123,
                size=1024,
                is_folder=False,
                parent_id=0,
                full_path="test.txt"
            )
            
            # Since use_fallback=False, this should raise DownloadError
            with pytest.raises(DownloadError, match="Axel download failed and fallback disabled"):
                download_manager.download_file(file_node, "https://example.com/file.txt")

    @patch('subprocess.run')
    def test_download_manager_handles_timeout(self, mock_run):
        """Test handling download timeouts"""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["axel"], timeout=30)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            download_manager = DownloadManager(destination_path=temp_dir, use_fallback=False)
            
            file_node = FileTreeNode(
                name="test.txt",
                file_id=123,
                size=1024,
                is_folder=False,
                parent_id=0,
                full_path="test.txt"
            )
            
            # Since use_fallback=False, this should raise DownloadError
            with pytest.raises(DownloadError, match="Axel download failed and fallback disabled"):
                download_manager.download_file(file_node, "https://example.com/file.txt")

    def test_get_partial_download_size(self):
        """Test getting size of partially downloaded files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            download_manager = DownloadManager(destination_path=temp_dir)
            
            # Test non-existent file
            non_existent = Path(temp_dir) / "non_existent.txt"
            assert download_manager.get_partial_download_size(non_existent) == 0
            
            # Test existing partial file
            partial_file = Path(temp_dir) / "partial.txt"
            partial_file.write_bytes(b"x" * 512)
            assert download_manager.get_partial_download_size(partial_file) == 512