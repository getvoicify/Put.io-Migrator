"""State management for Put.io to NAS migration tool."""

import json
import signal
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict


@dataclass
class FileState:
    """Represents the state of a single file in the migration."""
    file_path: str
    total_bytes: int
    downloaded_bytes: int = 0
    status: str = "pending"  # pending, in_progress, completed, failed
    error_message: Optional[str] = None
    retry_count: int = 0
    last_updated: Optional[str] = None
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.now().isoformat()


@dataclass
class MigrationState:
    """Complete migration state container."""
    files: Dict[str, FileState]
    scan_completed: bool = False
    total_files_discovered: int = 0
    total_bytes_discovered: int = 0
    migration_start_time: Optional[str] = None
    last_scan_time: Optional[str] = None
    
    def __post_init__(self):
        if self.migration_start_time is None:
            self.migration_start_time = datetime.now().isoformat()


class StateManager:
    """Manages persistent state for migration progress."""
    
    def __init__(self, state_file_path: str, auto_save_interval: int = 30):
        """Initialize state manager.
        
        Args:
            state_file_path: Path to JSON state file
            auto_save_interval: Seconds between auto-saves
        """
        self.state_file_path = Path(state_file_path)
        self.auto_save_interval = auto_save_interval
        self.last_save_time = time.time()
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self._load_state()
    
    def _load_state(self):
        """Load state from file or initialize empty state."""
        if self.state_file_path.exists():
            try:
                with open(self.state_file_path, 'r') as f:
                    data = json.load(f)
                
                # Convert dict data back to FileState objects
                files = {}
                for file_path, file_data in data.get('files', {}).items():
                    files[file_path] = FileState(**file_data)
                
                self.state = MigrationState(
                    files=files,
                    scan_completed=data.get('scan_completed', False),
                    total_files_discovered=data.get('total_files_discovered', 0),
                    total_bytes_discovered=data.get('total_bytes_discovered', 0),
                    migration_start_time=data.get('migration_start_time'),
                    last_scan_time=data.get('last_scan_time')
                )
            except (json.JSONDecodeError, KeyError, TypeError):
                # Handle corrupted state file by starting fresh
                self._initialize_empty_state()
        else:
            self._initialize_empty_state()
    
    def _initialize_empty_state(self):
        """Initialize empty migration state."""
        self.state = MigrationState(files={})
    
    def save_state(self):
        """Save current state to file."""
        # Convert FileState objects to dicts for JSON serialization
        files_dict = {}
        for file_path, file_state in self.state.files.items():
            files_dict[file_path] = asdict(file_state)
        
        state_dict = {
            'files': files_dict,
            'scan_completed': self.state.scan_completed,
            'total_files_discovered': self.state.total_files_discovered,
            'total_bytes_discovered': self.state.total_bytes_discovered,
            'migration_start_time': self.state.migration_start_time,
            'last_scan_time': self.state.last_scan_time
        }
        
        # Write to temp file first, then rename for atomic operation
        temp_file = self.state_file_path.with_suffix('.tmp')
        with open(temp_file, 'w') as f:
            json.dump(state_dict, f, indent=2)
        
        temp_file.rename(self.state_file_path)
        self.last_save_time = time.time()
    
    def maybe_auto_save(self):
        """Save state if enough time has passed since last save."""
        if time.time() - self.last_save_time >= self.auto_save_interval:
            self.save_state()
    
    def mark_file_completed(self, file_path: str, total_bytes: int):
        """Mark a file as successfully completed."""
        self.state.files[file_path] = FileState(
            file_path=file_path,
            total_bytes=total_bytes,
            downloaded_bytes=total_bytes,
            status="completed"
        )
    
    def mark_file_failed(self, file_path: str, error_message: str):
        """Mark a file as failed with error information."""
        if file_path in self.state.files:
            file_state = self.state.files[file_path]
            file_state.status = "failed"
            file_state.error_message = error_message
            file_state.retry_count += 1
            file_state.last_updated = datetime.now().isoformat()
        else:
            self.state.files[file_path] = FileState(
                file_path=file_path,
                total_bytes=0,
                status="failed",
                error_message=error_message,
                retry_count=1
            )
    
    def mark_file_in_progress(self, file_path: str, total_bytes: int, downloaded_bytes: int = 0):
        """Mark a file as currently being downloaded."""
        self.state.files[file_path] = FileState(
            file_path=file_path,
            total_bytes=total_bytes,
            downloaded_bytes=downloaded_bytes,
            status="in_progress"
        )
    
    def get_completed_files(self) -> Dict[str, FileState]:
        """Get all files that have been completed."""
        return {k: v for k, v in self.state.files.items() if v.status == "completed"}
    
    def get_failed_files(self) -> Dict[str, FileState]:
        """Get all files that have failed."""
        return {k: v for k, v in self.state.files.items() if v.status == "failed"}
    
    def get_in_progress_files(self) -> Dict[str, FileState]:
        """Get all files currently in progress."""
        return {k: v for k, v in self.state.files.items() if v.status == "in_progress"}
    
    def is_file_completed(self, file_path: str) -> bool:
        """Check if a file has been completed."""
        return (file_path in self.state.files and 
                self.state.files[file_path].status == "completed")
    
    def get_file_state(self, file_path: str) -> Optional[FileState]:
        """Get the state of a specific file."""
        return self.state.files.get(file_path)
    
    def _signal_handler(self, signum: int, frame):
        """Handle signals for graceful shutdown."""
        print(f"\nReceived signal {signum}. Saving state and shutting down gracefully...")
        self.save_state()
        exit(0)