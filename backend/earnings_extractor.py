import os
import logging
from typing import Optional
import json
from pydantic import BaseModel, Field
from google import genai
from google.genai.types import GenerateContentConfig

logger = logging.getLogger(__name__)

from pydantic import BaseModel, Field, ConfigDict

class EarningsData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    revenue: float = Field(..., description="Total Revenue in USD. For billions, convert to absolute number (e.g. 1.5B -> 1500000000).")
    net_income: float = Field(..., description="Net Income (GAAP preferred) in USD.")
    eps: float = Field(..., description="Diluted Earnings Per Share (EPS) in USD.")
    operating_cash_flow: Optional[float] = Field(None, description="Net cash provided by operating activities (QUARTERLY).")
    capital_expenditures: Optional[float] = Field(None, description="Additions to property and equipment / CapEx (QUARTERLY). Return POSITIVE absolute value.")
    total_debt: Optional[float] = Field(None, description="Total Debt (Short-term + Long-term) from Balance Sheet.")
    shareholder_equity: Optional[float] = Field(None, description="Total Stockholders' Equity from Balance Sheet.")
    shares_outstanding: Optional[float] = Field(None, description="Weighted average shares outstanding (diluted) from Income Statement or Balance Sheet.")
    cash_and_cash_equivalents: Optional[float] = Field(None, description="Cash and cash equivalents from Balance Sheet.")
    dividend_amount: Optional[float] = Field(None, description="Quarterly dividend per share declared, if mentioned.")
    fiscal_year: int = Field(..., description="The fiscal year associated with the report (e.g. 2025).")
    quarter: str = Field(..., description="The quarter (e.g. 'Q1', 'Q2', 'Q3', 'Q4').")

class EarningsExtractor:
    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self._api_key:
            logger.warning("GEMINI_API_KEY not found. EarningsExtractor will fail if used.")

        self._client = None
        self.model_name = "gemini-2.5-flash"

    @property
    def client(self):
        """Lazy initialization of Gemini client."""
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def extract(self, text: str, filing_date: Optional[str] = None) -> EarningsData:
        """
        Extracts financial metrics (Revenue, Net Income, EPS, Cash Flow, Balance Sheet) from the provided text.
        
        Args:
            text: Unstructured text from an 8-K filing (usually Item 2.02 or Exhibit 99.1).
            filing_date: Optional date of the filing (YYYY-MM-DD) to help identify the 'current' quarter.
            
        Returns:
            EarningsData object containing the extracted metrics.
        """
        date_context = f"The filing date is {filing_date}." if filing_date else ""
        
        formatted_prompt = f"""
        Extract the following financial metrics for the *most recent COMPLETED quarter* reported in this text.
        {date_context}
        
        CRITICAL INSTRUCTIONS:
        - Do NOT extract "Forecast", "Guidance", "Outlook", or "Projected" values. 
        - Only extract ACTUAL results for the quarter just ended.
        - Ensure data matches the "Three Months Ended" column (quarterly) where available.
        - Ignore "Twelve Months Ended" (annual) columns for Income/Cash Flow unless only annual is available (rare).
        
        Metrics to Extract:
        1. Income Statement: Revenue, Net Income, EPS (Diluted), Shares Outstanding (Diluted).
        2. Cash Flow Statement (Quarterly, if available):
           - Operating Cash Flow ("Net cash provided by operating activities").
           - Capital Expenditures ("Additions to property and equipment", "Purchases of property..."). Return as POSITIVE absolute value.
        3. Balance Sheet (End of Period):
           - Total Debt (Sum of "Short-term debt/Current portion of long-term debt" AND "Long-term debt").
           - Shareholder Equity ("Total stockholders' equity").
           - Cash and Cash Equivalents.
        4. Dividends: Quarterly dividend per share, if declared/mentioned.
        
        Text:
        {text[:200000]}  # Increased context window to ensure full tables are captured (e.g. NFLX BS is at >50k chars)
                           
        Return JSON matching this schema:
        {{
            "revenue": float,
            "net_income": float,
            "eps": float,
            "operating_cash_flow": float | null,
            "capital_expenditures": float | null,
            "total_debt": float | null,
            "shareholder_equity": float | null,
            "shares_outstanding": float | null,
            "cash_and_cash_equivalents": float | null,
            "dividend_amount": float | null,
            "fiscal_year": int,
            "quarter": str
        }}
        
        Guidance:
        - Convert 'billions' or 'millions' to absolute numbers ($1B = 1000000000).
        - CapEx should be positive (absolute magnitude).
        - Fiscal Year/Quarter: Infer from "Three Months Ended [Date]" or explicit mention.
        """
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=formatted_prompt,
                config=GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=EarningsData,
                    temperature=0.1, 
                )
            )
            
            if not response.parsed:
                try:
                   data = json.loads(response.text)
                   return EarningsData(**data)
                except:
                   raise ValueError("Failed to parse JSON from Gemini response")

            return response.parsed

        except Exception as e:
            logger.error(f"Error extracting earnings data: {e}")
            raise
