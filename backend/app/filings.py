# ABOUTME: SEC filing, news article, and material event endpoints
# ABOUTME: Handles filing section retrieval, summaries, and social sentiment

from flask import Blueprint, jsonify, request
from app import deps
import logging

logger = logging.getLogger(__name__)

filings_bp = Blueprint('filings', __name__)


@filings_bp.route('/api/stock/<symbol>/filings', methods=['GET'])
def get_stock_filings(symbol):
    """Get recent SEC filings (10-K and 10-Q) for a stock from DATABASE"""
    symbol = symbol.upper()

    # Check if stock exists
    stock_metrics = deps.db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Only return for US stocks
    country = stock_metrics.get('country', '')
    if country:
        country_upper = country.upper()
        if country_upper not in ('US', 'USA', 'UNITED STATES'):
            return jsonify({})

    # Get filings from database (cached during screening)
    try:
        filings = deps.db.get_sec_filings(symbol)
        return jsonify(filings if filings else {})
    except Exception as e:
        logger.error(f"Error fetching cached filings for {symbol}: {e}")
        return jsonify({'error': f'Failed to fetch filings: {str(e)}'}), 500


@filings_bp.route('/api/stock/<symbol>/sections', methods=['GET'])
def get_stock_sections(symbol):
    """
    Get key sections from SEC filings (10-K and 10-Q) from DATABASE
    Returns: business, risk_factors, mda, market_risk
    """
    symbol = symbol.upper()
    logger.info(f"[SECTIONS] Fetching cached sections for {symbol}")

    # Check if stock exists
    stock_metrics = deps.db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Only return for US stocks
    country = stock_metrics.get('country', '')
    if country:
        country_upper = country.upper()
        if country_upper not in ('US', 'USA', 'UNITED STATES'):
            logger.info(f"[SECTIONS] Skipping non-US stock {symbol}")
            return jsonify({'sections': {}, 'cached': True})

    # Get sections from database (cached during screening)
    try:
        sections = deps.db.get_filing_sections(symbol)

        # Also get any cached summaries
        summaries = deps.db.get_filing_section_summaries(symbol)

        # Merge summaries into sections response
        if sections and summaries:
            for section_name, summary_data in summaries.items():
                if section_name in sections:
                    sections[section_name]['summary'] = summary_data['summary']

        return jsonify({'sections': sections if sections else {}, 'cached': True})
    except Exception as e:
        logger.error(f"Error fetching cached sections for {symbol}: {e}")
        return jsonify({'error': f'Failed to fetch sections: {str(e)}'}), 500


