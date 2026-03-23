"""
Query Analyzer Module
====================
Analyzes user queries to detect fields and values for exact lookups.
"""

import pandas as pd
import re
from typing import Dict, Optional, Tuple


class QueryAnalyzer:
    """Analyze user query to detect which column they're asking about"""
    
    def __init__(self, data: Dict[str, pd.DataFrame]):
        self.data = data
        self.all_columns = self._extract_all_columns()
        self.column_aliases = {
            'client_id': ['client id', 'clientid', 'client code', 'cid', 'client'],
            'customer_name': ['customer name', 'customer', 'name', 'company name'],
            'le_id': ['le id', 'legal entity', 'le code'],
            'account_id': ['account id', 'account', 'acct'],
            'loan_id': ['loan id', 'loan', 'credit facility'],
            'facility_id': ['facility id', 'facility'],
            'collateral_id': ['collateral id', 'collateral'],
            'product_desc': ['product', 'product type', 'account type'],
            'fund_name': ['fund', 'fund name'],
            'security_name': ['security', 'security name', 'isin'],
        }
    
    def _extract_all_columns(self) -> Dict[str, str]:
        """Extract all unique column names from all datasets"""
        columns = {}
        for dataset_name, df in self.data.items():
            if df.empty:
                continue
            for col in df.columns:
                col_lower = col.lower()
                if col_lower not in columns:
                    columns[col_lower] = col  # keep original case
        return columns
    
    def detect_field_and_value(self, query: str) -> Optional[Tuple[str, str]]:
        """
        Detect which field and value user is asking about.
        Returns: (column_name, value) or None
        """
        query_lower = query.lower()
        query_original = query
        
        # Strategy 1: Look for explicit "client id" mention with value
        client_id_patterns = [
            r'client\s+id\s+([C\d]+)',
            r'clientid\s+([C\d]+)',
            r'client\s+([C\d]{6,8})',
            r'for\s+([C\d]{6,8})',
        ]
        
        for pattern in client_id_patterns:
            match = re.search(pattern, query_lower, re.IGNORECASE)
            if match:
                value = match.group(1).upper()
                # Verify it looks like a client_id
                if re.match(r'^C\d{3,8}$', value):
                    print(f"✅ Detected client_id via pattern: {pattern} -> {value}")
                    return ('client_id', value)
        
        # Strategy 2: Look for standalone client ID pattern (C followed by 6-8 digits)
        client_id_match = re.search(r'\b(C\d{6,8})\b', query_original, re.IGNORECASE)
        if client_id_match:
            value = client_id_match.group(1).upper()
            print(f"✅ Detected client_id via standalone pattern: {value}")
            return ('client_id', value)
        
        # Strategy 3: Look for LE_ID pattern (LE followed by 3 digits)
        le_id_match = re.search(r'\b(LE\d{3})\b', query_original, re.IGNORECASE)
        if le_id_match:
            value = le_id_match.group(1).upper()
            print(f"✅ Detected le_id via pattern: {value}")
            return ('le_id', value)
        
        # Strategy 4: Check for "field: value" or "field = value" patterns
        for delimiter in [':', '=', 'is', 'for', 'of']:
            pattern = rf"(\w+)\s*{delimiter}\s*['\"]?([^'\"]+)['\"]?"
            matches = re.findall(pattern, query_lower)
            if matches:
                for field_hint, value in matches:
                    col = self._match_column(field_hint)
                    if col and value.strip():
                        print(f"✅ Detected via delimiter {delimiter}: {col} = {value}")
                        return (col, value.strip())
        
        # Strategy 5: Extract quoted values (assume they're search values)
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", query)
        if quoted:
            for val in quoted:
                for dataset_name, df in self.data.items():
                    if df.empty:
                        continue
                    for col in df.columns:
                        matches = df[df[col].astype(str).str.lower() == val.lower()]
                        if not matches.empty:
                            print(f"✅ Detected quoted value in {col}: {val}")
                            return (col, val)
        
        # Strategy 6: Check if query mentions a column name or alias
        for alias_key, alias_list in self.column_aliases.items():
            for alias in alias_list:
                if alias in query_lower:
                    value_pattern = rf"{alias}\s*(?:is|=|:)?\s*['\"]?([^'\"]+?)['\"]?(?:\s|$)"
                    m = re.search(value_pattern, query_lower)
                    if m:
                        value = m.group(1).strip()
                        col = self._match_column(alias_key)
                        if col and value:
                            print(f"✅ Detected via alias {alias}: {col} = {value}")
                            return (col, value)
        
        print(f"❌ No detection matched for query: {query}")
        return None
    
    def _match_column(self, hint: str) -> Optional[str]:
        """Match a column hint to actual column name"""
        hint_lower = hint.lower()
        
        # Direct match
        if hint_lower in self.all_columns:
            return self.all_columns[hint_lower]
        
        # Fuzzy match (substring)
        for col_lower, col_actual in self.all_columns.items():
            if hint_lower in col_lower or col_lower in hint_lower:
                return col_actual
        
        # Check aliases
        for alias_key, alias_list in self.column_aliases.items():
            if hint_lower in alias_list:
                for col_lower, col_actual in self.all_columns.items():
                    if alias_key.lower() in col_lower:
                        return col_actual
        
        return None
    
    def search_across_all_datasets(self, col_name: str, value: str) -> pd.DataFrame:
        """Search for a value in a specific column across ALL datasets (no limit)"""
        results = []
        
        print(f"\n🔍 Searching for {col_name} = '{value}' across ALL records")
        
        for dataset_name, df in self.data.items():
            if df.empty:
                print(f"  ⏭️  {dataset_name}: empty")
                continue
            
            if col_name not in df.columns:
                print(f"  ⏭️  {dataset_name}: column '{col_name}' not found")
                continue
            
            print(f"  🔎 {dataset_name}: searching in {len(df)} records...")
            
            # Case-insensitive match - NO LIMIT, search ALL records
            matched = df[df[col_name].astype(str).str.lower() == str(value).lower()]
            
            if not matched.empty:
                print(f"     ✅ Found {len(matched)} record(s)")
                matched_copy = matched.copy()
                matched_copy['_dataset'] = dataset_name
                results.append(matched_copy)
            else:
                print(f"     ❌ No matches")
        
        if results:
            combined = pd.concat(results, ignore_index=True)
            print(f"\n✅ Total results across ALL datasets: {len(combined)}")
            return combined
        
        print(f"\n❌ No results found across any dataset")
        return pd.DataFrame()
