import sys
sys.path.append('backend')

from database import Database
from algorithm_optimizer import AlgorithmOptimizer
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Initialize
db = Database()
optimizer = AlgorithmOptimizer(db)

print("=" * 60)
print("ALGORITHM OPTIMIZATION TEST")
print("=" * 60)

# Run optimization on 1-year backtest data
result = optimizer.optimize(
    years_back=1,
    method='gradient_descent',
    max_iterations=50,
    learning_rate=0.05
)

if 'error' in result:
    print(f"Error: {result['error']}")
else:
    print(f"\n📊 OPTIMIZATION RESULTS")
    print(f"   Iterations: {result['iterations']}")
    print(f"\n📈 Initial Configuration:")
    for key, value in result['initial_config'].items():
        print(f"   {key}: {value:.3f}")
    print(f"   Correlation: {result['initial_correlation']:.4f}")
    
    print(f"\n🎯 Optimized Configuration:")
    for key, value in result['best_config'].items():
        print(f"   {key}: {value:.3f}")
    print(f"   Correlation: {result['final_correlation']:.4f}")
    
    print(f"\n✨ Improvement: {result['improvement']:.4f}")
    print(f"   ({result['improvement']/abs(result['initial_correlation'])*100:.1f}% better)")
    
    print(f"\n📝 Last 5 Iterations:")
    for entry in result['history'][-5:]:
        print(f"   Iteration {entry['iteration']}: {entry['correlation']:.4f}")
