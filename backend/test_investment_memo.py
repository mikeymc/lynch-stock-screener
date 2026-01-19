
import sys
import os
import json

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from app import app

# Configuration
SYMBOL = "AAPL"

def test_investment_memo_endpoint():
    print(f"Testing Investment Memo endpoint for {SYMBOL} using test_client...")
    
    with app.test_client() as client:
        # Mock session if needed, but we are using bypass
        url = f"/api/stock/{SYMBOL}/investment-memo?dev_auth_bypass=true"
        payload = {
            "model": "gemini-3-pro-preview",
            "force_refresh": True
        }
        
        try:
            response = client.post(url, json=payload)
            
            if response.status_code == 404:
                error_json = response.json
                if error_json.get('error') == 'Feature not enabled':
                    print("✅ Endpoint returned 404 as expected (feature disabled by default).")
                    return
                else:
                    print(f"❌ Endpoint returned 404: {error_json}")
                    return

            if response.status_code != 200:
                print(f"❌ Failed with status code: {response.status_code}")
                # print(response.data.decode('utf-8'))
                return

            print("✅ Connection established. processing stream...")
            
            # Streaming response handling with test_client
            content_received = False
            for line in response.response:
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        json_str = decoded_line[6:]
                        try:
                            data = json.loads(json_str)
                            if data['type'] == 'metadata':
                                print("   - Received Metadata")
                            elif data['type'] == 'chunk':
                                content_received = True
                                sys.stdout.write(".")
                                sys.stdout.flush()
                            elif data['type'] == 'done':
                                print("\n   - Stream complete.")
                            elif data['type'] == 'error':
                                print(f"\n❌ Stream error: {data['message']}")
                        except json.JSONDecodeError:
                            pass
            
            if content_received:
                print("\n✅ Successfully received content chunks.")
            else:
                print("\n⚠️ No content chunks received.")

        except Exception as e:
            print(f"\n❌ Exception occurred: {e}")

if __name__ == "__main__":
    test_investment_memo_endpoint()
