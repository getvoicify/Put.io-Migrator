import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from typing import List, Dict, Any

from putio_migrator.file_scanner import FileScanner, FileTreeNode, ScanProgress
from putio_migrator.putio_client import PutioClient


class TestFileScanner:
    
    def test_scanner_builds_complete_tree(self):
        """Test building complete file tree from put.io account"""
        # Mock put.io client responses
        mock_client = MagicMock(spec=PutioClient)
        
        # Root folder contains one file and one subfolder
        mock_client.list_files.side_effect = [
            {
                "files": [
                    {"id": 1, "name": "root_file.txt", "file_type": "VIDEO", "size": 1024, "parent_id": 0},
                    {"id": 2, "name": "subfolder", "file_type": "FOLDER", "size": 0, "parent_id": 0}
                ],
                "parent": {"id": 0}
            },
            # Subfolder contains one file
            {
                "files": [
                    {"id": 3, "name": "nested_file.txt", "file_type": "VIDEO", "size": 2048, "parent_id": 2}
                ],
                "parent": {"id": 2}
            }
        ]
        
        scanner = FileScanner(mock_client)
        tree = scanner.scan_account()
        
        # Verify tree structure
        assert tree.name == "root"
        assert tree.is_folder is True
        assert len(tree.children) == 2
        
        # Find the file and folder children
        root_file = next(child for child in tree.children if child.name == "root_file.txt")
        subfolder = next(child for child in tree.children if child.name == "subfolder")
        
        assert root_file.is_folder is False
        assert root_file.size == 1024
        assert root_file.file_id == 1
        
        assert subfolder.is_folder is True
        assert len(subfolder.children) == 1
        assert subfolder.children[0].name == "nested_file.txt"

    def test_scanner_handles_empty_account(self):
        """Test scanning empty put.io account"""
        mock_client = MagicMock(spec=PutioClient)
        mock_client.list_files.return_value = {
            "files": [],
            "parent": {"id": 0}
        }
        
        scanner = FileScanner(mock_client)
        tree = scanner.scan_account()
        
        assert tree.name == "root"
        assert tree.is_folder is True
        assert len(tree.children) == 0

    def test_scanner_tracks_progress(self):
        """Test progress tracking during scan"""
        mock_client = MagicMock(spec=PutioClient)
        mock_client.list_files.return_value = {
            "files": [
                {"id": 1, "name": "file1.txt", "file_type": "VIDEO", "size": 1024, "parent_id": 0},
                {"id": 2, "name": "file2.txt", "file_type": "VIDEO", "size": 2048, "parent_id": 0}
            ],
            "parent": {"id": 0}
        }
        
        scanner = FileScanner(mock_client)
        progress_updates = []
        
        def progress_callback(progress: ScanProgress):
            progress_updates.append(progress)
        
        scanner.scan_account(progress_callback=progress_callback)
        
        assert len(progress_updates) > 0
        final_progress = progress_updates[-1]
        assert final_progress.files_discovered == 2
        assert final_progress.total_bytes_discovered == 3072

    def test_scanner_applies_file_filters(self):
        """Test filtering files during scan"""
        mock_client = MagicMock(spec=PutioClient)
        mock_client.list_files.return_value = {
            "files": [
                {"id": 1, "name": "video.mp4", "file_type": "VIDEO", "size": 1024, "parent_id": 0},
                {"id": 2, "name": "archive.zip", "file_type": "ARCHIVE", "size": 2048, "parent_id": 0},
                {"id": 3, "name": "document.txt", "file_type": "TEXT", "size": 512, "parent_id": 0}
            ],
            "parent": {"id": 0}
        }
        
        # Filter to only include video files
        filters = {
            "allowed_extensions": ["mp4", "mkv"],
            "max_file_size_gb": 1
        }
        
        scanner = FileScanner(mock_client, file_filters=filters)
        tree = scanner.scan_account()
        
        # Should only include the mp4 file
        assert len(tree.children) == 1
        assert tree.children[0].name == "video.mp4"

    def test_scanner_handles_api_errors_gracefully(self):
        """Test handling API errors during scan"""
        mock_client = MagicMock(spec=PutioClient)
        
        # First call succeeds, second call (for subfolder) fails
        mock_client.list_files.side_effect = [
            {
                "files": [
                    {"id": 1, "name": "accessible_file.txt", "file_type": "VIDEO", "size": 1024, "parent_id": 0},
                    {"id": 2, "name": "inaccessible_folder", "file_type": "FOLDER", "size": 0, "parent_id": 0}
                ],
                "parent": {"id": 0}
            },
            Exception("API error accessing folder")
        ]
        
        scanner = FileScanner(mock_client)
        tree = scanner.scan_account()
        
        # Should still build partial tree with accessible content
        assert len(tree.children) == 2
        accessible_file = next(child for child in tree.children if child.name == "accessible_file.txt")
        inaccessible_folder = next(child for child in tree.children if child.name == "inaccessible_folder")
        
        assert accessible_file.is_folder is False
        assert inaccessible_folder.is_folder is True
        assert len(inaccessible_folder.children) == 0  # No children due to error

    def test_scanner_calculates_total_size(self):
        """Test calculation of total size for discovered files"""
        mock_client = MagicMock(spec=PutioClient)
        mock_client.list_files.return_value = {
            "files": [
                {"id": 1, "name": "file1.txt", "file_type": "VIDEO", "size": 1024, "parent_id": 0},
                {"id": 2, "name": "file2.txt", "file_type": "VIDEO", "size": 2048, "parent_id": 0},
                {"id": 3, "name": "file3.txt", "file_type": "VIDEO", "size": 512, "parent_id": 0}
            ],
            "parent": {"id": 0}
        }
        
        scanner = FileScanner(mock_client)
        tree = scanner.scan_account()
        
        total_size = scanner.get_total_size()
        assert total_size == 3584  # 1024 + 2048 + 512

    def test_scanner_gets_all_files_flat_list(self):
        """Test getting flat list of all files from tree"""
        mock_client = MagicMock(spec=PutioClient)
        mock_client.list_files.side_effect = [
            {
                "files": [
                    {"id": 1, "name": "root_file.txt", "file_type": "VIDEO", "size": 1024, "parent_id": 0},
                    {"id": 2, "name": "subfolder", "file_type": "FOLDER", "size": 0, "parent_id": 0}
                ],
                "parent": {"id": 0}
            },
            {
                "files": [
                    {"id": 3, "name": "nested_file.txt", "file_type": "VIDEO", "size": 2048, "parent_id": 2}
                ],
                "parent": {"id": 2}
            }
        ]
        
        scanner = FileScanner(mock_client)
        tree = scanner.scan_account()
        all_files = scanner.get_all_files()
        
        # Should return flat list of all files (not folders)
        assert len(all_files) == 2
        file_names = [f.name for f in all_files]
        assert "root_file.txt" in file_names
        assert "nested_file.txt" in file_names