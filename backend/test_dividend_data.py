from database import Database
db = Database()

# Check stock_metrics for dividend data
metrics = db.get_stock_metrics('KO')  # Coca-Cola, known dividend payer
print('=== stock_metrics dividend fields ===')
if 'dividend_yield' in metrics:
    print(f'dividend_yield: {metrics["dividend_yield"]}')

# Check earnings_history for dividend data
print('\n=== earnings_history dividend fields ===')
earnings = db.get_earnings_history('KO', period_type='annual')
if earnings and len(earnings) > 0:
    sample = earnings[0]
    if 'dividend_amount' in sample:
        print(f'dividend_amount field exists: {sample["dividend_amount"]}')
        # Show last 5 years
        print('\nLast 5 years of dividend data:')
        for record in earnings[:5]:
            div = record.get('dividend_amount')
            eps = record.get('eps')
            payout = (div / eps * 100) if div and eps and eps > 0 else None
            print(f"  {record['year']}: Div=${div}, EPS=${eps}, Payout={payout:.1f}%" if payout else f"  {record['year']}: Div=${div}, EPS=${eps}")
