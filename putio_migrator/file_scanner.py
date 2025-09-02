"""File scanning and tree building for Put.io accounts."""

import logging
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass

from .putio_client import PutioClient, PutioAPIError


@dataclass
class ScanProgress:
    """Progress information during account scanning."""
    folders_scanned: int = 0
    files_discovered: int = 0
    total_bytes_discovered: int = 0
    current_folder: str = ""


@dataclass
class FileTreeNode:
    """Represents a file or folder in the Put.io file tree."""
    name: str
    file_id: int
    size: int
    is_folder: bool
    parent_id: int
    full_path: str = ""
    children: List['FileTreeNode'] = None
    
    def __post_init__(self):
        if self.children is None:
            self.children = []


class FileScanner:
    """Scans Put.io account and builds complete file tree."""
    
    def __init__(self, putio_client: PutioClient, file_filters: Optional[Dict[str, Any]] = None):
        """Initialize file scanner.
        
        Args:
            putio_client: Put.io API client
            file_filters: Optional filters for files (extensions, size limits, etc.)
        """
        self.client = putio_client
        self.file_filters = file_filters or {}
        self.logger = logging.getLogger(__name__)
        self._total_size = 0
        self._all_files = []
    
    def scan_account(self, progress_callback: Optional[Callable[[ScanProgress], None]] = None) -> FileTreeNode:
        """Scan entire Put.io account and build file tree.
        
        Args:
            progress_callback: Optional callback for progress updates
            
        Returns:
            Root node of the complete file tree
        """
        self.logger.info("Starting Put.io account scan...")
        self._total_size = 0
        self._all_files = []
        
        progress = ScanProgress()
        root_node = FileTreeNode(
            name="root",
            file_id=0,
            size=0,
            is_folder=True,
            parent_id=-1,
            full_path=""
        )
        
        self._scan_folder_recursive(root_node, progress, progress_callback)
        
        self.logger.info(f"Scan completed: {progress.files_discovered} files, "
                        f"{progress.folders_scanned} folders, "
                        f"{progress.total_bytes_discovered} bytes total")
        
        return root_node
    
    def _scan_folder_recursive(self, folder_node: FileTreeNode, progress: ScanProgress,
                              progress_callback: Optional[Callable[[ScanProgress], None]]):
        """Recursively scan a folder and its subfolders.
        
        Args:
            folder_node: Folder node to scan
            progress: Progress tracking object
            progress_callback: Optional progress callback
        """
        try:
            progress.current_folder = folder_node.full_path or "/"
            progress.folders_scanned += 1
            
            if progress_callback:
                progress_callback(progress)
            
            # Get files in this folder
            response = self.client.list_files(folder_node.file_id)
            files = response.get("files", [])
            
            for file_data in files:
                if self._should_include_file(file_data):
                    # Build full path
                    if folder_node.full_path:
                        full_path = f"{folder_node.full_path}/{file_data['name']}"
                    else:
                        full_path = file_data['name']
                    
                    # Create node
                    node = FileTreeNode(
                        name=file_data['name'],
                        file_id=file_data['id'],
                        size=file_data['size'],
                        is_folder=(file_data['file_type'] == 'FOLDER'),
                        parent_id=folder_node.file_id,
                        full_path=full_path
                    )
                    
                    folder_node.children.append(node)
                    
                    if node.is_folder:
                        # Recursively scan subfolder
                        self._scan_folder_recursive(node, progress, progress_callback)
                    else:
                        # Track file statistics
                        progress.files_discovered += 1
                        progress.total_bytes_discovered += node.size
                        self._total_size += node.size
                        self._all_files.append(node)
                        
                        if progress_callback:
                            progress_callback(progress)
        
        except Exception as e:
            self.logger.warning(f"Error scanning folder {folder_node.full_path}: {str(e)}")
            # Continue scanning other folders even if one fails
    
    def _should_include_file(self, file_data: Dict[str, Any]) -> bool:
        """Check if file should be included based on filters.
        
        Args:
            file_data: File data from Put.io API
            
        Returns:
            True if file should be included
        """
        # Always include folders for structure
        if file_data['file_type'] == 'FOLDER':
            return True
        
        file_name = file_data['name']
        file_size = file_data['size']
        
        # Check file extension filters
        allowed_extensions = self.file_filters.get('allowed_extensions')
        if allowed_extensions:
            file_ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
            if file_ext not in [ext.lower() for ext in allowed_extensions]:
                return False
        
        blocked_extensions = self.file_filters.get('blocked_extensions')
        if blocked_extensions:
            file_ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
            if file_ext in [ext.lower() for ext in blocked_extensions]:
                return False
        
        # Check file size limits
        max_size_gb = self.file_filters.get('max_file_size_gb')
        if max_size_gb is not None:
            max_size_bytes = max_size_gb * 1024 * 1024 * 1024
            if file_size > max_size_bytes:
                return False
        
        return True
    
    def get_total_size(self) -> int:
        """Get total size of all discovered files in bytes."""
        return self._total_size
    
    def get_all_files(self) -> List[FileTreeNode]:
        """Get flat list of all files (excluding folders)."""
        return self._all_files.copy()
    
    def get_file_count(self) -> int:
        """Get total number of files discovered."""
        return len(self._all_files)
    
    def print_tree(self, node: Optional[FileTreeNode] = None, indent: int = 0):
        """Print file tree structure for debugging.
        
        Args:
            node: Node to print (uses last scanned tree if None)
            indent: Current indentation level
        """
        if node is None:
            return
        
        prefix = "  " * indent
        size_str = f" ({node.size} bytes)" if not node.is_folder else ""
        folder_marker = "/" if node.is_folder else ""
        
        print(f"{prefix}{node.name}{folder_marker}{size_str}")
        
        for child in node.children:
            self.print_tree(child, indent + 1)