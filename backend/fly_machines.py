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
        # Pass through database connection vars
        return {
            'DB_HOST': os.environ.get('DB_HOST', ''),
            'DB_PORT': os.environ.get('DB_PORT', '5432'),
            'DB_NAME': os.environ.get('DB_NAME', ''),
            'DB_USER': os.environ.get('DB_USER', ''),
            'DB_PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'WORKER_IDLE_TIMEOUT': os.environ.get('WORKER_IDLE_TIMEOUT', '300'),
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
                'name': f'worker-{int(__import__("time").time())}',
                'region': self.region,
                'config': {
                    'image': image,
                    'env': self.get_env_vars(),
                    'guest': {
                        'cpu_kind': 'shared',
                        'cpus': 2,
                        'memory_mb': 4096
                    },
                    'auto_destroy': True,  # Destroy when process exits
                    'restart': {
                        'policy': 'no'  # Don't auto-restart
                    },
                    'metadata': {
                        'role': 'worker'
                    },
                    'processes': [{
                        'name': 'worker',
                        'cmd': ['python', 'worker.py']
                    }]
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


# Global instance for convenience
_manager = None


def get_fly_manager() -> FlyMachineManager:
    """Get the global FlyMachineManager instance"""
    global _manager
    if _manager is None:
        _manager = FlyMachineManager()
    return _manager
