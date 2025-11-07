# ABOUTME: Research script to analyze IFRS field usage in SEC EDGAR filings
# ABOUTME: Tests foreign companies to determine if IFRS support is feasible for edgar_fetcher.py

import requests
import json
import time
from typing import Dict, Any, List, Optional

# Test companies: Foreign companies that file with SEC
TEST_COMPANIES = {
    'SAP': 'SAP SE (Germany)',
    'ASML': 'ASML Holding N.V. (Netherlands)',
    'NVO': 'Novo Nordisk (Denmark)',
    'TSM': 'Taiwan Semiconductor (Taiwan)',
    'UL': 'Unilever (UK/Netherlands)'
}

class IFRSResearcher:
    BASE_URL = "https://data.sec.gov"
    TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
    COMPANY_FACTS_URL = f"{BASE_URL}/api/xbrl/companyfacts/CIK{{cik}}.json"
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Research Script mikey@example.com',
            'Accept-Encoding': 'gzip, deflate'
        }
        self.last_request_time = 0
        self.min_request_interval = 0.1
    
    def _rate_limit(self):
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    def get_cik_for_ticker(self, ticker: str) -> Optional[str]:
        """Get CIK for a ticker"""
        self._rate_limit()
        response = requests.get(self.TICKER_CIK_URL, headers=self.headers, timeout=10)
        data = response.json()
        
        for entry in data.values():
            if entry.get('ticker', '').upper() == ticker.upper():
                return str(entry.get('cik_str', '')).zfill(10)
        return None
    
    def fetch_company_facts(self, cik: str) -> Optional[Dict[str, Any]]:
        """Fetch company facts"""
        self._rate_limit()
        url = self.COMPANY_FACTS_URL.format(cik=cik)
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching CIK {cik}: {e}")
            return None
    
    def analyze_company(self, ticker: str, description: str) -> Dict[str, Any]:
        """Analyze a single company for IFRS field usage"""
        print(f"\n{'='*80}")
        print(f"Analyzing {ticker} - {description}")
        print(f"{'='*80}")
        
        result = {
            'ticker': ticker,
            'description': description,
            'cik': None,
            'has_ifrs': False,
            'has_us_gaap': False,
            'ifrs_fields': [],
            'eps_fields': {},
            'revenue_fields': {},
            'sample_data': {},
            'errors': []
        }
        
        # Get CIK
        cik = self.get_cik_for_ticker(ticker)
        if not cik:
            result['errors'].append('CIK not found')
            print(f"ERROR: CIK not found for {ticker}")
            return result
        
        result['cik'] = cik
        print(f"CIK: {cik}")
        
        # Fetch company facts
        facts = self.fetch_company_facts(cik)
        if not facts:
            result['errors'].append('Could not fetch company facts')
            print(f"ERROR: Could not fetch company facts")
            return result
        
        print(f"Entity Name: {facts.get('entityName', 'N/A')}")
        
        # Check what namespaces are available
        available_namespaces = list(facts.get('facts', {}).keys())
        print(f"\nAvailable namespaces: {', '.join(available_namespaces)}")
        
        result['has_us_gaap'] = 'us-gaap' in available_namespaces
        result['has_ifrs'] = 'ifrs-full' in available_namespaces
        
        # Analyze IFRS fields if present
        if result['has_ifrs']:
            ifrs_facts = facts['facts']['ifrs-full']
            result['ifrs_fields'] = list(ifrs_facts.keys())
            print(f"\nTotal IFRS fields: {len(result['ifrs_fields'])}")
            
            # Look for EPS fields
            eps_related = [f for f in result['ifrs_fields'] if 'earnings' in f.lower() or 'eps' in f.lower() or 'pershare' in f.lower()]
            print(f"\nEPS-related fields ({len(eps_related)}):")
            for field in sorted(eps_related):
                print(f"  - {field}")
                
                # Get sample data for key EPS fields
                if field in ['DilutedEarningsLossPerShare', 'BasicEarningsLossPerShare', 'EarningsPerShare']:
                    try:
                        field_data = ifrs_facts[field]
                        units = list(field_data.get('units', {}).keys())
                        print(f"    Units: {units}")
                        
                        result['eps_fields'][field] = {
                            'units': units,
                            'sample_entries': []
                        }
                        
                        # Get sample entries
                        for unit in units[:3]:  # First 3 units
                            entries = field_data['units'][unit]
                            ten_k_entries = [e for e in entries if e.get('form') == '10-K'][:3]
                            if ten_k_entries:
                                print(f"    Sample 10-K entries for {unit}:")
                                for entry in ten_k_entries:
                                    print(f"      Year: {entry.get('fy')}, Value: {entry.get('val')}, End: {entry.get('end')}, Form: {entry.get('form')}")
                                    result['eps_fields'][field]['sample_entries'].append({
                                        'unit': unit,
                                        'year': entry.get('fy'),
                                        'value': entry.get('val'),
                                        'end': entry.get('end'),
                                        'form': entry.get('form')
                                    })
                    except Exception as e:
                        print(f"    Error getting sample data: {e}")
            
            # Look for revenue fields
            revenue_related = [f for f in result['ifrs_fields'] if 'revenue' in f.lower()]
            print(f"\nRevenue-related fields ({len(revenue_related)}):")
            for field in sorted(revenue_related):
                print(f"  - {field}")
                
                # Get sample data for key revenue fields
                if field in ['Revenue', 'RevenueFromSaleOfGoods', 'RevenueFromRenderingOfServices']:
                    try:
                        field_data = ifrs_facts[field]
                        units = list(field_data.get('units', {}).keys())
                        print(f"    Units: {units}")
                        
                        result['revenue_fields'][field] = {
                            'units': units,
                            'sample_entries': []
                        }
                        
                        # Get sample entries
                        for unit in units[:3]:
                            entries = field_data['units'][unit]
                            ten_k_entries = [e for e in entries if e.get('form') == '10-K'][:3]
                            if ten_k_entries:
                                print(f"    Sample 10-K entries for {unit}:")
                                for entry in ten_k_entries:
                                    print(f"      Year: {entry.get('fy')}, Value: {entry.get('val')}, End: {entry.get('end')}, Form: {entry.get('form')}")
                                    result['revenue_fields'][field]['sample_entries'].append({
                                        'unit': unit,
                                        'year': entry.get('fy'),
                                        'value': entry.get('val'),
                                        'end': entry.get('end'),
                                        'form': entry.get('form')
                                    })
                    except Exception as e:
                        print(f"    Error getting sample data: {e}")
        
        # Also check us-gaap if present
        if result['has_us_gaap']:
            print(f"\nCompany also has us-gaap namespace")
            us_gaap_facts = facts['facts']['us-gaap']
            us_gaap_fields = list(us_gaap_facts.keys())
            
            # Check if they use us-gaap for EPS
            if 'EarningsPerShareDiluted' in us_gaap_fields:
                print(f"  - Has EarningsPerShareDiluted in us-gaap")
        
        return result
    
    def generate_report(self, results: List[Dict[str, Any]]):
        """Generate final research report"""
        print(f"\n\n{'='*80}")
        print("IFRS RESEARCH REPORT - SUMMARY")
        print(f"{'='*80}\n")
        
        # Summary statistics
        total = len(results)
        with_ifrs = sum(1 for r in results if r['has_ifrs'])
        with_us_gaap = sum(1 for r in results if r['has_us_gaap'])
        
        print(f"Companies analyzed: {total}")
        print(f"Companies with ifrs-full namespace: {with_ifrs}")
        print(f"Companies with us-gaap namespace: {with_us_gaap}")
        print(f"Companies with both: {sum(1 for r in results if r['has_ifrs'] and r['has_us_gaap'])}")
        
        # EPS field analysis
        print(f"\n{'='*80}")
        print("EPS FIELD ANALYSIS")
        print(f"{'='*80}\n")
        
        eps_field_usage = {}
        for result in results:
            if result['has_ifrs']:
                for field in result['eps_fields'].keys():
                    if field not in eps_field_usage:
                        eps_field_usage[field] = []
                    eps_field_usage[field].append(result['ticker'])
        
        print("EPS fields found across companies:")
        for field, tickers in sorted(eps_field_usage.items()):
            print(f"  {field}: {', '.join(tickers)}")
        
        # Revenue field analysis
        print(f"\n{'='*80}")
        print("REVENUE FIELD ANALYSIS")
        print(f"{'='*80}\n")
        
        revenue_field_usage = {}
        for result in results:
            if result['has_ifrs']:
                for field in result['revenue_fields'].keys():
                    if field not in revenue_field_usage:
                        revenue_field_usage[field] = []
                    revenue_field_usage[field].append(result['ticker'])
        
        print("Revenue fields found across companies:")
        for field, tickers in sorted(revenue_field_usage.items()):
            print(f"  {field}: {', '.join(tickers)}")
        
        # Unit analysis
        print(f"\n{'='*80}")
        print("UNIT FORMATS")
        print(f"{'='*80}\n")
        
        all_eps_units = set()
        all_revenue_units = set()
        
        for result in results:
            for field, data in result['eps_fields'].items():
                all_eps_units.update(data['units'])
            for field, data in result['revenue_fields'].items():
                all_revenue_units.update(data['units'])
        
        print(f"EPS units found: {', '.join(sorted(all_eps_units))}")
        print(f"Revenue units found: {', '.join(sorted(all_revenue_units))}")
        
        # Data structure consistency
        print(f"\n{'='*80}")
        print("DATA STRUCTURE CONSISTENCY")
        print(f"{'='*80}\n")
        
        print("Checking if IFRS entries have same structure as us-gaap (form, fy, val, end)...")
        
        consistent = True
        for result in results:
            if result['has_ifrs']:
                for field, data in result['eps_fields'].items():
                    for entry in data['sample_entries']:
                        if not all(k in entry for k in ['year', 'value', 'end', 'form']):
                            print(f"  WARNING: {result['ticker']} {field} missing required fields")
                            consistent = False
        
        if consistent:
            print("  ✓ All sampled entries have required fields (form, fy, val, end)")
        
        # Recommendations
        print(f"\n{'='*80}")
        print("RECOMMENDATIONS")
        print(f"{'='*80}\n")
        
        if with_ifrs > 0:
            print(f"✓ IFRS support appears FEASIBLE")
            print(f"\nRecommended field mappings:")
            print(f"  EPS Fields:")
            for field in sorted(eps_field_usage.keys()):
                print(f"    - {field}")
            print(f"\n  Revenue Fields:")
            for field in sorted(revenue_field_usage.keys()):
                print(f"    - {field}")
            print(f"\n  Unit patterns to support:")
            print(f"    - EPS: Look for */shares pattern (e.g., DKK/shares, EUR/shares)")
            print(f"    - Revenue: Look for currency codes (EUR, DKK, TWD, GBP, etc.)")
        else:
            print(f"✗ IFRS support NOT feasible - no companies use ifrs-full namespace")
        
        # Save detailed report to file
        with open('/Users/mikey/workspace/lynch-stock-screener/backend/ifrs_research_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nDetailed results saved to: ifrs_research_results.json")


if __name__ == '__main__':
    researcher = IFRSResearcher()
    results = []
    
    for ticker, description in TEST_COMPANIES.items():
        try:
            result = researcher.analyze_company(ticker, description)
            results.append(result)
        except Exception as e:
            print(f"ERROR analyzing {ticker}: {e}")
            import traceback
            traceback.print_exc()
    
    researcher.generate_report(results)
