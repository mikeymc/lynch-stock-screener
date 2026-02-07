# ABOUTME: AI analysis endpoints for stock theses, chart narratives, and DCF recommendations
# ABOUTME: Handles streaming thesis generation, transcript summaries, and outlook caching

from flask import Blueprint, jsonify, request, Response, stream_with_context, session
from app import deps
from app.helpers import clean_nan_values
from auth import require_user_auth
from wacc_calculator import calculate_wacc
import json
import math
import logging
import time
import pandas as pd
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

analysis_bp = Blueprint('analysis', __name__)

# Available AI models for analysis generation
AVAILABLE_AI_MODELS = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-3-pro-preview"]
DEFAULT_AI_MODEL = "gemini-3-pro-preview"


@analysis_bp.route('/api/stock/<symbol>/outlook', methods=['GET'])
def get_stock_outlook(symbol):
    """
    Get data for the 'Future Outlook' tab:
    1. Forward Metrics (PEG, PE, EPS)
    2. Insider Buying/Selling Activity
    3. Inventory vs Sales Growth
    4. Gross Margin Stability
    """
    symbol = symbol.upper()

    # 1. Get Metrics (DB)
    metrics = deps.db.get_stock_metrics(symbol)
    if not metrics:
        return jsonify({'error': 'Stock not found (please analyze first)'}), 404

    # 2. Get Insider Trades (DB) - filter to last 365 days
    all_trades = deps.db.get_insider_trades(symbol)
    one_year_ago = datetime.now() - timedelta(days=365)
    trades = [
        t for t in all_trades
        if datetime.strptime(t['transaction_date'], '%Y-%m-%d') >= one_year_ago
    ]

    # 3. Calculate Trends (Live from yfinance cache via helper)
    # We do this live because we don't store Inventory/GrossProfit yet
    # Use fetcher's protected methods to assume caching policies apply
    inventory_data = []
    margin_data = []

    try:
        # Fetch Financials & Balance Sheet
        financials = deps.fetcher._get_yf_financials(symbol)
        balance_sheet = deps.fetcher._get_yf_balance_sheet(symbol)

        if financials is not None and not financials.empty and balance_sheet is not None and not balance_sheet.empty:
            # Common years
            years = sorted([c for c in financials.columns if hasattr(c, 'year')], key=lambda x: x)
            # Filter for last 5 years
            years = years[-5:]

            for date in years:
                year_node = {'year': date.year}

                # --- Gross Margin ---
                # Gross Profit / Total Revenue
                rev = None
                gross_profit = None

                if 'Total Revenue' in financials.index:
                    rev = financials.loc['Total Revenue', date]
                if 'Gross Profit' in financials.index:
                    gross_profit = financials.loc['Gross Profit', date]

                if rev and gross_profit and rev != 0:
                    margin = (gross_profit / rev) * 100
                    margin_data.append({'year': date.year, 'value': margin})

                # --- Inventory vs Sales ---
                # Inventory (Balance Sheet) / Revenue (Financials)
                # Compare Growth Rates
                inventory = None
                if 'Inventory' in balance_sheet.index:
                    if date in balance_sheet.columns:
                        inventory = balance_sheet.loc['Inventory', date]
                elif 'Inventories' in balance_sheet.index: # Alternative key
                     if date in balance_sheet.columns:
                        inventory = balance_sheet.loc['Inventories', date]

                if inventory is not None and rev is not None and pd.notna(inventory) and pd.notna(rev):
                    year_node['revenue'] = rev
                    year_node['inventory'] = inventory
                    inventory_data.append(year_node)

            # Calculate Growth Rates for Inventory Chart
            # Return absolute values (in billions) for cleaner display
            inventory_chart = []
            for item in inventory_data:
                inventory_chart.append({
                    'year': item['year'],
                    'revenue': item['revenue'] / 1e9 if item['revenue'] else 0,  # Convert to billions
                    'inventory': item['inventory'] / 1e9 if item['inventory'] else 0  # Convert to billions
                })

    except Exception as e:
        logger.warning(f"[{symbol}] Failed to calculate outlook trends: {e}")

    # Filter out records with None/NaN values before returning
    margin_data_clean = [m for m in margin_data if m.get('value') is not None and not (isinstance(m.get('value'), float) and math.isnan(m.get('value')))]
    inventory_chart_clean = [i for i in inventory_chart if i.get('revenue') is not None and i.get('inventory') is not None]

    # 4. Get new forward metrics tables
    analyst_estimates = deps.db.get_analyst_estimates(symbol)
    eps_trends = deps.db.get_eps_trends(symbol)
    eps_revisions = deps.db.get_eps_revisions(symbol)
    growth_estimates = deps.db.get_growth_estimates(symbol)
    recommendation_history = deps.db.get_analyst_recommendations(symbol)

    # Calculate current fiscal quarter info
    fiscal_calendar = None
    if analyst_estimates:
        reporting_q = analyst_estimates.get('0q', {})
        next_q = analyst_estimates.get('+1q', {})

        # Determine which quarter we're actually IN right now
        # If 0q has already ended, we're in +1q. Otherwise we're in 0q.
        current_q = reporting_q
        if reporting_q.get('period_end_date'):
            period_end = datetime.strptime(reporting_q['period_end_date'], '%Y-%m-%d')
            today = datetime.now()

            # If the reporting quarter has already ended, we're in the next quarter
            if period_end < today:
                current_q = next_q

        if current_q.get('fiscal_quarter') and current_q.get('fiscal_year'):
            fiscal_calendar = {
                'current_quarter': current_q.get('fiscal_quarter'),
                'current_fiscal_year': current_q.get('fiscal_year'),
                'reporting_quarter': reporting_q.get('fiscal_quarter'),
                'reporting_fiscal_year': reporting_q.get('fiscal_year'),
                'next_earnings_date': metrics.get('next_earnings_date')
            }

    return jsonify({
        'symbol': symbol,
        'metrics': {
            'forward_pe': metrics.get('forward_pe'),
            'forward_peg_ratio': metrics.get('forward_peg_ratio'),
            'forward_eps': metrics.get('forward_eps'),
            'insider_net_buying_6m': metrics.get('insider_net_buying_6m'),
            'next_earnings_date': metrics.get('next_earnings_date'),
            # New fields
            'earnings_growth': metrics.get('earnings_growth'),
            'earnings_quarterly_growth': metrics.get('earnings_quarterly_growth'),
            'revenue_growth': metrics.get('revenue_growth'),
            'recommendation_key': metrics.get('recommendation_key'),
        },
        'analyst_consensus': {
            'rating': metrics.get('analyst_rating'),  # e.g., "buy", "hold", "sell"
            'rating_score': metrics.get('analyst_rating_score'),  # 1.0 (Strong Buy) to 5.0 (Sell)
            'analyst_count': metrics.get('analyst_count'),
            'price_target_high': metrics.get('price_target_high'),
            'price_target_low': metrics.get('price_target_low'),
            'price_target_mean': metrics.get('price_target_mean'),
            'price_target_median': metrics.get('price_target_median'),
        },
        'short_interest': {
            'short_ratio': metrics.get('short_ratio'),  # Days to cover
            'short_percent_float': metrics.get('short_percent_float')
        },
        'current_price': metrics.get('price'),
        'insider_trades': trades,
        'inventory_vs_revenue': clean_nan_values(inventory_chart_clean),
        'gross_margin_history': clean_nan_values(margin_data_clean),
        # New forward metrics sections
        'analyst_estimates': analyst_estimates,  # EPS/Revenue by period
        'eps_trends': eps_trends,  # How estimates changed over time
        'eps_revisions': eps_revisions,  # Up/down revision counts
        'growth_estimates': growth_estimates,  # Stock vs index trend
        'recommendation_history': recommendation_history,  # Monthly buy/hold/sell
        'fiscal_calendar': fiscal_calendar,  # Current quarter and earnings date info
    })


