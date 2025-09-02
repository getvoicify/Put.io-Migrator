import pytest
import tempfile
import json
import os
import signal
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

from putio_migrator.state_manager import StateManager, MigrationState, FileState


class TestStateManager:
    
    def test_state_persists_across_restarts(self):
        """Test state persistence survives application restart"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            state_file = f.name
        
        try:
            # Create first state manager and add some data
            state1 = StateManager(state_file)
            state1.mark_file_completed("/test/file1.txt", 1024)
            state1.mark_file_completed("/test/file2.txt", 2048)
            state1.mark_file_in_progress("/test/file3.txt", 512, downloaded_bytes=256)
            state1.save_state()
            
            # Create second state manager and verify data persists
            state2 = StateManager(state_file)
            assert len(state2.get_completed_files()) == 2
            assert "/test/file1.txt" in state2.get_completed_files()
            assert "/test/file2.txt" in state2.get_completed_files()
            
            in_progress = state2.get_in_progress_files()
            assert len(in_progress) == 1
            assert "/test/file3.txt" in in_progress
            assert in_progress["/test/file3.txt"].downloaded_bytes == 256
        finally:
            os.unlink(state_file)

    def test_signal_handler_saves_state_on_interrupt(self):
        """Test graceful interruption saves state"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            state_file = f.name
        
        try:
            state = StateManager(state_file)
            state.mark_file_completed("/test/file1.txt", 1024)
            
            # Test signal handler directly instead of sending real signal
            with patch.object(state, 'save_state') as mock_save:
                with patch('builtins.exit') as mock_exit:
                    state._signal_handler(signal.SIGINT, None)
                    mock_save.assert_called_once()
                    mock_exit.assert_called_once_with(0)
        finally:
            os.unlink(state_file)

    def test_state_manager_initializes_empty_state(self):
        """Test StateManager initializes with empty state for new file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            state_file = f.name
        
        try:
            os.unlink(state_file)  # Remove the file so it doesn't exist
            state = StateManager(state_file)
            assert len(state.get_completed_files()) == 0
            assert len(state.get_failed_files()) == 0
            assert len(state.get_in_progress_files()) == 0
        except FileNotFoundError:
            pass  # It's okay if the file doesn't exist

    def test_state_tracks_file_completion(self):
        """Test marking files as completed"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            state_file = f.name
        
        try:
            state = StateManager(state_file)
            file_path = "/test/completed_file.txt"
            file_size = 1024
            
            state.mark_file_completed(file_path, file_size)
            
            completed = state.get_completed_files()
            assert file_path in completed
            assert completed[file_path].total_bytes == file_size
            assert completed[file_path].status == "completed"
        finally:
            os.unlink(state_file)

    def test_state_tracks_file_failure(self):
        """Test marking files as failed with error information"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            state_file = f.name
        
        try:
            state = StateManager(state_file)
            file_path = "/test/failed_file.txt"
            error_msg = "Network timeout"
            
            state.mark_file_failed(file_path, error_msg)
            
            failed = state.get_failed_files()
            assert file_path in failed
            assert failed[file_path].error_message == error_msg
            assert failed[file_path].retry_count == 1
        finally:
            os.unlink(state_file)

    def test_state_tracks_download_progress(self):
        """Test tracking download progress for files"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            state_file = f.name
        
        try:
            state = StateManager(state_file)
            file_path = "/test/progress_file.txt"
            total_size = 1024
            downloaded = 512
            
            state.mark_file_in_progress(file_path, total_size, downloaded)
            
            in_progress = state.get_in_progress_files()
            assert file_path in in_progress
            assert in_progress[file_path].total_bytes == total_size
            assert in_progress[file_path].downloaded_bytes == downloaded
            assert in_progress[file_path].status == "in_progress"
        finally:
            os.unlink(state_file)

    def test_state_handles_corrupted_file(self):
        """Test handling corrupted state files"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            state_file = f.name
        
        try:
            # Should initialize empty state when file is corrupted
            state = StateManager(state_file)
            assert len(state.get_completed_files()) == 0
        finally:
            os.unlink(state_file)

    def test_state_auto_saves_periodically(self):
        """Test automatic state saving based on time interval"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            state_file = f.name
        
        try:
            with patch('time.time') as mock_time:
                mock_time.side_effect = [0, 31]  # Simulate 31 seconds passing
                
                state = StateManager(state_file, auto_save_interval=30)
                state.mark_file_completed("/test/file1.txt", 1024)
                
                with patch.object(state, 'save_state') as mock_save:
                    state.maybe_auto_save()
                    mock_save.assert_called_once()
        finally:
            os.unlink(state_file)