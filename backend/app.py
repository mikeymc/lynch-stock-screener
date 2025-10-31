# ABOUTME: Flask REST API for Lynch stock screener
# ABOUTME: Provides endpoints for screening stocks and retrieving stock analysis

from flask import Flask, jsonify, request
from flask_cors import CORS
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
    limit = int(request.args.get('limit', 100))
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'

    symbols = fetcher.get_nyse_nasdaq_symbols()

    if not symbols:
        return jsonify({'error': 'Unable to fetch stock symbols'}), 500

    symbols = symbols[:limit]

    results = []
    for symbol in symbols:
        try:
            fetcher.fetch_stock_data(symbol, force_refresh)
            evaluation = criteria.evaluate_stock(symbol)
            if evaluation:
                results.append(evaluation)
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue

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
    app.run(debug=True, port=5000)
