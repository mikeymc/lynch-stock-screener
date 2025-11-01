# ABOUTME: Flask REST API for Lynch stock screener
# ABOUTME: Provides endpoints for screening stocks and retrieving stock analysis

from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
import json
import time
from database import Database
from data_fetcher import DataFetcher
from earnings_analyzer import EarningsAnalyzer
from lynch_criteria import LynchCriteria

app = Flask(__name__)
CORS(app)

db = Database("stocks.db")
fetcher = DataFetcher(db)
analyzer = EarningsAnalyzer(db)
criteria = LynchCriteria(db, analyzer)


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

                    time.sleep(0.25)
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


if __name__ == '__main__':
    app.run(debug=True, port=5001)
