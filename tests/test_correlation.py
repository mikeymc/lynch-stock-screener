import sys
sys.path.append('backend')

from database import Database
from correlation_analyzer import CorrelationAnalyzer
import json

# Initialize
db = Database()
analyzer = CorrelationAnalyzer(db)

print("=" * 60)
print("CORRELATION ANALYSIS - 1 YEAR BACKTESTS")
print("=" * 60)

# Analyze the results we just generated
analysis = analyzer.analyze_results(years_back=1)

if 'error' in analysis:
    print(f"Error: {analysis['error']}")
else:
    print(f"\nTotal stocks analyzed: {analysis['total_stocks']}")
    print(f"\nOverall Correlation:")
    print(f"  Coefficient: {analysis['overall_correlation']['coefficient']:.3f}")
    print(f"  P-value: {analysis['overall_correlation']['p_value']:.4f}")
    print(f"  Interpretation: {analysis['overall_correlation']['interpretation']}")
    print(f"  Statistically significant: {analysis['overall_correlation']['significant']}")
    
    print(f"\nComponent Correlations:")
    for component, corr in analysis['component_correlations'].items():
        print(f"  {component}: {corr['coefficient']:.3f} ({corr['interpretation']})")
    
    print(f"\nScore Bucket Analysis:")
    for bucket in analysis['score_buckets']:
        print(f"  {bucket['range']}: {bucket['count']} stocks, avg return: {bucket['avg_return']:.2f}%")
    
    print(f"\nRating Analysis:")
    for rating, stats in analysis['rating_analysis'].items():
        print(f"  {rating}: {stats['count']} stocks, avg return: {stats.get('avg_return', 0):.2f}%")
    
    print(f"\nTop 5 Performers:")
    for i, stock in enumerate(analysis['performers']['top_5'], 1):
        print(f"  {i}. {stock['symbol']}: {stock['return']:.2f}% (score: {stock['score']}, rating: {stock['rating']})")
    
    print(f"\nInsights:")
    for insight in analysis['insights']:
        print(f"  {insight}")
