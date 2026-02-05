import pytest
import json
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from backend/.env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# We will define this class later
# from backend.earnings_extractor import EarningsExtractor

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "8k"

def load_fixture(filename):
    with open(FIXTURES_DIR / filename, "r") as f:
        return json.load(f)

@pytest.mark.parametrize("filename, expected", [
    ("vz_8k.json", {
        "revenue": 36400000000, 
        "net_income": 2400000000, 
        "eps": 0.55,
        "total_debt": 158150000000,
        "shareholder_equity": 105741000000,
        "shares_outstanding": 4364000000,
        "cash_and_cash_equivalents": 19048000000,
        "dividend_amount": 0.69,
        "fiscal_year": 2025,
        "quarter": "Q4"
    }),
    ("msft_8k.json", {
        "revenue": 81273000000,
        "net_income": 38458000000,
        "eps": 5.16,
        "operating_cash_flow": 35758000000,
        "capital_expenditures": 29876000000,
        "total_debt": 40262000000,
        "shareholder_equity": 390875000000,
        "fiscal_year": 2026,
        "quarter": "Q2"
    }),
    ("nflx_8k.json", {
        "revenue": 12050000000,
        "net_income": 2418000000,
        "eps": 0.56,
        "operating_cash_flow": 2111000000,
        "capital_expenditures": 239300000,
        "total_debt": 14462836000,
        "shareholder_equity": 26615488000,
        "fiscal_year": 2025,
        "quarter": "Q4"
    })
])
def test_extract_earnings_ground_truth(filename, expected):
    """
    Test that the EarningsExtractor correctly extracts financial metrics 
    from known 8-K fixtures.
    """
    from backend.earnings_extractor import EarningsExtractor
    
    fixture_data = load_fixture(filename)
    text_content = fixture_data["content_text"]
    filing_date = fixture_data.get("filing_date")
    
    extractor = EarningsExtractor()
    result = extractor.extract(text_content, filing_date=filing_date)
    
    # Compare standard fields with tolerance
    for field, value in expected.items():
        if field == "quarter":
            assert result.quarter == value, f"{filename}: Expected quarter {value}, got {result.quarter}"
        elif field == "fiscal_year":
            assert result.fiscal_year == value, f"{filename}: Expected FY {value}, got {result.fiscal_year}"
        else:
            extracted_val = getattr(result, field)
            # Allow 5% tolerance for large numbers
            if isinstance(value, (int, float)) and value > 0:
                 diff = abs(extracted_val - value)
                 tolerance = 0.05 * value # 5% tolerance is generous but safe for "billions" vs exact
                 assert diff < tolerance, f"{filename}: {field} mismatch. Expected {value}, got {extracted_val} (diff: {diff})"
            else:
                 assert extracted_val == value, f"{filename}: {field} mismatch"

    ticker = filename.split('_')[0].upper()
