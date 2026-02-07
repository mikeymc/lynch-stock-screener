# ABOUTME: Strategy execution job mixin for the background worker
# ABOUTME: Handles autonomous investment strategy execution

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class StrategyJobsMixin:
    """Mixin for strategy_execution job type"""

    def _run_strategy_execution(self, job_id: int, params: Dict[str, Any]):
        """Execute autonomous investment strategies.

        Params:
            strategy_ids: Optional list of specific strategy IDs to run.
                         If not provided, runs all enabled strategies.
        """
        logger.info(f"Running strategy_execution job {job_id}")

        try:
            from strategy_executor import StrategyExecutor

            # Get strategies to execute
            strategy_ids = params.get('strategy_ids')

            # Fallback for singular strategy_id (backward compatibility)
            if not strategy_ids and params.get('strategy_id'):
                strategy_ids = [params.get('strategy_id')]

            if strategy_ids:
                strategies = [self.db.get_strategy(sid) for sid in strategy_ids]
                strategies = [s for s in strategies if s]  # Filter None
            else:
                strategies = self.db.get_enabled_strategies()

            if not strategies:
                logger.info("No enabled strategies to execute")
                self.db.complete_job(job_id, result={'status': 'no_strategies'})
                return

            total = len(strategies)
            logger.info(f"Executing {total} strategies")

            self.db.update_job_progress(
                job_id,
                progress_pct=5,
                progress_message=f'Starting execution of {total} strategies',
                total_count=total
            )

            executor = StrategyExecutor(self.db)
            results = []
            completed = 0
            errors = 0

            for strategy in strategies:
                strategy_id = strategy['id']
                strategy_name = strategy.get('name', f'Strategy {strategy_id}')

                try:
                    logger.info(f"Executing strategy: {strategy_name} (ID: {strategy_id})")

                    self.db.update_job_progress(
                        job_id,
                        progress_message=f'Executing: {strategy_name}'
                    )

                    # Execute the strategy
                    limit = params.get('limit')
                    result = executor.execute_strategy(strategy_id, limit=limit, job_id=job_id)
                    results.append({
                        'strategy_id': strategy_id,
                        'name': strategy_name,
                        'status': result.get('status', 'completed'),
                        'trades_executed': result.get('trades_executed', 0),
                        'alpha': result.get('alpha', 0)
                    })

                    logger.info(
                        f"Strategy {strategy_name} completed: "
                        f"{result.get('trades_executed', 0)} trades, "
                        f"alpha: {result.get('alpha', 0):.2f}%"
                    )

                except Exception as e:
                    logger.error(f"Strategy {strategy_name} failed: {e}")
                    results.append({
                        'strategy_id': strategy_id,
                        'name': strategy_name,
                        'status': 'failed',
                        'error': str(e)
                    })
                    errors += 1

                completed += 1
                pct = 5 + int((completed / total) * 90)
                self.db.update_job_progress(
                    job_id,
                    progress_pct=pct,
                    processed_count=completed
                )
                self._send_heartbeat(job_id)

            # Complete job
            final_result = {
                'total_strategies': total,
                'completed': completed,
                'errors': errors,
                'results': results
            }

            self.db.flush()
            self.db.complete_job(job_id, final_result)
            logger.info(f"Strategy execution complete: {completed}/{total} strategies, {errors} errors")

        except Exception as e:
            logger.error(f"Strategy execution job failed: {e}")
            import traceback
            traceback.print_exc()
            self.db.fail_job(job_id, str(e))
