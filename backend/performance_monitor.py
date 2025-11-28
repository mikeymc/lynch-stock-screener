"""
Simple performance monitoring for stock screening.
Tracks throughput and provides statistics.
"""

import time
from typing import Dict, Any
from datetime import datetime


class PerformanceMonitor:
    def __init__(self):
        self.start_time = None
        self.stocks_processed = 0
        self.last_report_time = None
        self.last_report_count = 0
        
    def start(self):
        """Start monitoring"""
        self.start_time = time.time()
        self.last_report_time = self.start_time
        self.stocks_processed = 0
        self.last_report_count = 0
        
    def record_stock(self):
        """Record that a stock was processed"""
        self.stocks_processed += 1
        
    def get_stats(self) -> Dict[str, Any]:
        """Get current performance statistics"""
        if not self.start_time:
            return {}
            
        elapsed = time.time() - self.start_time
        overall_rate = self.stocks_processed / elapsed if elapsed > 0 else 0
        
        # Calculate recent rate (since last report)
        time_since_report = time.time() - self.last_report_time
        stocks_since_report = self.stocks_processed - self.last_report_count
        recent_rate = stocks_since_report / time_since_report if time_since_report > 0 else 0
        
        return {
            'total_processed': self.stocks_processed,
            'elapsed_seconds': elapsed,
            'overall_rate': overall_rate,
            'recent_rate': recent_rate,
            'timestamp': datetime.now().isoformat()
        }
    
    def report(self, interval_seconds: int = 30) -> bool:
        """
        Check if it's time to report stats.
        Returns True if a report should be generated.
        """
        if not self.last_report_time:
            return False
            
        if time.time() - self.last_report_time >= interval_seconds:
            self.last_report_time = time.time()
            self.last_report_count = self.stocks_processed
            return True
        return False
    
    def print_stats(self):
        """Print current statistics"""
        stats = self.get_stats()
        if stats:
            print(f"[Performance] Processed {stats['total_processed']} stocks in {stats['elapsed_seconds']:.1f}s")
            print(f"[Performance] Overall rate: {stats['overall_rate']:.2f} stocks/sec")
            print(f"[Performance] Recent rate: {stats['recent_rate']:.2f} stocks/sec")
