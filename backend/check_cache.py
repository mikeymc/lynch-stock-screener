import sqlite3

def check_cache():
    conn = sqlite3.connect('stocks.db')
    cursor = conn.cursor()
    
    print("Checking chart_analyses table...")
    cursor.execute("SELECT symbol, section, generated_at FROM chart_analyses")
    rows = cursor.fetchall()
    
    if not rows:
        print("No cached analyses found.")
    else:
        print(f"Found {len(rows)} cached analyses:")
        for row in rows:
            print(f"  {row[0]} - {row[1]} - {row[2]}")
    
    conn.close()

if __name__ == "__main__":
    check_cache()
