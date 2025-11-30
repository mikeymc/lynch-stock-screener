import sys
sys.path.append('backend')

from database import Database
from algorithm_validator import AlgorithmValidator
from correlation_analyzer import CorrelationAnalyzer
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Initialize
db = Database()
validator = AlgorithmValidator(db)
analyzer = CorrelationAnalyzer(db)

print("=" * 60)
print("VALIDATION RUN - 50 STOCKS, 1 YEAR")
print("=" * 60)

# Run validation with 50 stocks
summary = validator.run_sp500_backtests(
    years_back=1,
    max_workers=5,
    limit=50
)

print("\n" + "=" * 60)
print("VALIDATION SUMMARY")
print("=" * 60)
print(f"Total processed: {summary['total_processed']}")
print(f"Successful: {summary['successful']}")
print(f"Errors: {summary['errors']}")
print(f"Time elapsed: {summary['elapsed_time']/60:.2f} minutes")

# Run correlation analysis
print("\n" + "=" * 60)
print("CORRELATION ANALYSIS")
print("=" * 60)

analysis = analyzer.analyze_results(years_back=1)

if 'error' not in analysis:
    print(f"Total stocks analyzed: {analysis['total_stocks']}")
    print(f"\n📊 Overall Correlation: {analysis['overall_correlation']['coefficient']:.3f}")
    print(f"   {analysis['overall_correlation']['interpretation'].title()}")
    print(f"   Significant: {analysis['overall_correlation']['significant']}")
    
    print(f"\n📈 Component Correlations:")
    for component, corr in sorted(analysis['component_correlations'].items(), 
                                   key=lambda x: abs(x[1]['coefficient']), reverse=True):
        print(f"   {component.replace('_', ' ').title()}: {corr['coefficient']:.3f}")
    
    print(f"\n🎯 Rating Performance:")
    for rating, stats in sorted(analysis['rating_analysis'].items(),
                                 key=lambda x: x[1].get('avg_return', 0), reverse=True):
        print(f"   {rating}: {stats['count']} stocks, {stats.get('avg_return', 0):.2f}% avg return")
    
    print(f"\n💡 Key Insights:")
    for insight in analysis['insights']:
        print(f"   • {insight}")
