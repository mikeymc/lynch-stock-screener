# ABOUTME: Client for Fly.io Machines API to manage on-demand worker instances
# ABOUTME: Starts and stops worker machines for background job processing

import os
import logging
import requests
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Fly Machines API configuration
FLY_API_HOST = 'https://api.machines.dev'


class FlyMachineManager:
    """Manages Fly.io worker machines via the Machines API"""

    def __init__(self):
        self.app_name = os.environ.get('FLY_APP_NAME')
        self.api_token = os.environ.get('FLY_API_TOKEN')
        self.region = os.environ.get('FLY_REGION', 'iad')

        if not self.app_name:
            logger.warning("FLY_APP_NAME not set - machine management disabled")
        if not self.api_token:
            logger.warning("FLY_API_TOKEN not set - machine management disabled")

    def _is_configured(self) -> bool:
        """Check if Fly.io is properly configured"""
        return bool(self.app_name and self.api_token)

    def _headers(self) -> Dict[str, str]:
        """Get API request headers"""
        return {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json'
        }

    def _api_url(self, path: str) -> str:
        """Build API URL"""
        return f'{FLY_API_HOST}/v1/apps/{self.app_name}{path}'

    def list_machines(self, role: str = None) -> List[Dict[str, Any]]:
        """List all machines, optionally filtered by role metadata"""
        if not self._is_configured():
            return []

        try:
            response = requests.get(
                self._api_url('/machines'),
                headers=self._headers(),
                timeout=30
            )
            response.raise_for_status()
            machines = response.json()

            if role:
                machines = [m for m in machines
                           if m.get('config', {}).get('metadata', {}).get('role') == role]

            return machines

        except Exception as e:
            logger.error(f"Failed to list machines: {e}")
            return []

    def get_worker_machines(self) -> List[Dict[str, Any]]:
        """Get all worker machines"""
        return self.list_machines(role='worker')

    def get_running_workers(self) -> List[Dict[str, Any]]:
        """Get running worker machines"""
        workers = self.get_worker_machines()
        return [w for w in workers if w.get('state') == 'started']

    def get_stopped_workers(self) -> List[Dict[str, Any]]:
        """Get stopped worker machines"""
        workers = self.get_worker_machines()
        return [w for w in workers if w.get('state') == 'stopped']

    def start_machine(self, machine_id: str) -> bool:
        """Start a stopped machine"""
        if not self._is_configured():
            return False

        try:
            response = requests.post(
                self._api_url(f'/machines/{machine_id}/start'),
                headers=self._headers(),
                timeout=60
            )
            response.raise_for_status()
            logger.info(f"Started machine {machine_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to start machine {machine_id}: {e}")
            return False

    def stop_machine(self, machine_id: str) -> bool:
        """Stop a running machine"""
        if not self._is_configured():
            return False

        try:
            response = requests.post(
                self._api_url(f'/machines/{machine_id}/stop'),
                headers=self._headers(),
                timeout=60
            )
            response.raise_for_status()
            logger.info(f"Stopped machine {machine_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to stop machine {machine_id}: {e}")
            return False

    def get_current_image(self) -> Optional[str]:
        """Get the current app image from a running web machine"""
        if not self._is_configured():
            return None

        try:
            machines = self.list_machines()
            web_machines = [m for m in machines
                          if m.get('config', {}).get('metadata', {}).get('role') != 'worker']

            if web_machines:
                return web_machines[0].get('config', {}).get('image')

            return None

        except Exception as e:
            logger.error(f"Failed to get current image: {e}")
            return None

    def get_env_vars(self) -> Dict[str, str]:
        """Get environment variables for worker machines"""
        # Pass through database connection vars and API credentials
        return {
            'DB_HOST': os.environ.get('DB_HOST', ''),
            'DB_PORT': os.environ.get('DB_PORT', '5432'),
            'DB_NAME': os.environ.get('DB_NAME', ''),
            'DB_USER': os.environ.get('DB_USER', ''),
            'DB_PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'WORKER_IDLE_TIMEOUT': os.environ.get('WORKER_IDLE_TIMEOUT', '300'),
            'SEC_USER_AGENT': os.environ.get('SEC_USER_AGENT', ''),
            'EDGAR_IDENTITY': os.environ.get('SEC_USER_AGENT', ''),  # edgartools requires this specific name
            'FINNHUB_API_KEY': os.environ.get('FINNHUB_API_KEY', ''),
        }

    def create_worker_machine(self) -> Optional[str]:
        """Create a new worker machine"""
        if not self._is_configured():
            logger.warning("Cannot create worker - Fly.io not configured")
            return None

        image = self.get_current_image()
        if not image:
            logger.error("Cannot create worker - unable to determine app image")
            return None

        try:
            config = {
                'region': self.region,
                'config': {
                    'image': image,
                    'env': self.get_env_vars(),
                    'guest': {
                        'cpu_kind': 'shared',
                        'cpus': 1,  # 1 vCPU sufficient for I/O-bound work
                        'memory_mb': 2048  # Keep 2GB - peak usage ~1.2GB
                    },
                    'auto_destroy': True,  # Destroy when process exits
                    'restart': {
                        'policy': 'on-failure',  # Restart on crash (e.g., OOM)
                        'max_retries': 3  # Limit retries to prevent infinite loops
                    },
                    'metadata': {
                        'role': 'worker'
                    },
                    'init': {
                        'cmd': ['python', '-u', 'worker.py']
                    }
                }
            }

            response = requests.post(
                self._api_url('/machines'),
                headers=self._headers(),
                json=config,
                timeout=120
            )
            response.raise_for_status()

            machine = response.json()
            machine_id = machine.get('id')
            logger.info(f"Created worker machine {machine_id}")
            return machine_id

        except Exception as e:
            logger.error(f"Failed to create worker machine: {e}")
            return None

    def start_worker_if_needed(self) -> Optional[str]:
        """
        Ensure a worker machine is running.
        Returns the machine ID of a running worker, or None if failed.
        """
        if not self._is_configured():
            logger.info("Fly.io not configured - worker will not be started")
            return None

        # Check for running workers
        running = self.get_running_workers()
        if running:
            logger.info(f"Worker already running: {running[0]['id']}")
            return running[0]['id']

        # Check for stopped workers to restart
        stopped = self.get_stopped_workers()
        if stopped:
            machine_id = stopped[0]['id']
            logger.info(f"Restarting stopped worker: {machine_id}")
            if self.start_machine(machine_id):
                return machine_id

        # Create new worker
        logger.info("Creating new worker machine")
        return self.create_worker_machine()

    def ensure_worker_running(self) -> bool:
        """
        Ensure at least one worker is running.
        Returns True if a worker is running or was started.
        """
        machine_id = self.start_worker_if_needed()
        return machine_id is not None

    def start_worker_for_job(self, max_workers: int = 4) -> Optional[str]:
        """
        Start a worker for a new job, respecting the max worker limit.
        
        Unlike ensure_worker_running() which reuses existing workers,
        this creates a new worker for each job to enable parallel processing.
        
        Args:
            max_workers: Maximum number of concurrent workers (default 4)
            
        Returns:
            Machine ID of the started/created worker, or None if at limit
        """
        if not self._is_configured():
            logger.info("Fly.io not configured - worker will not be started")
            return None

        # Count running workers
        running = self.get_running_workers()
        running_count = len(running)
        
        if running_count >= max_workers:
            logger.info(f"At max workers ({running_count}/{max_workers}), job will be queued")
            return running[0]['id']  # Return existing worker ID
        
        # Check for stopped workers to restart first (cheaper than creating new)
        stopped = self.get_stopped_workers()
        if stopped:
            machine_id = stopped[0]['id']
            logger.info(f"Restarting stopped worker: {machine_id} ({running_count + 1}/{max_workers})")
            if self.start_machine(machine_id):
                return machine_id
        
        # Create new worker
        logger.info(f"Creating new worker ({running_count + 1}/{max_workers})")
        return self.create_worker_machine()


# Global instance for convenience
_manager = None


def get_fly_manager() -> FlyMachineManager:
    """Get the global FlyMachineManager instance"""
    global _manager
    if _manager is None:
        _manager = FlyMachineManager()
    return _manager
