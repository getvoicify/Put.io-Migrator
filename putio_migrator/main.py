"""Main orchestration for Put.io to NAS migration tool."""

import sys
import argparse
import logging
from typing import Dict, Any, List

from .config_manager import ConfigManager
from .state_manager import StateManager
from .putio_client import PutioClient
from .file_scanner import FileScanner, ScanProgress
from .download_manager import DownloadManager


class MigrationOrchestrator:
    """Orchestrates the complete migration workflow."""
    
    def __init__(self, config_path: str):
        """Initialize migration orchestrator.
        
        Args:
            config_path: Path to TOML configuration file
        """
        self.config_path = config_path
        
        # Initialize components
        self.config = ConfigManager(config_path)
        self.state = StateManager(self.config.state_file_path, self.config.state_save_frequency)
        self.putio_client = PutioClient(
            self.config.putio_oauth_token,
            self.config.putio_api_base_url,
            self.config.download_retry_limit
        )
        
        # Setup logging
        logging.basicConfig(
            level=getattr(logging, self.config.logging_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    def _scan_files(self) -> Dict[str, Any]:
        """Scan Put.io account for files.
        
        Returns:
            Dict with tree, all_files, and total_size
        """
        # Verify Put.io authentication
        try:
            account_info = self.putio_client.get_account_info()
            self.logger.info(f"Authenticated as: {account_info['info']['username']}")
        except Exception as e:
            self.logger.error(f"Authentication failed: {str(e)}")
            raise Exception("Authentication failed")
        
        # Scan Put.io account for files
        self.logger.info("Scanning Put.io account...")
        scanner = FileScanner(self.putio_client)
        
        def progress_callback(progress: ScanProgress):
            if progress.files_discovered % 100 == 0:  # Report every 100 files
                print(f"Scanning... Found {progress.files_discovered} files, "
                      f"{progress.total_bytes_discovered // (1024*1024)} MB")
        
        file_tree = scanner.scan_account(progress_callback)
        all_files = scanner.get_all_files()
        total_size = scanner.get_total_size()
        
        self.logger.info(f"Scan complete: {len(all_files)} files, {total_size // (1024*1024)} MB total")
        
        return {
            "tree": file_tree,
            "all_files": all_files,
            "total_size": total_size
        }

    def run_migration(self) -> Dict[str, Any]:
        """Run the complete migration workflow.
        
        Returns:
            Dictionary with migration results and statistics
        """
        try:
            self.logger.info("Starting Put.io to NAS migration")
            
            # Scan files
            scan_result = self._scan_files()
            file_tree = scan_result["tree"]
            all_files = scan_result["all_files"]
            total_size = scan_result["total_size"]
            
            # Filter out already completed files
            pending_files = [f for f in all_files if not self.state.is_file_completed(f.full_path)]
            
            if not pending_files:
                self.logger.info("All files already downloaded")
                return {
                    "success": True,
                    "total_files": len(all_files),
                    "completed_files": len(all_files),
                    "failed_files": 0,
                    "skipped_files": 0
                }
            
            print(f"\nStarting download of {len(pending_files)} files...")
            if len(pending_files) > 10:
                print(f"This may take a while. You can interrupt with Ctrl+C to pause and resume later.")
            
            # Show first few files to be downloaded
            print(f"Next files to download:")
            for j, f in enumerate(pending_files[:5]):
                print(f"  {j+1}. {f.name} ({f.size / (1024*1024):.1f} MB)")
            if len(pending_files) > 5:
                print(f"  ... and {len(pending_files) - 5} more files")
            
            self.logger.info(f"Starting download of {len(pending_files)} files")
            
            # Initialize download manager
            download_manager = DownloadManager(
                destination_path=self.config.destination_base_path,
                connections=self.config.download_connections,
                timeout=self.config.download_timeout,
                preserve_structure=self.config.destination_preserve_structure
            )
            
            # Download files
            completed_files = 0
            failed_files = 0
            
            import time
            start_time = time.time()
            
            for i, file_node in enumerate(pending_files):
                try:
                    # Report progress
                    progress_pct = (i / len(pending_files)) * 100
                    elapsed = time.time() - start_time
                    print(f"Progress: {progress_pct:.1f}% - Downloading {file_node.name} (elapsed: {elapsed:.0f}s)")
                    
                    # Get download URL with timeout handling
                    print(f"  Getting download URL for {file_node.name}...")
                    try:
                        download_url = self.putio_client.get_download_url(file_node.file_id)
                        print(f"  Got download URL successfully")
                    except Exception as e:
                        print(f"  ✗ Failed to get download URL: {str(e)}")
                        self.state.mark_file_failed(file_node.full_path, f"Failed to get download URL: {str(e)}")
                        failed_files += 1
                        continue
                    
                    # Download file
                    print(f"  Starting download of {file_node.name} ({file_node.size / (1024*1024):.1f} MB)...")
                    result = download_manager.download_file(file_node, download_url)
                    
                    if result.success:
                        self.state.mark_file_completed(file_node.full_path, file_node.size)
                        completed_files += 1
                        print(f"  ✓ Completed: {file_node.name}")
                        self.logger.info(f"Completed: {file_node.name}")
                    else:
                        self.state.mark_file_failed(file_node.full_path, result.error_message)
                        failed_files += 1
                        print(f"  ✗ Failed: {file_node.name} - {result.error_message}")
                        self.logger.error(f"Failed: {file_node.name} - {result.error_message}")
                    
                    # Auto-save state periodically
                    self.state.maybe_auto_save()
                    
                except KeyboardInterrupt:
                    print(f"\n  Interrupted during {file_node.name}")
                    raise  # Re-raise to be caught by outer handler
                except Exception as e:
                    self.state.mark_file_failed(file_node.full_path, str(e))
                    failed_files += 1
                    print(f"  ✗ Error: {file_node.name} - {str(e)}")
                    self.logger.error(f"Unexpected error for {file_node.name}: {str(e)}")
            
            # Final state save
            self.state.save_state()
            
            # Report final results
            print(f"\nMigration completed!")
            print(f"Total files: {len(all_files)}")
            print(f"Completed: {completed_files}")
            print(f"Failed: {failed_files}")
            print(f"Already completed: {len(all_files) - len(pending_files)}")
            
            return {
                "success": True,
                "total_files": len(all_files),
                "completed_files": completed_files,
                "failed_files": failed_files,
                "skipped_files": len(all_files) - len(pending_files)
            }
            
        except KeyboardInterrupt:
            self.logger.info("Migration interrupted by user")
            self.state.save_state()
            return {"success": False, "error": "Interrupted by user"}
        except Exception as e:
            self.logger.error(f"Migration failed: {str(e)}")
            self.state.save_state()
            return {"success": False, "error": str(e)}


def main():
    """Main entry point for the migration tool."""
    parser = argparse.ArgumentParser(description="Put.io to NAS Migration Tool")
    parser.add_argument(
        '--config', '-c',
        default='config.toml',
        help='Path to configuration file (default: config.toml)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Scan and show what would be downloaded without actually downloading'
    )
    
    args = parser.parse_args()
    
    try:
        orchestrator = MigrationOrchestrator(args.config)
        
        if args.dry_run:
            print("Dry run mode - scanning only...")
            
            # Scan the account to show what would be downloaded
            scan_result = orchestrator._scan_files()
            tree = scan_result["tree"]
            all_files = scan_result["all_files"]
            
            # Calculate totals
            total_size = sum(f.size for f in all_files)
            total_size_gb = total_size / (1024**3)
            
            print(f"\nDry run results:")
            print(f"Files found: {len(all_files)}")
            print(f"Total size: {total_size_gb:.2f} GB")
            
            # Show sample of files that would be downloaded
            print(f"\nSample files (showing first 10):")
            for i, file_node in enumerate(all_files[:10]):
                size_mb = file_node.size / (1024**2)
                print(f"  {file_node.full_path} ({size_mb:.1f} MB)")
            
            if len(all_files) > 10:
                print(f"  ... and {len(all_files) - 10} more files")
            
            print(f"\nTo proceed with actual download, run without --dry-run")
            return
        
        result = orchestrator.run_migration()
        
        if result["success"]:
            print("\nMigration completed successfully!")
        else:
            print(f"\nMigration failed: {result.get('error', 'Unknown error')}")
            sys.exit(1)
            
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()