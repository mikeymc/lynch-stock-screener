import sys
import os
import json
import logging
import traceback
from typing import Dict, Any, List

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../backend'))

try:
    from worker import BackgroundWorker
except ImportError:
    print("Error: Could not import BackgroundWorker. Make sure you are running from the tests directory or have setup python path.")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

def load_test_cases(filepath: str) -> List[Dict[str, Any]]:
    with open(filepath, 'r') as f:
        return json.load(f)

def run_tests():
    print("Initializing BackgroundWorker...")
    # Initialize worker (will connect to DB and GenAI)
    try:
        worker = BackgroundWorker()
    except Exception as e:
        print(f"Failed to initialize worker: {e}")
        return

    test_file = os.path.join(os.path.dirname(__file__), 'scenarios/alert_test_cases.json')
    if not os.path.exists(test_file):
        print(f"Test cases not found at {test_file}")
        return

    cases = load_test_cases(test_file)
    print(f"Loaded {len(cases)} test cases.\n")

    passed = 0
    failed = 0

    for i, case in enumerate(cases):
        print(f"[{i+1}/{len(cases)}] Testing '{case['id']}' ({case['category']})... ", end='', flush=True)
        
        symbol = case['metrics'].get('symbol', 'TEST')
        condition = case['condition']
        metrics = case['metrics']
        context = case.get('context')

        try:
            # 1. Construct Prompt
            prompt = worker._construct_alert_prompt(symbol, condition, metrics, context)
            
            # 2. Call LLM (mocking the exact call structure from worker.py)
            response = worker.llm_client.models.generate_content(
                model='gemini-2.0-flash-exp', 
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            
            result = json.loads(response.text)
            triggered = result.get('triggered', False)
            reason = result.get('reason', '')
            
            # 3. Verify
            expected_trigger = case['expected_trigger']
            trigger_match = (triggered == expected_trigger)
            
            reason_match = True
            if 'expected_reason_contains' in case:
                if case['expected_reason_contains'].lower() not in reason.lower():
                    reason_match = False

            if trigger_match and reason_match:
                print("✅ PASS")
                passed += 1
            else:
                print("❌ FAIL")
                print(f"    Condition: {condition}")
                print(f"    Expected Trigger: {expected_trigger}, Got: {triggered}")
                if not reason_match:
                    print(f"    Expected Reason containing: '{case['expected_reason_contains']}'")
                print(f"    Actual Reason: {reason}")
                failed += 1
            
            # Avoid rate limits
            import time
            time.sleep(4)

        except Exception as e:
            print("❌ ERROR")
            print(f"    Exception: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\nTest Execution Complete.")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {passed/len(cases)*100:.1f}%")

if __name__ == "__main__":
    run_tests()
