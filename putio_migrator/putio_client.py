"""Put.io API client with retry logic and rate limiting."""

import time
import requests
from typing import Dict, Any, Optional


class PutioAPIError(Exception):
    """Raised when Put.io API returns an error."""
    pass


class PutioRateLimitError(PutioAPIError):
    """Raised when Put.io API rate limit is exceeded."""
    pass


class PutioClient:
    """Client for interacting with Put.io API."""
    
    def __init__(self, oauth_token: str, api_base_url: str = "https://api.put.io/v2", 
                 retry_limit: int = 3, requests_per_second: int = 5):
        """Initialize Put.io client.
        
        Args:
            oauth_token: Put.io OAuth token
            api_base_url: Base URL for Put.io API
            retry_limit: Number of retries for failed requests
            requests_per_second: Rate limit for API requests
        """
        self.oauth_token = oauth_token
        self.api_base_url = api_base_url.rstrip('/')
        self.retry_limit = retry_limit
        self.min_request_interval = 1.0 / requests_per_second
        self.last_request_time = 0
        
        # Set up session without automatic retries (we handle retries manually)
        self.session = requests.Session()
        
        # Set default headers
        self.session.headers.update({
            'Authorization': f'Bearer {oauth_token}',
            'User-Agent': 'putio-migrator/0.1.0'
        })
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make API request with rate limiting and error handling.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments for requests
            
        Returns:
            API response as dictionary
            
        Raises:
            PutioAPIError: If API returns error or request fails
            PutioRateLimitError: If rate limit exceeded
        """
        # Rate limiting
        time_since_last = time.time() - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        
        url = f"{self.api_base_url}/{endpoint.lstrip('/')}"
        
        for attempt in range(self.retry_limit + 1):
            try:
                response = self.session.request(method, url, timeout=30, **kwargs)
                self.last_request_time = time.time()
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    if attempt < self.retry_limit:
                        time.sleep(retry_after)
                        continue
                    else:
                        raise PutioRateLimitError(f"Rate limit exceeded after {self.retry_limit} retries")
                
                # Handle authentication errors immediately
                if response.status_code == 401:
                    raise PutioAPIError("Authentication failed. Check your OAuth token.")
                
                # Handle other client errors
                if 400 <= response.status_code < 500:
                    raise PutioAPIError(f"Client error {response.status_code}: {response.text}")
                
                # Handle server errors with retries
                if response.status_code >= 500:
                    if attempt < self.retry_limit:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    else:
                        raise PutioAPIError(f"API request failed after {self.retry_limit} retries")
                
                # Check for rate limit headers and sleep if needed
                remaining = response.headers.get('X-RateLimit-Remaining')
                reset_time = response.headers.get('X-RateLimit-Reset')
                if remaining and int(remaining) == 0 and reset_time:
                    sleep_time = int(reset_time) - int(time.time())
                    if sleep_time > 0:
                        time.sleep(min(sleep_time, 60))  # Cap at 60 seconds
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                if attempt < self.retry_limit:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    raise PutioAPIError(f"API request failed after {self.retry_limit} retries: {str(e)}")
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get account information."""
        return self._make_request("GET", "/account/info")
    
    def list_files(self, parent_id: int = 0) -> Dict[str, Any]:
        """List files in a folder.
        
        Args:
            parent_id: Parent folder ID (0 for root)
            
        Returns:
            Dictionary containing files list and parent info
        """
        params = {"parent_id": parent_id} if parent_id > 0 else {}
        return self._make_request("GET", "/files/list", params=params)
    
    def get_file_info(self, file_id: int) -> Dict[str, Any]:
        """Get information about a specific file.
        
        Args:
            file_id: File ID
            
        Returns:
            File information dictionary
        """
        return self._make_request("GET", f"/files/{file_id}")
    
    def get_download_url(self, file_id: int) -> str:
        """Get download URL for a file.
        
        Args:
            file_id: File ID
            
        Returns:
            Download URL string
        """
        response = self._make_request("GET", f"/files/{file_id}/download")
        return response["url"]