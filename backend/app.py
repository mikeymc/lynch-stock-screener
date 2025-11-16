# ABOUTME: Flask REST API for Lynch stock screener
# ABOUTME: Provides endpoints for screening stocks and retrieving stock analysis

from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
import json
import time
import yfinance as yf
from datetime import datetime
from database import Database
from data_fetcher import DataFetcher
from earnings_analyzer import EarningsAnalyzer
from lynch_criteria import LynchCriteria
from schwab_client import SchwabClient
from lynch_analyst import LynchAnalyst
from conversation_manager import ConversationManager

app = Flask(__name__)
CORS(app)

db = Database("stocks.db")
fetcher = DataFetcher(db)
analyzer = EarningsAnalyzer(db)
criteria = LynchCriteria(db, analyzer)
schwab_client = SchwabClient()
lynch_analyst = LynchAnalyst(db)
conversation_manager = ConversationManager(db)


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'})


@app.route('/api/stock/<symbol>', methods=['GET'])
def get_stock(symbol):
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'

    stock_data = fetcher.fetch_stock_data(symbol.upper(), force_refresh)
    if not stock_data:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    evaluation = criteria.evaluate_stock(symbol.upper())

    return jsonify({
        'stock_data': stock_data,
        'evaluation': evaluation
    })


@app.route('/api/screen', methods=['GET'])
def screen_stocks():
    limit_param = request.args.get('limit')
    limit = int(limit_param) if limit_param else None
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'

    def generate():
        session_id = None
        try:
            yield f"data: {json.dumps({'type': 'progress', 'message': 'Fetching stock list...'})}\n\n"

            symbols = fetcher.get_nyse_nasdaq_symbols()

            if not symbols:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Unable to fetch stock symbols'})}\n\n"
                return

            if limit:
                symbols = symbols[:limit]

            total = len(symbols)
            yield f"data: {json.dumps({'type': 'progress', 'message': f'Found {total} stocks to screen...'})}\n\n"

            # Create a new screening session
            session_id = db.create_session(total_analyzed=0, pass_count=0, close_count=0, fail_count=0)

            results = []
            for i, symbol in enumerate(symbols, 1):
                try:
                    yield f"data: {json.dumps({'type': 'progress', 'message': f'Analyzing {symbol} ({i}/{total})...'})}\n\n"

                    stock_data = fetcher.fetch_stock_data(symbol, force_refresh)
                    if not stock_data:
                        print(f"No stock data returned for {symbol}")
                        continue

                    evaluation = criteria.evaluate_stock(symbol)
                    if not evaluation:
                        print(f"No evaluation returned for {symbol}")
                        continue

                    results.append(evaluation)

                    # Save result to session
                    db.save_screening_result(session_id, evaluation)

                    yield f"data: {json.dumps({'type': 'stock_result', 'stock': evaluation})}\n\n"

                    time.sleep(0.2)
                except Exception as e:
                    print(f"Error processing {symbol}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue

            results_by_status = {
                'pass': [r for r in results if r['overall_status'] == 'PASS'],
                'close': [r for r in results if r['overall_status'] == 'CLOSE'],
                'fail': [r for r in results if r['overall_status'] == 'FAIL']
            }

            # Update session with final counts
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE screening_sessions
                SET total_analyzed = ?, pass_count = ?, close_count = ?, fail_count = ?
                WHERE id = ?
            """, (len(results), len(results_by_status['pass']), len(results_by_status['close']), len(results_by_status['fail']), session_id))
            conn.commit()
            conn.close()

            # Cleanup old sessions, keeping only the 2 most recent
            db.cleanup_old_sessions(keep_count=2)

            yield f"data: {json.dumps({'type': 'complete', 'total_analyzed': len(results), 'pass_count': len(results_by_status['pass']), 'close_count': len(results_by_status['close']), 'fail_count': len(results_by_status['fail']), 'results': results_by_status})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(stream_with_context(generate()), content_type='text/event-stream')


@app.route('/api/cached', methods=['GET'])
def get_cached_stocks():
    symbols = db.get_all_cached_stocks()

    results = []
    for symbol in symbols:
        evaluation = criteria.evaluate_stock(symbol)
        if evaluation:
            results.append(evaluation)

    results_by_status = {
        'pass': [r for r in results if r['overall_status'] == 'PASS'],
        'close': [r for r in results if r['overall_status'] == 'CLOSE'],
        'fail': [r for r in results if r['overall_status'] == 'FAIL']
    }

    return jsonify({
        'total_analyzed': len(results),
        'pass_count': len(results_by_status['pass']),
        'close_count': len(results_by_status['close']),
        'fail_count': len(results_by_status['fail']),
        'results': results_by_status
    })


@app.route('/api/sessions/latest', methods=['GET'])
def get_latest_session():
    """Get the most recent screening session with all results"""
    session_data = db.get_latest_session()

    if not session_data:
        return jsonify({'error': 'No screening sessions found'}), 404

    return jsonify(session_data)


@app.route('/api/stock/<symbol>/history', methods=['GET'])
def get_stock_history(symbol):
    """Get historical earnings, revenue, price, and P/E ratio data for charting"""

    # Get period_type parameter (default to 'annual' for backward compatibility)
    period_type = request.args.get('period_type', 'annual').lower()
    if period_type not in ['annual', 'quarterly', 'both']:
        return jsonify({'error': f'Invalid period_type: {period_type}. Must be annual, quarterly, or both'}), 400

    # Get earnings history from database
    earnings_history = db.get_earnings_history(symbol.upper())

    if not earnings_history:
        return jsonify({'error': f'No historical data found for {symbol}'}), 404

    # Filter based on period_type
    if period_type == 'annual':
        earnings_history = [e for e in earnings_history if e.get('period') == 'annual']
    elif period_type == 'quarterly':
        quarterly_data = [e for e in earnings_history if e.get('period') and e.get('period') != 'annual']
        # Fall back to annual data if no quarterly data is available
        if not quarterly_data:
            earnings_history = [e for e in earnings_history if e.get('period') == 'annual']
        else:
            earnings_history = quarterly_data
    # If period_type == 'both', keep all data

    # Sort by year ascending, then by quarter for charting
    def sort_key(entry):
        year = entry['year']
        period = entry.get('period', 'annual')
        # Sort quarterly data by quarter number
        if period and period.startswith('Q'):
            try:
                quarter = int(period[1])
                return (year, quarter)
            except (ValueError, IndexError):
                return (year, 0)
        # Annual data comes after all quarters for the same year
        return (year, 5)

    earnings_history.sort(key=sort_key)

    labels = []
    eps_values = []
    revenue_values = []
    pe_ratios = []
    prices = []
    debt_to_equity_values = []

    # Get yfinance ticker for fallback
    ticker = yf.Ticker(symbol.upper())

    for entry in earnings_history:
        year = entry['year']
        eps = entry['eps']
        revenue = entry['revenue']
        fiscal_end = entry.get('fiscal_end')
        debt_to_equity = entry.get('debt_to_equity')
        period = entry.get('period', 'annual')

        # Create label based on period type
        if period == 'annual':
            label = str(year)
        else:
            # Quarterly data: format as "2023 Q1"
            label = f"{year} {period}"

        labels.append(label)
        eps_values.append(eps)
        revenue_values.append(revenue)
        debt_to_equity_values.append(debt_to_equity)

        price = None

        # Fetch historical price for this year's fiscal year-end
        if fiscal_end:
            # Try Schwab API first if available
            if schwab_client.is_available():
                try:
                    price = schwab_client.get_historical_price(symbol.upper(), fiscal_end)
                except Exception as e:
                    print(f"Schwab API error for {symbol} on {fiscal_end}: {e}")
                    price = None

            # Fall back to yfinance if Schwab failed or unavailable
            if price is None:
                try:
                    # Use fiscal year-end date for yfinance
                    # Fetch a few days before and after to handle weekends/holidays
                    from datetime import datetime, timedelta
                    fiscal_date = datetime.strptime(fiscal_end, '%Y-%m-%d')
                    start_date = (fiscal_date - timedelta(days=7)).strftime('%Y-%m-%d')
                    end_date = (fiscal_date + timedelta(days=3)).strftime('%Y-%m-%d')

                    hist = ticker.history(start=start_date, end=end_date)

                    if not hist.empty:
                        # Get closing price from the last available day
                        price = hist.iloc[-1]['Close']
                except Exception as e:
                    print(f"yfinance error for {symbol} on {fiscal_end}: {e}")
                    price = None
        else:
            # No fiscal_end date, fall back to December 31
            try:
                start_date = f"{year}-12-01"
                end_date = f"{year}-12-31"

                hist = ticker.history(start=start_date, end=end_date)

                if not hist.empty:
                    price = hist.iloc[-1]['Close']
            except Exception as e:
                print(f"Error fetching historical price for {symbol} year {year}: {e}")
                price = None

        # Calculate P/E ratio if we have price and positive EPS
        if price is not None and eps > 0:
            pe_ratio = price / eps
            pe_ratios.append(pe_ratio)
            prices.append(price)
        else:
            # No price data or negative EPS
            pe_ratios.append(None)
            prices.append(None)

    return jsonify({
        'labels': labels,
        'eps': eps_values,
        'revenue': revenue_values,
        'price': prices,
        'pe_ratio': pe_ratios,
        'debt_to_equity': debt_to_equity_values
    })


@app.route('/api/stock/<symbol>/filings', methods=['GET'])
def get_stock_filings(symbol):
    """Get recent SEC filings (10-K and 10-Q) for a stock"""
    symbol = symbol.upper()

    # Check if stock exists
    stock_metrics = db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Only fetch for US stocks
    country = stock_metrics.get('country', '')
    if country and country.upper() != 'USA' and country.upper() != 'UNITED STATES':
        return jsonify({})

    # Check cache validity
    if db.is_filings_cache_valid(symbol):
        filings = db.get_sec_filings(symbol)
        if filings:
            return jsonify(filings)

    # Fetch fresh filings from EDGAR
    try:
        edgar_fetcher = fetcher.edgar_fetcher
        recent_filings = edgar_fetcher.fetch_recent_filings(symbol)

        if not recent_filings:
            return jsonify({})

        # Save to database
        for filing in recent_filings:
            db.save_sec_filing(
                symbol,
                filing['type'],
                filing['date'],
                filing['url'],
                filing['accession_number']
            )

        # Return the formatted result
        filings = db.get_sec_filings(symbol)
        return jsonify(filings if filings else {})

    except Exception as e:
        print(f"Error fetching filings for {symbol}: {e}")
        return jsonify({'error': f'Failed to fetch filings: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/sections', methods=['GET'])
def get_stock_sections(symbol):
    """
    Extract key sections from SEC filings (10-K and 10-Q)
    Returns: business, risk_factors, mda, market_risk
    """
    import sys
    symbol = symbol.upper()
    app.logger.info(f"[SECTIONS] Starting section extraction for {symbol}")
    print(f"[SECTIONS] Starting section extraction for {symbol}", file=sys.stderr, flush=True)

    # Check if stock exists
    stock_metrics = db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Only fetch for US stocks
    country = stock_metrics.get('country', '')
    app.logger.info(f"[SECTIONS] {symbol} country: {country}")
    print(f"[SECTIONS] {symbol} country: {country}", file=sys.stderr, flush=True)
    if country and country.upper() != 'USA' and country.upper() != 'UNITED STATES':
        app.logger.info(f"[SECTIONS] Skipping non-US stock {symbol}")
        print(f"[SECTIONS] Skipping non-US stock {symbol}", file=sys.stderr, flush=True)
        return jsonify({'sections': {}, 'cached': False})

    # Check cache validity (30 days)
    if db.is_sections_cache_valid(symbol, max_age_days=30):
        app.logger.info(f"[SECTIONS] Cache is valid for {symbol}")
        print(f"[SECTIONS] Cache is valid for {symbol}", file=sys.stderr, flush=True)
        sections = db.get_filing_sections(symbol)
        if sections:
            return jsonify({'sections': sections, 'cached': True})
    else:
        app.logger.info(f"[SECTIONS] Cache is NOT valid for {symbol}")
        print(f"[SECTIONS] Cache is NOT valid for {symbol}", file=sys.stderr, flush=True)

    # Extract sections using edgartools (no need for filing URLs)
    edgar_fetcher = fetcher.edgar_fetcher
    all_sections = {}

    # Extract from most recent 10-K (Items 1, 1A, 7, 7A)
    try:
        app.logger.info(f"[SECTIONS] Extracting 10-K sections for {symbol}")
        print(f"[SECTIONS] Extracting 10-K sections for {symbol}", file=sys.stderr, flush=True)
        sections_10k = edgar_fetcher.extract_filing_sections(symbol, '10-K')

        # Save each section to database
        for section_name, section_data in sections_10k.items():
            db.save_filing_section(
                symbol,
                section_name,
                section_data['content'],
                section_data['filing_type'],
                section_data['filing_date']
            )
            all_sections[section_name] = section_data

        app.logger.info(f"[SECTIONS] Extracted {len(sections_10k)} sections from 10-K")
        print(f"[SECTIONS] Extracted {len(sections_10k)} sections from 10-K", file=sys.stderr, flush=True)

    except Exception as e:
        print(f"Error extracting 10-K sections for {symbol}: {e}")
        import traceback
        traceback.print_exc()

    # Extract from most recent 10-Q (Items 2, 3)
    try:
        app.logger.info(f"[SECTIONS] Extracting 10-Q sections for {symbol}")
        print(f"[SECTIONS] Extracting 10-Q sections for {symbol}", file=sys.stderr, flush=True)
        sections_10q = edgar_fetcher.extract_filing_sections(symbol, '10-Q')

        # Save and add 10-Q sections (may overwrite 10-K MD&A and Market Risk with more recent data)
        for section_name, section_data in sections_10q.items():
            db.save_filing_section(
                symbol,
                section_name,
                section_data['content'],
                section_data['filing_type'],
                section_data['filing_date']
            )
            all_sections[section_name] = section_data

        app.logger.info(f"[SECTIONS] Extracted {len(sections_10q)} sections from 10-Q")
        print(f"[SECTIONS] Extracted {len(sections_10q)} sections from 10-Q", file=sys.stderr, flush=True)

    except Exception as e:
        print(f"Error extracting 10-Q sections for {symbol}: {e}")
        import traceback
        traceback.print_exc()

    # Return all extracted sections
    return jsonify({'sections': all_sections, 'cached': False})


@app.route('/api/stock/<symbol>/lynch-analysis', methods=['GET'])
def get_lynch_analysis(symbol):
    """
    Get Peter Lynch-style analysis for a stock.
    Returns cached analysis if available, otherwise generates a new one.
    """
    symbol = symbol.upper()

    # Check if stock exists
    stock_metrics = db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Get historical data
    history = db.get_earnings_history(symbol)
    if not history:
        return jsonify({'error': f'No historical data for {symbol}'}), 404

    # Prepare stock data for analysis
    evaluation = criteria.evaluate_stock(symbol)
    stock_data = {
        **stock_metrics,
        'peg_ratio': evaluation.get('peg_ratio'),
        'earnings_cagr': evaluation.get('earnings_cagr'),
        'revenue_cagr': evaluation.get('revenue_cagr')
    }

    # Get filing sections if available (for US stocks only)
    sections = None
    country = stock_metrics.get('country', '')
    if not country or country.upper() in ['USA', 'UNITED STATES']:
        sections = db.get_filing_sections(symbol)

    # Check if analysis exists in cache before generating
    cached_analysis = db.get_lynch_analysis(symbol)
    was_cached = cached_analysis is not None

    # Get or generate analysis
    try:
        analysis_text = lynch_analyst.get_or_generate_analysis(
            symbol,
            stock_data,
            history,
            sections=sections,
            use_cache=True
        )

        # Get timestamp (fetch again if it was just generated)
        if not was_cached:
            cached_analysis = db.get_lynch_analysis(symbol)

        return jsonify({
            'analysis': analysis_text,
            'cached': was_cached,
            'generated_at': cached_analysis['generated_at'] if cached_analysis else datetime.now().isoformat()
        })
    except Exception as e:
        print(f"Error generating Lynch analysis for {symbol}: {e}")
        return jsonify({'error': f'Failed to generate analysis: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/lynch-analysis/refresh', methods=['POST'])
def refresh_lynch_analysis(symbol):
    """
    Force regeneration of Peter Lynch-style analysis for a stock,
    bypassing the cache.
    """
    symbol = symbol.upper()

    # Check if stock exists
    stock_metrics = db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Get historical data
    history = db.get_earnings_history(symbol)
    if not history:
        return jsonify({'error': f'No historical data for {symbol}'}), 404

    # Prepare stock data for analysis
    evaluation = criteria.evaluate_stock(symbol)
    stock_data = {
        **stock_metrics,
        'peg_ratio': evaluation.get('peg_ratio'),
        'earnings_cagr': evaluation.get('earnings_cagr'),
        'revenue_cagr': evaluation.get('revenue_cagr')
    }

    # Get filing sections if available (for US stocks only)
    sections = None
    country = stock_metrics.get('country', '')
    if not country or country.upper() in ['USA', 'UNITED STATES']:
        sections = db.get_filing_sections(symbol)

    # Force regeneration
    try:
        analysis_text = lynch_analyst.get_or_generate_analysis(
            symbol,
            stock_data,
            history,
            sections=sections,
            use_cache=False
        )

        cached_analysis = db.get_lynch_analysis(symbol)

        return jsonify({
            'analysis': analysis_text,
            'cached': False,
            'generated_at': cached_analysis['generated_at'] if cached_analysis else datetime.now().isoformat()
        })
    except Exception as e:
        print(f"Error refreshing Lynch analysis for {symbol}: {e}")
        return jsonify({'error': f'Failed to generate analysis: {str(e)}'}), 500


@app.route('/api/watchlist', methods=['GET'])
def get_watchlist():
    try:
        symbols = db.get_watchlist()
        return jsonify({'symbols': symbols})
    except Exception as e:
        print(f"Error getting watchlist: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/watchlist/<symbol>', methods=['POST'])
def add_to_watchlist(symbol):
    try:
        db.add_to_watchlist(symbol.upper())
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error adding {symbol} to watchlist: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/watchlist/<symbol>', methods=['DELETE'])
def remove_from_watchlist(symbol):
    try:
        db.remove_from_watchlist(symbol.upper())
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error removing {symbol} from watchlist: {e}")
        return jsonify({'error': str(e)}), 500


# Chat / RAG Endpoints

@app.route('/api/chat/<symbol>/conversations', methods=['GET'])
def list_conversations(symbol):
    """List all conversations for a stock"""
    try:
        conversations = conversation_manager.list_conversations(symbol.upper())
        return jsonify({'conversations': conversations})
    except Exception as e:
        print(f"Error listing conversations for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/<symbol>/new', methods=['POST'])
def create_conversation(symbol):
    """Create a new conversation for a stock"""
    try:
        data = request.get_json() or {}
        title = data.get('title')

        conversation_id = conversation_manager.create_conversation(symbol.upper(), title)

        return jsonify({
            'conversation_id': conversation_id,
            'symbol': symbol.upper(),
            'title': title
        })
    except Exception as e:
        print(f"Error creating conversation for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/conversation/<int:conversation_id>/messages', methods=['GET'])
def get_messages(conversation_id):
    """Get all messages in a conversation"""
    try:
        messages = conversation_manager.get_messages(conversation_id)
        conversation = conversation_manager.get_conversation(conversation_id)

        return jsonify({
            'conversation': conversation,
            'messages': messages
        })
    except Exception as e:
        print(f"Error getting messages for conversation {conversation_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/<symbol>/message', methods=['POST'])
def send_message(symbol):
    """
    Send a message and get AI response.
    Creates a new conversation if none exists, or uses the most recent one.
    """
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Message required'}), 400

        user_message = data['message']
        conversation_id = data.get('conversation_id')

        # Get or create conversation
        if not conversation_id:
            conversation_id = conversation_manager.get_or_create_conversation(symbol.upper())

        # Send message and get response
        result = conversation_manager.send_message(conversation_id, user_message)

        return jsonify({
            'conversation_id': conversation_id,
            'user_message': user_message,
            'assistant_message': result['message'],
            'sources': result['sources'],
            'message_id': result['message_id']
        })

    except Exception as e:
        print(f"Error sending message: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/<symbol>/message/stream', methods=['POST'])
def send_message_stream(symbol):
    """
    Send a message and stream AI response using Server-Sent Events.
    Creates a new conversation if none exists, or uses the most recent one.
    """
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Message required'}), 400

        user_message = data['message']
        conversation_id = data.get('conversation_id')
        lynch_analysis = data.get('lynch_analysis')

        # Get or create conversation
        if not conversation_id:
            conversation_id = conversation_manager.get_or_create_conversation(symbol.upper())

        def generate():
            """Generate Server-Sent Events"""
            # Send conversation ID first
            yield f"data: {json.dumps({'type': 'conversation_id', 'data': conversation_id})}\n\n"

            # Stream response from conversation manager
            for event in conversation_manager.send_message_stream(conversation_id, user_message, lynch_analysis):
                yield f"data: {json.dumps(event)}\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )

    except Exception as e:
        print(f"Error streaming message: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5001)
