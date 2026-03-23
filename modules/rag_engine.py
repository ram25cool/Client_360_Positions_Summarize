"""
RAG Query Engine Module
======================
Main query processing engine using ChromaDB and Claude.
"""

import pandas as pd
import json
from typing import Dict, List, Any, Optional

from anthropic import Anthropic

from .vector_db import VectorDBManager
from .query_analyzer import QueryAnalyzer
from .langsmith_tracer import LangSmithTracer


class RAGQueryEngine:
    """RAG-based query engine using ChromaDB + Claude - ENHANCED"""
    
    def __init__(self, vectordb: VectorDBManager, anthropic_client: Anthropic, 
                 query_analyzer: QueryAnalyzer, langsmith: Optional[LangSmithTracer] = None):
        self.vectordb = vectordb
        self.anthropic = anthropic_client
        self.langsmith = langsmith
        self.query_analyzer = query_analyzer
    
    def _extract_requested_field(self, question: str) -> Optional[str]:
        """
        Extract which field/column the user is asking for.
        Examples:
        - "What is the customer name for..." -> "customer_name"
        - "What is the segment for..." -> "cust_seg_desc"
        - "Show me the status for..." -> "status"
        """
        query_lower = question.lower()
        
        # Map of common question keywords to column names
        field_keywords = {
            'customer name': ['customer_name', 'orig_customer_name'],
            'segment': ['cust_seg_desc', 'segment', 'cust_seg'],
            'status': ['status', 'account_status', 'loan_status', 'status_code'],
            'type': ['cust_type_desc', 'product_type', 'account_type', 'facility_type', 'collateral_type'],
            'product': ['product_desc', 'product_type', 'product_code'],
            'amount': ['outstanding_amount', 'principal_amount', 'facility_limit', 'utilized_amount', 'collateral_value'],
            'balance': ['closing_balance', 'balance'],
            'interest rate': ['interest_rate', 'rate'],
            'maturity': ['maturity_date', 'maturity'],
            'risk rating': ['risk_rating', 'risk'],
            'le id': ['le_id', 'legal_entity'],
            'account': ['account_id', 'account_type', 'account_status'],
            'loan': ['loan_id', 'loan_status', 'loan_product'],
            'facility': ['facility_id', 'facility_type', 'facility_limit'],
            'collateral': ['collateral_id', 'collateral_type', 'collateral_value'],
            'security': ['security_name', 'isin'],
            'fund': ['fund_name', 'units', 'current_nav'],
        }
        
        requested_field = None
        for keyword, possible_cols in field_keywords.items():
            if keyword in query_lower:
                # Return the first column that exists in any dataset
                for col in possible_cols:
                    for dataset_name, df in self.query_analyzer.data.items():
                        if not df.empty and col in df.columns:
                            requested_field = col
                            print(f"🎯 Requested field detected: '{keyword}' -> '{col}'")
                            break
                    if requested_field:
                        break
            if requested_field:
                break
        
        return requested_field
    
    def _format_exact_results(self, identifier_col: str, identifier_value: str, df: pd.DataFrame, 
                              requested_field: Optional[str] = None) -> str:
        """
        Format exact match results - return only non-empty fields and avoid NaN outputs.
        """
        if df is None or df.empty:
            return f"❌ No records found for **{identifier_col}**=`{identifier_value}`"

        results_text = []

        # Header
        if len(df) > 1:
            results_text.append(f"✅ Found **{len(df)} record(s)** for {identifier_col}=`{identifier_value}`:\n")
        else:
            results_text.append(f"✅ Found **1 record** for {identifier_col}=`{identifier_value}`:\n")

        for idx, row in df.iterrows():
            dataset = row.get('_dataset', 'unknown') if isinstance(row, dict) else row.get('_dataset', 'unknown')
            # If row is Series, drop the internal marker
            if hasattr(row, "drop"):
                row_dict = row.drop(labels=['_dataset'], errors='ignore').to_dict()
            else:
                row_dict = dict(row)
                row_dict.pop('_dataset', None)

            # If specific field requested, show ONLY that field (but avoid NaN)
            if requested_field:
                if requested_field in row_dict:
                    val = row_dict.get(requested_field)
                    if pd.isna(val) or val is None or (isinstance(val, str) and val.strip() == ""):
                        results_text.append(f"**[{dataset}]** - **{requested_field}**: `Not available`")
                    else:
                        results_text.append(f"**[{dataset}]** - **{requested_field}**: `{val}`")
                else:
                    results_text.append(f"**[{dataset}]** - **{requested_field}**: `Column not present`")
            else:
                # Build a clean dict without NaN/None/empty values
                clean = {}
                for k, v in row_dict.items():
                    if v is None:
                        continue
                    # pandas NaN check
                    try:
                        if pd.isna(v):
                            continue
                    except Exception:
                        pass
                    if isinstance(v, str) and v.strip() == "":
                        continue
                    clean[k] = v

                results_text.append(f"**[{dataset}]**")
                if clean:
                    results_text.append("```json")
                    try:
                        results_text.append(json.dumps(clean, default=str, indent=2))
                    except Exception:
                        # fallback safe str conversion
                        cleaned_simple = {kk: str(vv) for kk, vv in clean.items()}
                        results_text.append(json.dumps(cleaned_simple, indent=2))
                    results_text.append("```")
                else:
                    results_text.append("_No non-empty fields available for this record._")

        return "\n".join(results_text)
    
    def query(self, question: str, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """Process query using RAG with FULL dataset + exact lookup + smart field extraction"""
        
        print(f"\n{'='*80}")
        print(f"📝 QUERY: {question}")
        print(f"{'='*80}")
        
        # Extract what field user is asking for
        requested_field = self._extract_requested_field(question)
        
        # Step 0: Try to detect and perform exact lookup on ANY column
        detected = self.query_analyzer.detect_field_and_value(question)
        
        if detected:
            col_name, col_value = detected
            print(f"✅ Detection successful: {col_name} = '{col_value}'")
            print(f"🎯 Searching across ALL records in all datasets...")
            
            exact_df = self.query_analyzer.search_across_all_datasets(col_name, col_value)
            
            if not exact_df.empty:
                # Format with smart field extraction
                answer = self._format_exact_results(col_name, col_value, exact_df, requested_field)
                
                if self.langsmith and self.langsmith.enabled:
                    self.langsmith.trace_query(question, "Exact match lookup", answer, "exact_lookup")
                
                print(f"✅ EXACT MATCH found: {len(exact_df)} record(s)")
                
                return {
                    "answer": answer,
                    "context": f"Exact match across ALL records for {col_name}=`{col_value}`",
                    "search_results": [],
                    "num_results": len(exact_df),
                    "lookup_type": "exact"
                }
            else:
                print(f"⚠️  Detection matched but no data found in any dataset")
        else:
            print(f"❌ No field detection - falling back to semantic search")
        
        # Step 1: Semantic search via vectordb (search across ALL indexed records)
        print(f"\n🔍 Performing semantic search across full vector database...")
        search_results = self.vectordb.search(question, n_results=100, filters=filters)
        
        print(f"📊 Semantic search returned {len(search_results)} results")
        
        # Step 2: Build context from search results
        context = self._build_context(search_results)
        
        # Step 3: Query Claude with context
        response = self._query_claude(question, context)
        
        # Step 4: Trace with LangSmith
        if self.langsmith and self.langsmith.enabled:
            self.langsmith.trace_query(question, context, response, "semantic_search")
        
        return {
            'answer': response,
            'context': context,
            'search_results': search_results[:10],
            'num_results': len(search_results),
            'lookup_type': 'semantic'
        }
    
    def _build_context(self, search_results: List[Dict]) -> str:
        """Build context from search results"""
        if not search_results:
            return "No relevant data found."
        
        context_parts = ["Here is the relevant data from the FULL database:\n"]
        
        for i, result in enumerate(search_results[:50], 1):  # Show up to 50 results
            context_parts.append(f"\n--- Result {i} ---")
            context_parts.append(result['document'])
            context_parts.append(f"[Source: {result['metadata'].get('dataset', 'unknown')}]")
        
        return "\n".join(context_parts)
    
    def _query_claude(self, question: str, context: str) -> str:
        """Query Claude with context"""
        
        system_prompt = """You are a financial data analyst assistant with access to comprehensive client banking data.

Your role:
1. Answer questions accurately based on the provided data context
2. For specific lookups, extract the exact information requested
3. For analytical questions, provide insights and summaries
4. If data is not in the context, clearly state "Information not available in the provided data"
5. Be concise but thorough
6. Format numbers with proper currency symbols and thousand separators
7. Always cite which dataset the information comes from
8. When multiple records are found, summarize key patterns or list top results"""

        prompt = f"""Context (Retrieved from vector database - showing results from FULL dataset):
{context}

Question: {question}

Provide a clear, accurate answer based on the context above."""
        
        try:
            message = self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}]
            )
            
            return message.content[0].text
        
        except Exception as e:
            return f"Error querying AI: {str(e)}"
