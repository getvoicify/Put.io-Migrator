"""Download management with Axel integration and fallback support."""

import logging
import subprocess
import requests
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from .file_scanner import FileTreeNode


class DownloadError(Exception):
    """Raised when download fails."""
    pass


@dataclass
class DownloadResult:
    """Result of a download operation."""
    success: bool
    file_path: str
    error_message: Optional[str] = None
    already_existed: bool = False
    used_fallback: bool = False
    bytes_downloaded: int = 0


class DownloadManager:
    """Manages file downloads using Axel with fallback to requests."""
    
    def __init__(self, destination_path: str, connections: int = 4, timeout: int = 30,
                 preserve_structure: bool = True, use_fallback: bool = True):
        """Initialize download manager.
        
        Args:
            destination_path: Base destination directory
            connections: Number of connections for Axel
            timeout: Download timeout in seconds
            preserve_structure: Whether to preserve folder structure
            use_fallback: Whether to use requests fallback if Axel fails
        """
        self.destination_path = Path(destination_path)
        self.connections = connections
        self.timeout = timeout
        self.preserve_structure = preserve_structure
        self.use_fallback = use_fallback
        self.logger = logging.getLogger(__name__)
    
    def download_file(self, file_node: FileTreeNode, download_url: str) -> DownloadResult:
        """Download a file using Axel or fallback method.
        
        Args:
            file_node: File node containing metadata
            download_url: Direct download URL from Put.io
            
        Returns:
            DownloadResult with operation details
        """
        # Determine target file path
        if self.preserve_structure and file_node.full_path:
            target_path = self.destination_path / file_node.full_path
        else:
            target_path = self.destination_path / file_node.name
        
        # Create directory structure if needed
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if file already exists and is complete
        if target_path.exists() and target_path.stat().st_size == file_node.size:
            self.logger.info(f"File already exists and is complete: {target_path}")
            return DownloadResult(
                success=True,
                file_path=str(target_path),
                already_existed=True
            )
        
        # Try downloading with Axel first
        try:
            return self._download_with_axel(file_node, download_url, target_path)
        except (FileNotFoundError, DownloadError) as e:
            if self.use_fallback:
                self.logger.warning(f"Axel failed ({str(e)}), trying fallback method")
                return self._download_with_requests(file_node, download_url, target_path)
            else:
                raise DownloadError(f"Axel download failed and fallback disabled: {str(e)}")
    
    def _download_with_axel(self, file_node: FileTreeNode, download_url: str, 
                           target_path: Path) -> DownloadResult:
        """Download file using Axel.
        
        Args:
            file_node: File node metadata
            download_url: Download URL
            target_path: Target file path
            
        Returns:
            DownloadResult
            
        Raises:
            DownloadError: If download fails
        """
        command = [
            "axel",
            "-n", str(self.connections),
            "-T", str(self.timeout),
            "-o", str(target_path)
        ]
        
        # Add resume option if partial file exists
        if target_path.exists():
            command.append("-c")
        
        command.append(download_url)
        
        try:
            self.logger.info(f"Starting Axel download: {file_node.name}")
            self.logger.debug(f"Axel command: {' '.join(command)}")
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout + 5  # Add buffer for process overhead
            )
            self.logger.debug(f"Axel completed with return code: {result.returncode}")
            
            if result.returncode != 0:
                error_msg = f"Axel download failed (code {result.returncode}): {result.stderr}"
                raise DownloadError(error_msg)
            
            # Verify file integrity
            if not target_path.exists():
                raise DownloadError("Downloaded file does not exist")
            
            actual_size = target_path.stat().st_size
            if actual_size != file_node.size:
                raise DownloadError(
                    f"File size mismatch: expected {file_node.size}, got {actual_size}"
                )
            
            self.logger.info(f"Successfully downloaded: {file_node.name}")
            return DownloadResult(
                success=True,
                file_path=str(target_path),
                bytes_downloaded=actual_size
            )
            
        except subprocess.TimeoutExpired:
            raise DownloadError(f"Download timeout after {self.timeout} seconds")
        except FileNotFoundError:
            raise DownloadError("Axel command not found")
    
    def _download_with_requests(self, file_node: FileTreeNode, download_url: str,
                               target_path: Path) -> DownloadResult:
        """Download file using requests as fallback.
        
        Args:
            file_node: File node metadata
            download_url: Download URL
            target_path: Target file path
            
        Returns:
            DownloadResult
        """
        try:
            self.logger.info(f"Starting fallback download: {file_node.name}")
            
            with requests.get(download_url, stream=True, timeout=self.timeout) as response:
                response.raise_for_status()
                
                with open(target_path, 'wb') as f:
                    bytes_downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            bytes_downloaded += len(chunk)
            
            # Verify file integrity
            if not target_path.exists():
                raise DownloadError("Downloaded file does not exist")
            
            actual_size = target_path.stat().st_size
            if actual_size != file_node.size:
                raise DownloadError(
                    f"File size mismatch: expected {file_node.size}, got {actual_size}"
                )
            
            self.logger.info(f"Successfully downloaded with fallback: {file_node.name}")
            return DownloadResult(
                success=True,
                file_path=str(target_path),
                used_fallback=True,
                bytes_downloaded=actual_size
            )
            
        except requests.exceptions.RequestException as e:
            raise DownloadError(f"Fallback download failed: {str(e)}")
    
    def get_partial_download_size(self, file_path: Path) -> int:
        """Get size of partially downloaded file.
        
        Args:
            file_path: Path to check
            
        Returns:
            Size in bytes, or 0 if file doesn't exist
        """
        if file_path.exists():
            return file_path.stat().st_size
        return 0