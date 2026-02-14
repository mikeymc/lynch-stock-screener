# ABOUTME: Generates post-run briefings combining structured data with AI narrative
# ABOUTME: Assembles trade/hold/watch data from decisions and calls Gemini for executive summary

import json
import logging
import os
from typing import Dict, Any

from google import genai

logger = logging.getLogger(__name__)


class BriefingGenerator:

    def __init__(self, db):
        self.db = db

    def generate(
        self,
        run_id: int,
        strategy_id: int,
        portfolio_id: int,
        performance: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate a briefing for a completed strategy run.

        Pulls decisions from the DB, categorizes them, and generates an AI summary.
        Returns a dict ready for db.save_briefing().
        """
        run = self.db.get_strategy_run(run_id)
        decisions = self.db.get_run_decisions(run_id)

        # Categorize decisions
        buys = []
        sells = []
        holds = []
        watchlist = []

        for d in decisions:
            decision = d.get('final_decision')
            entry = {
                'symbol': d['symbol'],
                'reasoning': d.get('decision_reasoning', ''),
                'lynch_score': d.get('lynch_score'),
                'buffett_score': d.get('buffett_score'),
                'lynch_status': d.get('lynch_status'),
                'buffett_status': d.get('buffett_status'),
                'consensus_verdict': d.get('consensus_verdict'),
                'consensus_score': d.get('consensus_score'),
                'dcf_fair_value': d.get('dcf_fair_value'),
                'dcf_upside_pct': d.get('dcf_upside_pct'),
                'deliberation': d.get('thesis_full') or d.get('thesis_summary', ''),
            }

            if decision == 'BUY':
                entry['shares'] = d.get('shares_traded')
                entry['price'] = d.get('trade_price')
                entry['position_value'] = d.get('position_value')
                buys.append(entry)
            elif decision == 'SELL':
                entry['shares'] = d.get('shares_traded')
                entry['price'] = d.get('trade_price')
                entry['position_value'] = d.get('position_value')
                entry['exit_type'] = 'strategy'
                sells.append(entry)
            elif decision == 'HOLD':
                entry['verdict'] = d.get('thesis_verdict', 'HOLD')
                entry['position_value'] = d.get('position_value')
                holds.append(entry)
            elif decision == 'SKIP':
                entry['verdict'] = d.get('thesis_verdict', 'WATCH')
                watchlist.append(entry)

        # Build structured data
        briefing = {
            'run_id': run_id,
            'strategy_id': strategy_id,
            'portfolio_id': portfolio_id,
            'stocks_screened': run.get('stocks_screened', 0),
            'stocks_scored': run.get('stocks_scored', 0),
            'theses_generated': run.get('theses_generated', 0),
            'trades_executed': run.get('trades_executed', 0),
            'portfolio_value': performance.get('portfolio_value'),
            'portfolio_return_pct': performance.get('portfolio_return_pct'),
            'spy_return_pct': performance.get('spy_return_pct'),
            'alpha': performance.get('alpha'),
            'buys_json': json.dumps(buys),
            'sells_json': json.dumps(sells),
            'holds_json': json.dumps(holds),
            'watchlist_json': json.dumps(watchlist),
        }

        # Generate AI executive summary
        briefing['executive_summary'] = self._generate_executive_summary(briefing)

        return briefing

    def _generate_executive_summary(self, briefing: Dict[str, Any]) -> str:
        """Generate a detailed AI briefing covering trades, rationale, and portfolio posture."""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            prompt_path = os.path.join(current_dir, 'briefing_prompt.md')

            with open(prompt_path, 'r') as f:
                prompt_template = f.read()

            prompt = prompt_template.format(
                stocks_screened=briefing.get('stocks_screened', 0),
                stocks_scored=briefing.get('stocks_scored', 0),
                theses_generated=briefing.get('theses_generated', 0),
                trades_executed=briefing.get('trades_executed', 0),
                portfolio_value=briefing.get('portfolio_value', 0),
                portfolio_return_pct=briefing.get('portfolio_return_pct', 0),
                spy_return_pct=briefing.get('spy_return_pct', 0),
                alpha=briefing.get('alpha', 0),
                buys=briefing.get('buys_json', '[]'),
                sells=briefing.get('sells_json', '[]'),
                holds=briefing.get('holds_json', '[]'),
                watchlist=briefing.get('watchlist_json', '[]'),
            )

            from google.genai.types import GenerateContentConfig
            client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=GenerateContentConfig(temperature=0.7),
            )
            return response.text

        except Exception as e:
            logger.warning(f"Failed to generate executive summary: {e}")
            return f"Strategy run completed. Unable to generate AI summary: {e}"
