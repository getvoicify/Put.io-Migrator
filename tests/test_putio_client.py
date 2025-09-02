import pytest
import responses
import requests
import time
from unittest.mock import patch, MagicMock

from putio_migrator.putio_client import PutioClient, PutioAPIError, PutioRateLimitError


class TestPutioClient:
    
    @responses.activate
    def test_client_authenticates_successfully(self):
        """Test successful API authentication"""
        responses.add(
            responses.GET,
            "https://api.put.io/v2/account/info",
            json={"info": {"username": "testuser", "user_id": 123}},
            status=200
        )
        
        client = PutioClient("test_token_123")
        user_info = client.get_account_info()
        
        assert user_info["info"]["username"] == "testuser"
        assert user_info["info"]["user_id"] == 123

    @responses.activate
    def test_client_handles_invalid_token(self):
        """Test handling of invalid OAuth token"""
        responses.add(
            responses.GET,
            "https://api.put.io/v2/account/info",
            json={"error": "Invalid token"},
            status=401
        )
        
        client = PutioClient("invalid_token")
        
        with pytest.raises(PutioAPIError, match="Authentication failed"):
            client.get_account_info()

    @responses.activate
    def test_client_retries_on_api_failure(self):
        """Test API client retries failed requests"""
        # First request fails, second succeeds
        responses.add(
            responses.GET,
            "https://api.put.io/v2/files/list",
            json={"error": "Server error"},
            status=500
        )
        responses.add(
            responses.GET,
            "https://api.put.io/v2/files/list",
            json={"files": [], "parent": {"id": 0}},
            status=200
        )
        
        client = PutioClient("test_token_123", retry_limit=2)
        result = client.list_files()
        
        assert result["files"] == []
        assert len(responses.calls) == 2

    @responses.activate
    def test_client_handles_rate_limiting(self):
        """Test client respects rate limits"""
        responses.add(
            responses.GET,
            "https://api.put.io/v2/files/list",
            json={"error": "Too Many Requests"},
            status=429,
            headers={"Retry-After": "2"}
        )
        responses.add(
            responses.GET,
            "https://api.put.io/v2/files/list",
            json={"files": [], "parent": {"id": 0}},
            status=200
        )
        
        client = PutioClient("test_token_123")
        
        with patch('time.sleep') as mock_sleep:
            result = client.list_files()
            mock_sleep.assert_called_once_with(2)
            assert result["files"] == []

    @responses.activate
    def test_client_exhausts_retries_and_raises_error(self):
        """Test client raises error after exhausting retries"""
        # All requests fail
        for _ in range(4):  # Default retry_limit is 3, so 4 total attempts
            responses.add(
                responses.GET,
                "https://api.put.io/v2/files/list",
                json={"error": "Server error"},
                status=500
            )
        
        client = PutioClient("test_token_123", retry_limit=3)
        
        with pytest.raises(PutioAPIError, match="API request failed after 3 retries"):
            client.list_files()
        
        assert len(responses.calls) == 4

    @responses.activate
    def test_client_lists_files_in_folder(self):
        """Test listing files in a specific folder"""
        folder_id = 123
        responses.add(
            responses.GET,
            f"https://api.put.io/v2/files/list?parent_id={folder_id}",
            json={
                "files": [
                    {"id": 456, "name": "test_file.txt", "file_type": "VIDEO", "size": 1024},
                    {"id": 789, "name": "subfolder", "file_type": "FOLDER", "size": 0}
                ],
                "parent": {"id": folder_id}
            },
            status=200
        )
        
        client = PutioClient("test_token_123")
        result = client.list_files(folder_id)
        
        assert len(result["files"]) == 2
        assert result["files"][0]["name"] == "test_file.txt"
        assert result["files"][1]["name"] == "subfolder"

    @responses.activate
    def test_client_gets_download_url(self):
        """Test getting download URL for a file"""
        file_id = 456
        responses.add(
            responses.GET,
            f"https://api.put.io/v2/files/{file_id}/download",
            json={"url": "https://download.put.io/files/test_file.txt"},
            status=200
        )
        
        client = PutioClient("test_token_123")
        download_url = client.get_download_url(file_id)
        
        assert download_url == "https://download.put.io/files/test_file.txt"

    @responses.activate
    def test_client_respects_rate_limiting_headers(self):
        """Test client respects X-RateLimit headers"""
        with patch('time.sleep') as mock_sleep:
            responses.add(
                responses.GET,
                "https://api.put.io/v2/account/info",
                json={"info": {"username": "testuser"}},
                status=200,
                headers={
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + 60)
                }
            )
            
            client = PutioClient("test_token_123", requests_per_second=5)
            client.get_account_info()
            
            # Should sleep to respect rate limit
            assert mock_sleep.called