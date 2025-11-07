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

app = Flask(__name__)
CORS(app)

db = Database("stocks.db")
fetcher = DataFetcher(db)
analyzer = EarningsAnalyzer(db)
criteria = LynchCriteria(db, analyzer)
schwab_client = SchwabClient()


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
        try:
            yield f"data: {json.dumps({'type': 'progress', 'message': 'Fetching stock list...'})}\n\n"

            if limit == 50:
                symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BRK.B', 'V', 'JPM']
            else:
                symbols = fetcher.get_nyse_nasdaq_symbols()

                if not symbols:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Unable to fetch stock symbols'})}\n\n"
                    return

                if limit:
                    symbols = symbols[:limit]

            total = len(symbols)
            yield f"data: {json.dumps({'type': 'progress', 'message': f'Found {total} stocks to screen...'})}\n\n"

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


@app.route('/api/stock/<symbol>/history', methods=['GET'])
def get_stock_history(symbol):
    """Get historical earnings, revenue, price, and P/E ratio data for charting"""

    # Get earnings history from database
    earnings_history = db.get_earnings_history(symbol.upper())

    if not earnings_history:
        return jsonify({'error': f'No historical data found for {symbol}'}), 404

    # Sort by year ascending for charting
    earnings_history.sort(key=lambda x: x['year'])

    years = []
    eps_values = []
    revenue_values = []
    pe_ratios = []
    prices = []

    # Get yfinance ticker for fallback
    ticker = yf.Ticker(symbol.upper())

    for entry in earnings_history:
        year = entry['year']
        eps = entry['eps']
        revenue = entry['revenue']
        fiscal_end = entry.get('fiscal_end')

        years.append(year)
        eps_values.append(eps)
        revenue_values.append(revenue)

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
        'years': years,
        'eps': eps_values,
        'revenue': revenue_values,
        'price': prices,
        'pe_ratio': pe_ratios
    })


if __name__ == '__main__':
    app.run(debug=True, port=5001)