@filings_bp.route('/api/stock/<symbol>/section-summaries', methods=['GET'])
def get_section_summaries(symbol):
    """
    Get AI-generated summaries for SEC filing sections.
    Generates summaries on-demand if not cached.
    """
    symbol = symbol.upper()
    logger.info(f"[SECTION-SUMMARIES] Fetching/generating summaries for {symbol}")

    # Check if stock exists
    stock_metrics = deps.db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Only return for US stocks
    country = stock_metrics.get('country', '')
    if country:
        country_upper = country.upper()
        if country_upper not in ('US', 'USA', 'UNITED STATES'):
            return jsonify({'summaries': {}, 'cached': True})

    company_name = stock_metrics.get('company_name', symbol)

    try:
        # Get raw sections from database
        sections = deps.db.get_filing_sections(symbol)
        if not sections:
            return jsonify({'summaries': {}, 'message': 'No filing sections available'})

        # Get any existing cached summaries
        cached_summaries = deps.db.get_filing_section_summaries(symbol) or {}

        # Check which sections need summaries generated
        summaries = {}
        sections_to_generate = []

        for section_name, section_data in sections.items():
            if section_name in cached_summaries:
                # Use cached summary
                summaries[section_name] = {
                    'summary': cached_summaries[section_name]['summary'],
                    'filing_type': section_data.get('filing_type'),
                    'filing_date': section_data.get('filing_date'),
                    'cached': True
                }
            else:
                # Need to generate
                sections_to_generate.append((section_name, section_data))

        # Generate missing summaries
        for section_name, section_data in sections_to_generate:
            try:
                content = section_data.get('content', '')
                filing_type = section_data.get('filing_type', '10-K')
                filing_date = section_data.get('filing_date', '')

                if not content:
                    continue

                # Generate summary using AI
                summary = deps.stock_analyst.generate_filing_section_summary(
                    section_name=section_name,
                    section_content=content,
                    company_name=company_name,
                    filing_type=filing_type
                )

                # Cache the summary
                deps.db.save_filing_section_summary(
                    symbol=symbol,
                    section_name=section_name,
                    summary=summary,
                    filing_type=filing_type,
                    filing_date=filing_date
                )

                summaries[section_name] = {
                    'summary': summary,
                    'filing_type': filing_type,
                    'filing_date': filing_date,
                    'cached': False
                }

                logger.info(f"[SECTION-SUMMARIES] Generated summary for {symbol}/{section_name}")

            except Exception as e:
                logger.error(f"Error generating summary for {symbol}/{section_name}: {e}")
                # Continue with other sections even if one fails
                continue

        return jsonify({
            'summaries': summaries,
            'generated_count': len(sections_to_generate),
            'cached_count': len(cached_summaries)
        })

    except Exception as e:
        logger.error(f"Error fetching section summaries for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to fetch summaries: {str(e)}'}), 500


@filings_bp.route('/api/stock/<symbol>/news', methods=['GET'])
def get_stock_news(symbol):
    """
    Get news articles for a stock from DATABASE
    """
    symbol = symbol.upper()

    try:
        # Get news from database (cached during screening)
        articles = deps.db.get_news_articles(symbol)
        cache_status = deps.db.get_news_cache_status(symbol)

        return jsonify({
            'articles': articles if articles else [],
            'cached': True,
            'last_updated': cache_status['last_updated'].isoformat() if cache_status and cache_status.get('last_updated') else None,
            'article_count': len(articles) if articles else 0
        })
    except Exception as e:
        logger.error(f"Error fetching cached news for {symbol}: {e}")
        return jsonify({'error': f'Failed to fetch news: {str(e)}'}), 500


@filings_bp.route('/api/stock/<symbol>/reddit', methods=['GET'])
def get_stock_reddit(symbol):
    """
    Get Reddit sentiment data for a stock.

    First tries to get cached data from database.
    If no cached data exists, fetches live from Reddit (rate limited).
    Includes top conversations (comments + replies) for top 3 posts.
    """
    symbol = symbol.upper()
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'

    try:
        # Clear cache if refresh requested
        if force_refresh:
            conn = deps.db.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM social_sentiment WHERE symbol = %s", (symbol,))
                conn.commit()
                logger.info(f"Cleared {cursor.rowcount} cached Reddit posts for {symbol}")
            finally:
                deps.db.return_connection(conn)

        # Try cached data first (unless we just cleared it)
        if not force_refresh:
            posts = deps.db.get_social_sentiment(symbol, limit=20, min_score=10)

            if posts:
                return jsonify({
                    'posts': posts,
                    'cached': True,
                    'source': 'database'
                })

        # No cached data - fetch live (using Google Search Grounding)
        from reddit_client import RedditClient

        # Get company name for disambiguation (important for short symbols like TW)
        company_name = None
        metrics = deps.db.get_stock_metrics(symbol)
        if metrics and metrics.get('company_name'):
            company_name = metrics.get('company_name')

        client = RedditClient()
        raw_posts = client.find_stock_mentions_with_conversations(
            symbol=symbol,
            time_filter='month',
            max_results=10,
            company_name=company_name
        )

        # Cache for future requests
        if raw_posts:
            deps.db.save_social_sentiment(raw_posts)

        return jsonify({
            'posts': raw_posts,
            'cached': False,
            'source': 'reddit_live'
        })

    except Exception as e:
        logger.error(f"Error fetching Reddit data for {symbol}: {e}")
        return jsonify({'error': f'Failed to fetch Reddit data: {str(e)}'}), 500


@filings_bp.route('/api/stock/<symbol>/material-events', methods=['GET'])
def get_material_events(symbol):
    """
    Get material events (8-K filings) for a stock from DATABASE
    """
    symbol = symbol.upper()

    try:
        # Get events from database (cached during screening)
        events = deps.db.get_material_events(symbol)
        cache_status = deps.db.get_material_events_cache_status(symbol)

        return jsonify({
            'events': events if events else [],
            'cached': True,
            'last_updated': cache_status['last_updated'].isoformat() if cache_status and cache_status.get('last_updated') else None,
            'event_count': len(events) if events else 0
        })
    except Exception as e:
        logger.error(f"Error fetching cached material events for {symbol}: {e}")
        return jsonify({'error': f'Failed to fetch material events: {str(e)}'}), 500


@filings_bp.route('/api/stock/<symbol>/material-event-summaries', methods=['POST'])
def get_material_event_summaries(symbol):
    """
    Get or generate AI summaries for summarizable material events.

    Summarizable item types: 2.02 (earnings), 2.01 (M&A), 1.01 (agreements),
    1.05 (cybersecurity), 2.06 (impairments), 4.02 (accounting issues).

    Request body (optional):
        event_ids: List of specific event IDs to summarize
        model: AI model to use (default: gemini-2.5-flash)

    Returns:
        summaries: Dict mapping event_id to {summary, cached} objects
        generated_count: Number of newly generated summaries
        cached_count: Number of cached summaries returned
    """
    symbol = symbol.upper()
    data = request.get_json() or {}

    try:
        # Get stock info for company name
        stock_metrics = deps.db.get_stock_metrics(symbol)
        if not stock_metrics:
            return jsonify({'error': f'Stock {symbol} not found'}), 404

        company_name = stock_metrics.get('company_name', symbol)

        # Get all material events for the symbol
        all_events = deps.db.get_material_events(symbol)
        if not all_events:
            return jsonify({
                'summaries': {},
                'generated_count': 0,
                'cached_count': 0,
                'message': 'No material events found'
            })

        # Filter to summarizable events
        requested_ids = data.get('event_ids')
        model = data.get('model', 'gemini-2.5-flash')

        summarizable_events = []
        for event in all_events:
            item_codes = event.get('sec_item_codes', [])
            if deps.event_summarizer.should_summarize(item_codes):
                # If specific IDs requested, filter to those
                if requested_ids is None or event['id'] in requested_ids:
                    summarizable_events.append(event)

        if not summarizable_events:
            return jsonify({
                'summaries': {},
                'generated_count': 0,
                'cached_count': 0,
                'message': 'No summarizable events found'
            })

        # Get cached summaries
        event_ids = [e['id'] for e in summarizable_events]
        cached_summaries = deps.db.get_material_event_summaries_batch(event_ids)

        # Build response, generating missing summaries
        summaries = {}
        generated_count = 0
        cached_count = 0

        for event in summarizable_events:
            event_id = event['id']

            if event_id in cached_summaries:
                # Use cached summary
                summaries[event_id] = {
                    'summary': cached_summaries[event_id],
                    'cached': True
                }
                cached_count += 1
            else:
                # Generate new summary
                try:
                    # Check if event has content to summarize
                    if not event.get('content_text'):
                        logger.warning(f"Event {event_id} has no content_text, skipping")
                        continue

                    summary = deps.event_summarizer.generate_summary(
                        event_data=event,
                        company_name=company_name,
                        model_version=model
                    )

                    # Cache the summary
                    deps.db.save_material_event_summary(event_id, summary, model)
                    deps.db.flush()  # Ensure it's written immediately

                    summaries[event_id] = {
                        'summary': summary,
                        'cached': False
                    }
                    generated_count += 1

                    logger.info(f"Generated summary for event {event_id} ({symbol})")

                except Exception as e:
                    logger.error(f"Error generating summary for event {event_id}: {e}")
                    # Continue with other events
                    continue

        return jsonify({
            'summaries': summaries,
            'generated_count': generated_count,
            'cached_count': cached_count
        })

    except Exception as e:
        logger.error(f"Error generating material event summaries for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to generate summaries: {str(e)}'}), 500
