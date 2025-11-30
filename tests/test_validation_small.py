import sys
sys.path.append('backend')

from database import Database
from algorithm_validator import AlgorithmValidator
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Initialize
db = Database()
validator = AlgorithmValidator(db)

print("=" * 60)
print("ALGORITHM VALIDATION TEST - 10 STOCKS, 1 YEAR")
print("=" * 60)

# Run small test
summary = validator.run_sp500_backtests(
    years_back=1,
    max_workers=3,  # Conservative for testing
    limit=10  # Just 10 stocks
)

print("\n" + "=" * 60)
print("TEST RESULTS")
print("=" * 60)
print(f"Total processed: {summary['total_processed']}")
print(f"Successful: {summary['successful']}")
print(f"Errors: {summary['errors']}")
print(f"Time elapsed: {summary['elapsed_time']/60:.2f} minutes")

if summary['error_list']:
    print("\nErrors encountered:")
    for error in summary['error_list']:
        print(f"  - {error['symbol']}: {error['error']}")

# Show a few results
print("\n" + "=" * 60)
print("SAMPLE BACKTEST RESULTS")
print("=" * 60)
results = db.get_backtest_results(years_back=1)
for i, result in enumerate(results[:5]):
    print(f"\n{i+1}. {result['symbol']}:")
    print(f"   Return: {result['total_return']:.2f}%")
    print(f"   Historical Score: {result['historical_score']}")
    print(f"   Rating: {result['historical_rating']}")
