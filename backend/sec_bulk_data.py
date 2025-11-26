"""
SEC Bulk Data Manager

Downloads and manages the SEC's bulk companyfacts.zip file containing
financial data for all publicly traded companies.

The companyfacts.zip file:
- Contains individual JSON files per company (CIK##########.json)
- Is ~1GB compressed, ~10-13GB uncompressed
- Updated nightly by SEC around 3:00 AM ET
- Each JSON has the same structure as the SEC API response
"""

import os
import json
import zipfile
import requests
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class SECBulkDataManager:
    """Manages SEC bulk companyfacts.zip download and extraction"""
    
    ZIP_URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
    
    def __init__(self, cache_dir: str = "./sec_cache", user_agent: str = ""):
        """
        Initialize bulk data manager
        
        Args:
            cache_dir: Directory to store downloaded and extracted data
            user_agent: User-Agent header for SEC requests
        """
        self.cache_dir = Path(cache_dir)
        self.zip_path = self.cache_dir / "companyfacts.zip"
        self.extract_dir = self.cache_dir / "companyfacts"
        self.metadata_path = self.cache_dir / "metadata.json"
        
        self.headers = {
            'User-Agent': user_agent or 'Stock Screener',
            'Accept-Encoding': 'gzip, deflate'
        }
        
        # Create cache directory
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def is_cache_valid(self, max_age_days: int = 1) -> bool:
        """
        Check if local cache exists and is fresh
        
        Args:
            max_age_days: Maximum age in days before cache is considered stale
            
        Returns:
            True if cache exists and is fresh, False otherwise
        """
        if not self.metadata_path.exists():
            return False
        
        try:
            with open(self.metadata_path, 'r') as f:
                metadata = json.load(f)
            
            last_updated = datetime.fromisoformat(metadata['last_updated'])
            age = datetime.now() - last_updated
            
            is_valid = age < timedelta(days=max_age_days)
            if is_valid:
                logger.info(f"SEC cache is valid (age: {age.days} days, {age.seconds // 3600} hours)")
            else:
                logger.info(f"SEC cache is stale (age: {age.days} days)")
            
            return is_valid
            
        except Exception as e:
            logger.warning(f"Error reading cache metadata: {e}")
            return False
    
    def download_and_extract(self, show_progress: bool = True) -> bool:
        """
        Download companyfacts.zip and extract all company JSON files
        
        Supports resume on connection failure.
        
        Args:
            show_progress: Whether to print download/extract progress
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Download zip file with retry and resume support
            max_retries = 3
            
            for attempt in range(max_retries):
                try:
                    # Check if we have a partial download
                    downloaded = 0
                    if self.zip_path.exists():
                        downloaded = os.path.getsize(self.zip_path)
                        if downloaded > 0:
                            print(f"Resuming download from {downloaded // (1024*1024)}MB...")
                    
                    if attempt == 0:
                        print(f"Downloading SEC companyfacts.zip from {self.ZIP_URL}")
                        print("This may take 5-10 minutes depending on connection speed...")
                        print()
                    else:
                        print(f"Retry attempt {attempt + 1}/{max_retries}...")
                    
                    # Set up headers for resume
                    headers = self.headers.copy()
                    if downloaded > 0:
                        headers['Range'] = f'bytes={downloaded}-'
                    
                    response = requests.get(self.ZIP_URL, headers=headers, stream=True, timeout=60)
                    response.raise_for_status()
                    
                    # Get total file size
                    if 'content-range' in response.headers:
                        # Resume response: "bytes 851079347-1338941594/1338941595"
                        total_size = int(response.headers['content-range'].split('/')[-1])
                    else:
                        # Fresh download
                        total_size = int(response.headers.get('content-length', 0))
                    
                    # Download with progress
                    chunk_size = 8192
                    last_progress = int((downloaded / total_size * 100) / 5) * 5 if total_size > 0 else 0
                    
                    mode = 'ab' if downloaded > 0 else 'wb'
                    with open(self.zip_path, mode) as f:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                
                                if show_progress and total_size > 0:
                                    progress = (downloaded / total_size) * 100
                                    # Print every 5%
                                    if progress >= last_progress + 5:
                                        print(f"Download progress: {progress:.1f}% ({downloaded // (1024*1024)}MB / {total_size // (1024*1024)}MB)", flush=True)
                                        last_progress = int(progress / 5) * 5
                    
                    print(f"✓ Download complete: {self.zip_path}")
                    print()
                    break  # Success, exit retry loop
                    
                except (requests.exceptions.ChunkedEncodingError, 
                        requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout) as e:
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                        print(f"✗ Download interrupted: {type(e).__name__}")
                        print(f"Waiting {wait_time}s before retry...")
                        print()
                        import time
                        time.sleep(wait_time)
                    else:
                        raise  # Re-raise on final attempt
            
            # Extract zip file
            print("Extracting companyfacts.zip...")
            print("This may take several minutes...")
            print()
            
            self.extract_dir.mkdir(parents=True, exist_ok=True)
            
            with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
                members = zip_ref.namelist()
                total_files = len(members)
                last_progress = 0
                
                for i, member in enumerate(members):
                    zip_ref.extract(member, self.extract_dir)
                    
                    if show_progress:
                        progress = ((i + 1) / total_files) * 100
                        # Print every 10% or every 1000 files
                        if progress >= last_progress + 10 or (i + 1) % 1000 == 0:
                            print(f"Extract progress: {progress:.1f}% ({i + 1}/{total_files} files)", flush=True)
                            last_progress = int(progress / 10) * 10
            
            print(f"✓ Extraction complete: {total_files} files extracted to {self.extract_dir}")
            print()
            
            # Save metadata
            metadata = {
                'last_updated': datetime.now().isoformat(),
                'total_files': total_files,
                'zip_size_bytes': os.path.getsize(self.zip_path),
                'extract_dir': str(self.extract_dir)
            }
            
            with open(self.metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print("✓ SEC bulk data cache ready!")
            return True
            
        except Exception as e:
            print(f"✗ Error downloading/extracting SEC bulk data: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_company_facts_path(self, cik: str) -> Optional[Path]:
        """
        Get path to company facts JSON file for a given CIK
        
        Args:
            cik: 10-digit CIK string (e.g., '0000320193')
            
        Returns:
            Path to JSON file if it exists, None otherwise
        """
        # Ensure CIK is 10 digits with leading zeros
        cik_padded = cik.zfill(10)
        json_path = self.extract_dir / f"CIK{cik_padded}.json"
        
        if json_path.exists():
            return json_path
        
        return None
    
    def load_company_facts(self, cik: str) -> Optional[Dict[str, Any]]:
        """
        Load company facts JSON for a given CIK
        
        Args:
            cik: 10-digit CIK string
            
        Returns:
            Company facts dictionary or None if not found
        """
        json_path = self.get_company_facts_path(cik)
        
        if not json_path:
            return None
        
        try:
            with open(json_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading company facts for CIK {cik}: {e}")
            return None
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the cache
        
        Returns:
            Dictionary with cache statistics
        """
        if not self.metadata_path.exists():
            return {'status': 'not_initialized'}
        
        try:
            with open(self.metadata_path, 'r') as f:
                metadata = json.load(f)
            
            last_updated = datetime.fromisoformat(metadata['last_updated'])
            age = datetime.now() - last_updated
            
            return {
                'status': 'ready',
                'last_updated': metadata['last_updated'],
                'age_days': age.days,
                'age_hours': age.seconds // 3600,
                'total_files': metadata.get('total_files', 0),
                'zip_size_mb': metadata.get('zip_size_bytes', 0) / (1024 * 1024),
                'extract_dir': metadata.get('extract_dir', ''),
                'is_valid': self.is_cache_valid()
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {'status': 'error', 'error': str(e)}