@analysis_bp.route('/api/stock/<symbol>/transcript', methods=['GET'])
def get_stock_transcript(symbol):
    """
    Get the latest earnings call transcript.
    """
    transcript = deps.db.get_latest_earnings_transcript(symbol)

    if not transcript:
        return jsonify({'error': 'No transcript found'}), 404

    return jsonify(clean_nan_values(transcript))


@analysis_bp.route('/api/stock/<symbol>/transcript/summary', methods=['POST'])
def generate_transcript_summary(symbol):
    """
    Generate or retrieve AI summary for the latest earnings transcript.
    Returns cached summary if available, otherwise generates and caches new one.
    """
    try:
        # Get the transcript
        transcript = deps.db.get_latest_earnings_transcript(symbol)

        if not transcript:
            return jsonify({'error': 'No transcript found'}), 404

        # Check if we already have a cached summary
        if transcript.get('summary'):
            return jsonify({
                'summary': transcript['summary'],
                'cached': True,
                'quarter': transcript['quarter'],
                'fiscal_year': transcript['fiscal_year']
            })

        # Generate new summary
        stock = deps.db.get_stock_metrics(symbol)
        company_name = stock.get('company_name', symbol) if stock else symbol

        summary = deps.stock_analyst.generate_transcript_summary(
            transcript_text=transcript['transcript_text'],
            company_name=company_name,
            quarter=transcript['quarter'],
            fiscal_year=transcript['fiscal_year']
        )

        # Save to database
        deps.db.save_transcript_summary(
            symbol=symbol,
            quarter=transcript['quarter'],
            fiscal_year=transcript['fiscal_year'],
            summary=summary
        )
        deps.db.flush()

        return jsonify({
            'summary': summary,
            'cached': False,
            'quarter': transcript['quarter'],
            'fiscal_year': transcript['fiscal_year']
        })

    except Exception as e:
        logger.error(f"Error generating transcript summary for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@analysis_bp.route('/api/stock/<symbol>/thesis', methods=['GET'])
@require_user_auth
def get_stock_thesis(symbol, user_id):
    """
    Get character-specific analysis (thesis) for a stock.
    Supports Lynch vs Buffett based on 'character' query param.
    """
    symbol = symbol.upper()
    character_id = request.args.get('character')

    # Check if stock exists
    t0 = time.time()
    stock_metrics = deps.db.get_stock_metrics(symbol)
    t_metrics = (time.time() - t0) * 1000
    if not stock_metrics:
        logger.warning(f"[Thesis][{symbol}] Stock not found (metrics fetch took {t_metrics:.2f}ms)")
        return jsonify({'error': f'Stock {symbol} not found'}), 404
    logger.info(f"[Thesis][{symbol}] Fetched stock metrics in {t_metrics:.2f}ms")

    # Get historical data
    history = deps.db.get_earnings_history(symbol)
    if not history:
        return jsonify({'error': f'No historical data for {symbol}'}), 404

    # Prepare stock data for analysis
    evaluation = deps.criteria.evaluate_stock(symbol)
    stock_data = {
        **stock_metrics,
        'peg_ratio': evaluation.get('peg_ratio') if evaluation else None,
        'earnings_cagr': evaluation.get('earnings_cagr') if evaluation else None,
        'revenue_cagr': evaluation.get('revenue_cagr') if evaluation else None
    }

    # Get filing sections if available (for US stocks only)
    sections = None
    country = stock_metrics.get('country', '')
    if not country or country.upper() in ['USA', 'UNITED STATES']:
        t0 = time.time()
        sections = deps.db.get_filing_sections(symbol)
        t_sections = (time.time() - t0) * 1000
        section_size_mb = 0
        if sections:
            # Rough estimation of size
            section_size_mb = sum(len(s.get('content', '')) for s in sections.values()) / 1024 / 1024
        logger.info(f"[Thesis][{symbol}] Fetched SEC sections in {t_sections:.2f}ms (Size: {section_size_mb:.2f} MB)")

    # Check cache
    cached_analysis = deps.db.get_lynch_analysis(user_id, symbol, character_id=character_id)
    was_cached = cached_analysis is not None

    # Get model from query parameter and validate
    model = request.args.get('model', DEFAULT_AI_MODEL)
    if model not in AVAILABLE_AI_MODELS:
        return jsonify({'error': f'Invalid model: {model}. Must be one of {AVAILABLE_AI_MODELS}'}), 400

    # Handle 'only_cached' request
    only_cached = request.args.get('only_cached', 'false').lower() == 'true'
    should_stream = request.args.get('stream', 'false').lower() == 'true'

    if only_cached:
        if was_cached:
            return jsonify({
                'analysis': cached_analysis['analysis_text'],
                'cached': True,
                'generated_at': cached_analysis['generated_at'],
                'character_id': cached_analysis.get('character_id', 'lynch')
            })
        else:
            return jsonify({
                'analysis': None,
                'cached': False,
                'generated_at': None
            })

    # Get or generate analysis
    try:
        t_start = time.time()
        logger.info(f"[Thesis][{symbol}] Starting thesis generation request")

        # Fetch material events and news articles for context
        t0 = time.time()
        material_events = deps.db.get_material_events(symbol, limit=10)
        t_events = (time.time() - t0) * 1000
        logger.info(f"[Thesis][{symbol}] Fetched material events in {t_events:.2f}ms")

        t0 = time.time()
        news_articles = deps.db.get_news_articles(symbol, limit=20)
        t_news = (time.time() - t0) * 1000
        logger.info(f"[Thesis][{symbol}] Fetched news articles in {t_news:.2f}ms")

        if should_stream:
            def generate():
                try:
                    # Send metadata first
                    gen_at = cached_analysis['generated_at'] if was_cached else datetime.now().isoformat()
                    if hasattr(gen_at, 'isoformat'):
                        gen_at = gen_at.isoformat()

                    yield f"data: {json.dumps({'type': 'metadata', 'cached': was_cached, 'generated_at': gen_at})}\n\n"

                    # Get iterator
                    iterator = deps.stock_analyst.get_or_generate_analysis(
                        user_id, symbol, stock_data, history,
                        sections=sections, news=news_articles, material_events=material_events,
                        use_cache=True, model_version=model, character_id=character_id
                    )

                    for chunk in iterator:
                        yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                except Exception as e:
                    logger.error(f"Streaming error for {symbol}: {e}")
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            return Response(stream_with_context(generate()), mimetype='text/event-stream')

        # Normal synchronous response
        analysis_generator = deps.stock_analyst.get_or_generate_analysis(
            user_id,
            symbol,
            stock_data,
            history,
            sections=sections,
            news=news_articles,
            material_events=material_events,
            use_cache=True,
            model_version=model,
            character_id=character_id
        )
        analysis_text = "".join(analysis_generator)

        # Get timestamp (fetch again if it was just generated)
        if not was_cached:
            cached_analysis = deps.db.get_lynch_analysis(user_id, symbol, character_id=character_id)

        return jsonify({
            'analysis': analysis_text,
            'cached': was_cached,
            'generated_at': cached_analysis['generated_at'] if cached_analysis else datetime.now().isoformat(),
            'character_id': character_id
        })
    except Exception as e:
        print(f"Error generating thesis for {symbol}: {e}")
        return jsonify({'error': f'Failed to generate analysis: {str(e)}'}), 500


@analysis_bp.route('/api/stock/<symbol>/thesis/refresh', methods=['POST'])
@require_user_auth
def refresh_stock_thesis(symbol, user_id):
    """
    Force regeneration of character-specific analysis for a stock,
    bypassing the cache.
    """
    symbol = symbol.upper()
    data = request.get_json() or {}
    character_id = data.get('character') or request.args.get('character')

    # Check if stock exists
    stock_metrics = deps.db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Get historical data
    history = deps.db.get_earnings_history(symbol)
    if not history:
        return jsonify({'error': f'No historical data for {symbol}'}), 404

    # Prepare stock data for analysis
    evaluation = deps.criteria.evaluate_stock(symbol)
    stock_data = {
        **stock_metrics,
        'peg_ratio': evaluation.get('peg_ratio') if evaluation else None,
        'earnings_cagr': evaluation.get('earnings_cagr') if evaluation else None,
        'revenue_cagr': evaluation.get('revenue_cagr') if evaluation else None
    }

    # Get filing sections if available (for US stocks only)
    sections = None
    country = stock_metrics.get('country', '')
    if not country or country.upper() in ['USA', 'UNITED STATES']:
        sections = deps.db.get_filing_sections(symbol)

    # Get model from request body and validate
    model = data.get('model', DEFAULT_AI_MODEL)
    should_stream = data.get('stream', False)

    if model not in AVAILABLE_AI_MODELS:
        return jsonify({'error': f'Invalid model: {model}. Must be one of {AVAILABLE_AI_MODELS}'}), 400

    # Force regeneration
    try:
        # Fetch material events and news articles for context
        material_events = deps.db.get_material_events(symbol, limit=10)
        news_articles = deps.db.get_news_articles(symbol, limit=20)

        if should_stream:
            def generate():
                try:
                    # Send metadata first (cached=False since we are forcing refresh)
                    yield f"data: {json.dumps({'type': 'metadata', 'cached': False, 'generated_at': datetime.now().isoformat()})}\n\n"

                    # Get iterator
                    iterator = deps.stock_analyst.get_or_generate_analysis(
                        user_id, symbol, stock_data, history,
                        sections=sections, news=news_articles, material_events=material_events,
                        use_cache=False, model_version=model, character_id=character_id
                    )

                    for chunk in iterator:
                        yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                except Exception as e:
                    logger.error(f"Streaming refresh error for {symbol}: {e}")
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            return Response(stream_with_context(generate()), mimetype='text/event-stream')

        analysis_generator = deps.stock_analyst.get_or_generate_analysis(
            user_id,
            symbol,
            stock_data,
            history,
            sections=sections,
            news=news_articles,
            material_events=material_events,
            use_cache=False,
            model_version=model,
            character_id=character_id
        )
        analysis_text = "".join(analysis_generator)

        cached_analysis = deps.db.get_lynch_analysis(user_id, symbol, character_id=character_id)

        return jsonify({
            'analysis': analysis_text,
            'cached': False,
            'generated_at': cached_analysis['generated_at'] if cached_analysis else datetime.now().isoformat(),
            'character_id': character_id
        })
    except Exception as e:
        print(f"Error refreshing thesis for {symbol}: {e}")
        return jsonify({'error': f'Failed to generate analysis: {str(e)}'}), 500


@analysis_bp.route('/api/stock/<symbol>/unified-chart-analysis', methods=['POST'])
@require_user_auth
def get_unified_chart_analysis(symbol, user_id):
    """
    Generate unified character-specific analysis for all three chart sections.
    Returns all three sections with shared context and cohesive narrative.
    """
    symbol = symbol.upper()
    data = request.get_json() or {}
    # Check for 'character' (consistent name) or 'character_id' (legacy/specific name)
    character_id = data.get('character') or data.get('character_id')

    # Check if stock exists
    stock_metrics = deps.db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Get historical data
    history = deps.db.get_earnings_history(symbol)
    if not history:
        return jsonify({'error': f'No historical data for {symbol}'}), 404

    # Prepare stock data for analysis
    evaluation = deps.criteria.evaluate_stock(symbol, character_id=character_id)
    stock_data = {
        **stock_metrics,
        'peg_ratio': evaluation.get('peg_ratio') if evaluation else None,
        'earnings_cagr': evaluation.get('earnings_cagr') if evaluation else None,
        'revenue_cagr': evaluation.get('revenue_cagr') if evaluation else None
    }

    # Get model from request body and validate
    model = data.get('model', DEFAULT_AI_MODEL)
    if model not in AVAILABLE_AI_MODELS:
        return jsonify({'error': f'Invalid model: {model}. Must be one of {AVAILABLE_AI_MODELS}'}), 400

    # Check cache first
    force_refresh = data.get('force_refresh', False)
    only_cached = data.get('only_cached', False)

    # Check for cached unified narrative first (new format)
    cached_narrative = deps.db.get_chart_analysis(user_id, symbol, 'narrative', character_id=character_id)

    if cached_narrative and not force_refresh:
        return jsonify({
            'narrative': cached_narrative['analysis_text'],
            'cached': True,
            'generated_at': cached_narrative['generated_at'],
            'character_id': character_id
        })

    # Fallback: check for legacy 3-section format
    # Legacy sections are also character-specific now
    cached_growth = deps.db.get_chart_analysis(user_id, symbol, 'growth', character_id=character_id)
    cached_cash = deps.db.get_chart_analysis(user_id, symbol, 'cash', character_id=character_id)
    cached_valuation = deps.db.get_chart_analysis(user_id, symbol, 'valuation', character_id=character_id)

    all_legacy_cached = cached_growth and cached_cash and cached_valuation

    if all_legacy_cached and not force_refresh:
        # Return legacy sections format for backward compatibility
        return jsonify({
            'sections': {
                'growth': cached_growth['analysis_text'],
                'cash': cached_cash['analysis_text'],
                'valuation': cached_valuation['analysis_text']
            },
            'cached': True,
            'generated_at': cached_growth['generated_at'],
            'character_id': character_id
        })

    # If only_cached is True and nothing is cached, return empty
    if only_cached:
        return jsonify({})


    try:
        # Get filing sections if available (for US stocks only)
        sections_data = None
        country = stock_metrics.get('country', '')
        if not country or country.upper() in ['US', 'USA', 'UNITED STATES']:
            sections_data = deps.db.get_filing_sections(symbol)

        # Fetch material events and news articles for context
        material_events = deps.db.get_material_events(symbol, limit=10)
        news_articles = deps.db.get_news_articles(symbol, limit=20)

        # Fetch earnings transcripts (last 2 quarters)
        transcripts = deps.db.get_earnings_transcripts(symbol, limit=2)

        # Fetch summary/thesis brief if it exists
        lynch_brief = deps.db.get_lynch_analysis(user_id, symbol, character_id=character_id)
        lynch_brief_text = lynch_brief['analysis_text'] if lynch_brief else None

        # Generate unified analysis with full context
        result = deps.stock_analyst.generate_unified_chart_analysis(
            stock_data,
            history,
            sections=sections_data,
            news=news_articles,
            material_events=material_events,
            transcripts=transcripts,
            lynch_brief=lynch_brief_text,
            model_version=model,
            user_id=user_id,
            character_id=character_id
        )

        # Save unified narrative to cache (using 'narrative' as section name)
        narrative = result.get('narrative', '')
        deps.db.set_chart_analysis(user_id, symbol, 'narrative', narrative, model, character_id=character_id)

        return jsonify({
            'narrative': narrative,
            'cached': False,
            'generated_at': datetime.now().isoformat(),
            'character_id': character_id
        })
    except Exception as e:
        print(f"Error generating unified chart analysis for {symbol}: {e}")
        return jsonify({'error': f'Failed to generate analysis: {str(e)}'}), 500


@analysis_bp.route('/api/stock/<symbol>/dcf-recommendations', methods=['POST'])
@require_user_auth
def get_dcf_recommendations(symbol, user_id):
    """
    Generate AI-powered DCF model recommendations.
    Returns three scenarios (conservative, base, optimistic) with reasoning.
    """
    symbol = symbol.upper()
    data = request.get_json() or {}

    # Check if stock exists
    stock_metrics = deps.db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Get historical data
    history = deps.db.get_earnings_history(symbol)
    if not history:
        return jsonify({'error': f'No historical data for {symbol}'}), 404

    # Prepare stock data for analysis
    evaluation = deps.criteria.evaluate_stock(symbol)
    stock_data = {
        **stock_metrics,
        'peg_ratio': evaluation.get('peg_ratio') if evaluation else None,
        'earnings_cagr': evaluation.get('earnings_cagr') if evaluation else None,
        'revenue_cagr': evaluation.get('revenue_cagr') if evaluation else None
    }

    # Get model from request body (default to gemini-2.5-flash for DCF)
    model = data.get('model', 'gemini-2.5-flash')
    if model not in AVAILABLE_AI_MODELS:
        return jsonify({'error': f'Invalid model: {model}. Must be one of {AVAILABLE_AI_MODELS}'}), 400

    # Check cache first
    force_refresh = data.get('force_refresh', False)
    only_cached = data.get('only_cached', False)

    cached_recommendations = deps.db.get_dcf_recommendations(user_id, symbol)

    if cached_recommendations and not force_refresh:
        return jsonify({
            'scenarios': cached_recommendations['scenarios'],
            'reasoning': cached_recommendations['reasoning'],
            'cached': True,
            'generated_at': cached_recommendations['generated_at']
        })

    # If only_cached is True and no cache, return empty
    if only_cached:
        return jsonify({})

    try:
        # Get WACC data
        wacc_data = calculate_wacc(stock_metrics) if stock_metrics else None

        # Get filing sections if available (for US stocks only)
        sections_data = None
        country = stock_metrics.get('country', '')
        if not country or country.upper() in ['US', 'USA', 'UNITED STATES']:
            sections_data = deps.db.get_filing_sections(symbol)

        # Fetch material events and news articles for context
        material_events = deps.db.get_material_events(symbol, limit=10)
        news_articles = deps.db.get_news_articles(symbol, limit=20)

        # Generate DCF recommendations
        result = deps.stock_analyst.generate_dcf_recommendations(
            stock_data,
            history,
            wacc_data=wacc_data,
            sections=sections_data,
            news=news_articles,
            material_events=material_events,
            model_version=model
        )

        # Save to cache for this user
        deps.db.set_dcf_recommendations(user_id, symbol, result, model)

        return jsonify({
            'scenarios': result['scenarios'],
            'reasoning': result.get('reasoning', ''),
            'cached': False,
            'generated_at': datetime.now().isoformat()
        })
    except Exception as e:
        print(f"Error generating DCF recommendations for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to generate recommendations: {str(e)}'}), 500
