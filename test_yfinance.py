import yfinance as yf

stock = yf.Ticker("AAPL")
info = stock.info

print("longName:", info.get('longName'))
print("exchange:", info.get('exchange'))
print("sector:", info.get('sector'))
print("country:", info.get('country'))
print("firstTradeDateMilliseconds:", info.get('firstTradeDateMilliseconds'))
print("firstTradeDateEpochUtc:", info.get('firstTradeDateEpochUtc'))

# Calculate IPO year
ipo_year = None
first_trade_millis = info.get('firstTradeDateMilliseconds')
first_trade_epoch = info.get('firstTradeDateEpochUtc')
if first_trade_millis:
    from datetime import datetime as dt
    ipo_year = dt.fromtimestamp(first_trade_millis / 1000).year
elif first_trade_epoch:
    from datetime import datetime as dt
    ipo_year = dt.fromtimestamp(first_trade_epoch).year

print("Calculated ipo_year:", ipo_year)
