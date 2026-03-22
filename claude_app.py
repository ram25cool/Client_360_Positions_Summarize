# (Full script content — only one change compared to the previous version:
# the Loans by Product Type block now checks both 'loan_product' and 'outstanding_amount'
# exist in the loans dataframe before performing groupby. No other logic was altered.)

"""
Client 360 Intelligence POC with RAG (ChromaDB) + LangSmith Tracing
====================================================================
Enhanced version with:
- Fixed: Full dataset search across ALL records (not just top 20)
- Fixed: Smart field extraction - returns only requested field
- Improved: Advanced vector search with better filtering
- Enhanced: Rich analytics with multiple visualizations
- NEW: Exact lookup on ANY column (not just client_id)
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import os
from anthropic import Anthropic
import json
from typing import Dict, List, Any, Tuple, Optional
import chromadb
from chromadb.config import Settings
from langsmith import Client as LangSmithClient
from langsmith.run_helpers import traceable
import hashlib
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

file_path="Data/ai_generated_data/upload_dataset_other_files/"

# Page config
st.set_page_config(
    page_title="Client 360 Intelligence - RAG POC",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .search-result {
        background: #1e1e2e;
        color: #e0e0e0;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        border-left: 4px solid #1f77b4;
        font-family: 'Courier New', monospace;
        line-height: 1.6;
    }
    .search-result p {
        color: #e0e0e0;
        margin: 0.5rem 0;
    }
    .search-result code {
        background-color: #0d0d14;
        color: #58a6ff;
        padding: 2px 6px;
        border-radius: 3px;
    }
    .section-header {
        background: #e8f4f8;
        padding: 0.8rem;
        border-radius: 5px;
        font-weight: bold;
        margin-top: 1rem;
        border-left: 5px solid #1f77b4;
    }
    .answer-box {
        background-color: #1e1e2e !important;
        color: #e0e0e0 !important;
        padding: 1.5rem !important;
        border-radius: 8px !important;
        border-left: 4px solid #1f77b4 !important;
        font-size: 0.95rem !important;
        line-height: 1.6 !important;
    }
    .answer-box h1, .answer-box h2, .answer-box h3 {
        color: #58a6ff !important;
    }
    .answer-box strong {
        color: #79c0ff !important;
    }
    .answer-box a {
        color: #58a6ff !important;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'vectordb_initialized' not in st.session_state:
    st.session_state.vectordb_initialized = False

# ============================================================================
# DATA LOADING FUNCTIONS
# ============================================================================

@st.cache_data
def load_all_data():
    """Load all CSV files into dataframes"""
    data = {}
    
    files = {
        'clients': 'client_master.csv',
        'core': 'core.csv',
        'collateral': 'collateral.csv',
        'custody': 'custody.csv',
        'facilities': 'facilities.csv',
        'loans': 'loans.csv',
        'fxd': 'fxd.csv',
        'funds': 'funds.csv',
        'trade_otp': 'trade_otp.csv',
        'trade_dtp': 'trade_dtp.csv'
    }
    
    for name, path in files.items():
        try:
            file_name=file_path + path
            data[name] = pd.read_csv(file_name)
        except FileNotFoundError:
            st.warning(f"File not found: {path}, using empty DataFrame")
            data[name] = pd.DataFrame()
    
    return data

# ============================================================================
# COLUMN/VALUE DETECTOR (ENHANCED)
# ============================================================================

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

# ============================================================================
# CHROMADB VECTOR DATABASE SETUP (FULL DATASET)
# ============================================================================

class VectorDBManager:
    """Manage ChromaDB vector database for RAG - FULL DATASET INDEXING"""
    
    def __init__(self):
        self.client = chromadb.Client(Settings(
            anonymized_telemetry=False,
            is_persistent=False
        ))
        self.collection = None
        self.raw_data = None
        
    def initialize_vectordb(self, data: Dict[str, pd.DataFrame]):
        """Initialize ChromaDB with ALL records from dataset (no sampling)"""
        
        self.raw_data = data
        
        try:
            self.collection = self.client.get_collection("client360")
            self.client.delete_collection("client360")
        except:
            pass
        
        self.collection = self.client.create_collection(
            name="client360",
            metadata={"description": "Client 360 data for RAG - FULL DATASET"}
        )
        
        documents = []
        metadatas = []
        ids = []
        
        doc_id = 0
        total_records = 0
        
        # Process each dataset - ALL RECORDS, NO SAMPLING
        for dataset_name, df in data.items():
            if len(df) == 0:
                continue
            
            print(f"📊 Processing {dataset_name}: {len(df)} records")
            total_records += len(df)
                
            for idx, row in df.iterrows():
                doc_text = self._create_document_text(dataset_name, row)
                
                metadata = {
                    'dataset': dataset_name,
                    'row_index': str(idx)
                }
                
                # Add ALL identifier fields to metadata
                for col in df.columns:
                    if col in ['client_id', 'le_id', 'sub_prof_id', 'customer_name', 
                               'account_id', 'loan_id', 'facility_id', 'cif_id',
                               'product_type', 'product_code', 'account_type']:
                        val = str(row[col]) if pd.notna(row[col]) else ''
                        if val:
                            metadata[col] = val
                
                documents.append(doc_text)
                metadatas.append(metadata)
                ids.append(f"{dataset_name}_{doc_id}")
                doc_id += 1
                
                # Batch insert every 500 records
                if len(documents) >= 500:
                    self.collection.add(
                        documents=documents,
                        metadatas=metadatas,
                        ids=ids
                    )
                    documents, metadatas, ids = [], [], []
        
        # Insert remaining documents
        if documents:
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
        
        print(f"\n✅ Total records indexed in vector DB: {total_records:,}")
        return True
    
    def _create_document_text(self, dataset_name: str, row: pd.Series) -> str:
        """Create searchable text from a data row with ALL fields"""
        parts = [f"Dataset: {dataset_name}"]
        
        for col, val in row.items():
            if pd.notna(val):
                parts.append(f"{col}: {val}")
        
        return " | ".join(parts)
    
    def search(self, query: str, n_results: int = 100, filters: Dict = None) -> List[Dict]:
        """Search vector database - INCREASED to 100 by default for full coverage"""
        if not self.collection:
            return []
        
        where_filter = None
        if filters:
            where_filter = {}
            for key, value in filters.items():
                if value and value != "All":
                    where_filter[key] = value
        
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter if where_filter else None
            )
            return self._format_results(results)
        except Exception as e:
            print(f"Search error: {e}")
            return []
    
    def get_all_records_for_identifier(self, identifier_type: str, identifier_value: str, 
                                       dataset_name: str = None) -> pd.DataFrame:
        """Get ALL records from raw data for a specific identifier (no limit)"""
        if not self.raw_data:
            return pd.DataFrame()
        
        results = []
        datasets_to_search = [dataset_name] if dataset_name else self.raw_data.keys()
        
        for ds_name in datasets_to_search:
            df = self.raw_data.get(ds_name, pd.DataFrame())
            if len(df) == 0:
                continue
            
            if identifier_type in df.columns:
                matched = df[df[identifier_type].astype(str) == str(identifier_value)]
                if len(matched) > 0:
                    matched_copy = matched.copy()
                    matched_copy['_dataset'] = ds_name
                    results.append(matched_copy)
        
        if results:
            return pd.concat(results, ignore_index=True)
        return pd.DataFrame()
    
    def _format_results(self, results: Dict) -> List[Dict]:
        """Format ChromaDB results"""
        formatted = []
        
        if not results['documents'] or not results['documents'][0]:
            return formatted
        
        for i, doc in enumerate(results['documents'][0]):
            formatted.append({
                'document': doc,
                'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                'distance': results['distances'][0][i] if results['distances'] else None
            })
        
        return formatted

# ============================================================================
# LANGSMITH TRACING INTEGRATION
# ============================================================================

class LangSmithTracer:
    """LangSmith integration for tracing"""
    
    def __init__(self, api_key: str, project: str = None):
        """
        Initialize LangSmith client/tracer. If project provided, pass it to the client so runs are grouped.
        """
        try:
            if api_key:
                # pass project if supported by the LangSmithClient constructor
                if project:
                    self.client = LangSmithClient(api_key=api_key, project=project)
                else:
                    self.client = LangSmithClient(api_key=api_key)
                self.enabled = True
            else:
                self.client = None
                self.enabled = False
        except Exception as e:
            # keep failure quiet and mark tracer disabled
            print("LangSmith client init error:", e)
            self.client = None
            self.enabled = False
    
    @traceable(run_type="chain", name="client360_query")
    def trace_query(self, query: str, context: str, response: str) -> Dict:
        """Trace a query through LangSmith"""
        return {
            'query': query,
            'context_length': len(context),
            'response_length': len(response),
            'timestamp': datetime.now().isoformat()
        }

# ============================================================================
# RAG QUERY ENGINE (ENHANCED WITH SMART FIELD EXTRACTION)
# ============================================================================

class RAGQueryEngine:
    """RAG-based query engine using ChromaDB + Claude - ENHANCED"""
    
    def __init__(self, vectordb: VectorDBManager, anthropic_client: Anthropic, 
                 query_analyzer: QueryAnalyzer, langsmith: LangSmithTracer = None):
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
                              requested_field: str = None) -> str:
        """
        Format exact match results - return only non-empty fields and avoid NaN outputs.
        Keeps same signature as original.
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
    
    def query(self, question: str, filters: Dict = None) -> Dict[str, Any]:
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
                    self.langsmith.trace_query(question, "Exact match lookup", answer)
                
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
            self.langsmith.trace_query(question, context, response)
        
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

# ============================================================================
# COMPREHENSIVE SUMMARY WITH DETAILED SECTIONS
# ============================================================================

def generate_comprehensive_summary(query_engine: RAGQueryEngine, 
                                  identifier_type: str, 
                                  identifier_value: str) -> str:
    """Generate detailed comprehensive summary with section-wise breakdown"""
    
    vectordb = query_engine.vectordb
    
    all_records = vectordb.get_all_records_for_identifier(identifier_type, identifier_value)
    
    if len(all_records) == 0:
        return f"# No data found for {identifier_type}: {identifier_value}"
    
    summary_parts = [f"# Comprehensive Client Intelligence Report"]
    summary_parts.append(f"**{identifier_type.upper()}:** {identifier_value}")
    summary_parts.append(f"**Report Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    summary_parts.append("\n---\n")
    
    # Section 1: Client Profile
    summary_parts.append("## 1. CLIENT PROFILE")
    client_data = all_records[all_records['_dataset'] == 'clients']
    if len(client_data) > 0:
        row = client_data.iloc[0]
        summary_parts.append(f"**Customer Name:** {row.get('customer_name', 'N/A')}")
        summary_parts.append(f"**Client ID:** {row.get('client_id', 'N/A')}")
        summary_parts.append(f"**Legal Entity (LE):** {row.get('le_id', 'N/A')}")
        summary_parts.append(f"**Customer Segment:** {row.get('cust_seg_desc', 'N/A')}")
        summary_parts.append(f"**Relationship Start Date:** {row.get('relationship_open_date', 'N/A')}")
        summary_parts.append(f"**Customer Type:** {row.get('cust_type_desc', 'N/A')}")
        summary_parts.append(f"**Risk Rating:** {row.get('risk_rating', 'N/A')}")
    else:
        summary_parts.append("**Status:** No client profile data available (N/A)")
    
    summary_parts.append("\n---\n")
    
    # Section 2: Core Banking Accounts
    summary_parts.append("## 2. CORE BANKING ACCOUNTS")
    core_data = all_records[all_records['_dataset'] == 'core']
    if len(core_data) > 0:
        summary_parts.append(f"**Total Accounts:** {len(core_data)}")
        # safe numeric conversion
        try:
            total_balance = pd.to_numeric(core_data.get('closing_balance', pd.Series([], dtype=float)), errors='coerce').fillna(0).sum()
        except Exception:
            total_balance = 0.0
        summary_parts.append(f"**Total Balance:** ${total_balance:,.2f}")
        summary_parts.append("\n**Account Details:**")
        for idx, row in core_data.iterrows():
            summary_parts.append(f"\n- **Account ID:** {row.get('account_id', 'N/A')}")
            summary_parts.append(f"  - Product: {row.get('product_desc', 'N/A')}")
            summary_parts.append(f"  - Account Type: {row.get('account_type', 'N/A')}")
            summary_parts.append(f"  - Currency: {row.get('account_ccy', 'N/A')}")
            bal = row.get('closing_balance', 0)
            try:
                bal_val = float(bal) if pd.notna(bal) else 0.0
            except Exception:
                bal_val = 0.0
            summary_parts.append(f"  - Closing Balance: ${bal_val:,.2f}")
            summary_parts.append(f"  - Status: {row.get('account_status', 'N/A')}")
    else:
        summary_parts.append("**Status:** No core banking account data available (N/A)")
    
    summary_parts.append("\n---\n")
    
    # Section 3: Loans & Credit Facilities
    summary_parts.append("## 3. LOANS & CREDIT FACILITIES")
    loans_data = all_records[all_records['_dataset'] == 'loans']
    facilities_data = all_records[all_records['_dataset'] == 'facilities']
    
    if len(loans_data) > 0:
        summary_parts.append(f"**Total Loans:** {len(loans_data)}")
        total_outstanding = pd.to_numeric(loans_data.get('outstanding_amount', pd.Series([], dtype=float)), errors='coerce').fillna(0).sum()
        summary_parts.append(f"**Total Outstanding:** ${total_outstanding:,.2f}")
        summary_parts.append("\n**Loan Details:**")
        for idx, row in loans_data.iterrows():
            summary_parts.append(f"\n- **Loan ID:** {row.get('loan_id', 'N/A')}")
            summary_parts.append(f"  - Product: {row.get('loan_product', 'N/A')}")
            out_amt = row.get('outstanding_amount', 0)
            try:
                out_val = float(out_amt) if pd.notna(out_amt) else 0.0
            except Exception:
                out_val = 0.0
            summary_parts.append(f"  - Outstanding Amount: ${out_val:,.2f}")
            summary_parts.append(f"  - Interest Rate: {row.get('interest_rate', 'N/A')}%")
            summary_parts.append(f"  - Maturity Date: {row.get('maturity_date', 'N/A')}")
            summary_parts.append(f"  - Status: {row.get('loan_status', 'N/A')}")
    else:
        summary_parts.append("**Loans Status:** No loan data available (N/A)")
    
    if len(facilities_data) > 0:
        summary_parts.append(f"\n**Total Facilities:** {len(facilities_data)}")
        summary_parts.append("\n**Facility Details:**")
        for idx, row in facilities_data.iterrows():
            summary_parts.append(f"\n- **Facility ID:** {row.get('facility_id', 'N/A')}")
            summary_parts.append(f"  - Type: {row.get('facility_type', 'N/A')}")
            lim = row.get('facility_limit', 0)
            try:
                lim_val = float(lim) if pd.notna(lim) else 0.0
            except Exception:
                lim_val = 0.0
            util = row.get('utilized_amount', 0)
            try:
                util_val = float(util) if pd.notna(util) else 0.0
            except Exception:
                util_val = 0.0
            summary_parts.append(f"  - Limit: ${lim_val:,.2f}")
            summary_parts.append(f"  - Utilized: ${util_val:,.2f}")
    else:
        summary_parts.append("\n**Facilities Status:** No facility data available (N/A)")
    
    summary_parts.append("\n---\n")
    
    # Section 4: Collateral & Securities
    summary_parts.append("## 4. COLLATERAL & SECURITIES")
    collateral_data = all_records[all_records['_dataset'] == 'collateral']
    if len(collateral_data) > 0:
        summary_parts.append(f"**Total Collateral Items:** {len(collateral_data)}")
        total_value = pd.to_numeric(collateral_data.get('collateral_value', pd.Series([], dtype=float)), errors='coerce').fillna(0).sum()
        summary_parts.append(f"**Total Collateral Value:** ${total_value:,.2f}")
        summary_parts.append("\n**Collateral Details:**")
        for idx, row in collateral_data.iterrows():
            summary_parts.append(f"\n- **Collateral ID:** {row.get('collateral_id', 'N/A')}")
            summary_parts.append(f"  - Type: {row.get('collateral_type', 'N/A')}")
            val = row.get('collateral_value', 0)
            try:
                val_f = float(val) if pd.notna(val) else 0.0
            except Exception:
                val_f = 0.0
            summary_parts.append(f"  - Value: ${val_f:,.2f}")
            summary_parts.append(f"  - Coverage: {row.get('coverage_ratio', 'N/A')}%")
    else:
        summary_parts.append("**Status:** No collateral data available (N/A)")
    
    summary_parts.append("\n---\n")
    
    # Section 5: Custody & Investments
    summary_parts.append("## 5. CUSTODY & INVESTMENTS")
    custody_data = all_records[all_records['_dataset'] == 'custody']
    if len(custody_data) > 0:
        summary_parts.append(f"**Total Custody Positions:** {len(custody_data)}")
        total_market_value = pd.to_numeric(custody_data.get('market_value', pd.Series([], dtype=float)), errors='coerce').fillna(0).sum()
        summary_parts.append(f"**Total Market Value:** ${total_market_value:,.2f}")
        summary_parts.append("\n**Position Details:**")
        for idx, row in custody_data.iterrows():
            summary_parts.append(f"\n- **Security:** {row.get('security_name', 'N/A')}")
            summary_parts.append(f"  - ISIN: {row.get('isin', 'N/A')}")
            qty = row.get('quantity', 0)
            try:
                qty_val = float(qty) if pd.notna(qty) else 0.0
            except Exception:
                qty_val = 0.0
            summary_parts.append(f"  - Quantity: {qty_val:,.0f}")
            mv = row.get('market_value', 0)
            try:
                mv_val = float(mv) if pd.notna(mv) else 0.0
            except Exception:
                mv_val = 0.0
            summary_parts.append(f"  - Market Value: ${mv_val:,.2f}")
    else:
        summary_parts.append("**Status:** No custody data available (N/A)")
    
    summary_parts.append("\n---\n")
    
    # Section 6: Fixed Deposits
    summary_parts.append("## 6. FIXED DEPOSITS (FXD)")
    fxd_data = all_records[all_records['_dataset'] == 'fxd']
    if len(fxd_data) > 0:
        summary_parts.append(f"**Total Fixed Deposits:** {len(fxd_data)}")
        total_principal = pd.to_numeric(fxd_data.get('principal_amount', pd.Series([], dtype=float)), errors='coerce').fillna(0).sum()
        summary_parts.append(f"**Total Principal:** ${total_principal:,.2f}")
        summary_parts.append("\n**Deposit Details:**")
        for idx, row in fxd_data.iterrows():
            summary_parts.append(f"\n- **Deposit ID:** {row.get('deposit_id', 'N/A')}")
            princ = row.get('principal_amount', 0)
            try:
                princ_val = float(princ) if pd.notna(princ) else 0.0
            except Exception:
                princ_val = 0.0
            summary_parts.append(f"  - Principal: ${princ_val:,.2f}")
            summary_parts.append(f"  - Interest Rate: {row.get('interest_rate', 'N/A')}%")
            summary_parts.append(f"  - Maturity Date: {row.get('maturity_date', 'N/A')}")
    else:
        summary_parts.append("**Status:** No fixed deposit data available (N/A)")
    
    summary_parts.append("\n---\n")
    
    # Section 7: Investment Funds
    summary_parts.append("## 7. INVESTMENT FUNDS")
    funds_data = all_records[all_records['_dataset'] == 'funds']
    if len(funds_data) > 0:
        summary_parts.append(f"**Total Fund Investments:** {len(funds_data)}")
        if 'current_nav' in funds_data.columns:
            total_nav = pd.to_numeric(funds_data['current_nav'], errors='coerce').fillna(0).sum()
            summary_parts.append(f"**Total NAV:** ${total_nav:,.2f}")
        else:
            summary_parts.append("**Total NAV:** Not available (column missing)")
        summary_parts.append("\n**Fund Details:**")
        for idx, row in funds_data.iterrows():
            summary_parts.append(f"\n- **Fund Name:** {row.get('fund_name', 'N/A')}")
            units = row.get('units', 0)
            try:
                units_val = float(units) if pd.notna(units) else 0.0
            except Exception:
                units_val = 0.0
            nav = row.get('current_nav', None)
            try:
                nav_val = float(nav) if nav is not None and pd.notna(nav) else None
            except Exception:
                nav_val = None
            summary_parts.append(f"  - Units: {units_val:,.2f}")
            if nav_val is not None:
                summary_parts.append(f"  - Current NAV: ${nav_val:,.2f}")
            else:
                summary_parts.append(f"  - Current NAV: Not available")
    else:
        summary_parts.append("**Status:** No fund investment data available (N/A)")
    
    summary_parts.append("\n---\n")
    
    # Section 8: Trading Activity
    summary_parts.append("## 8. TRADING ACTIVITY")
    trade_otp = all_records[all_records['_dataset'] == 'trade_otp']
    trade_dtp = all_records[all_records['_dataset'] == 'trade_dtp']
    
    if len(trade_otp) > 0 or len(trade_dtp) > 0:
        summary_parts.append(f"**OTP Trades:** {len(trade_otp)}")
        summary_parts.append(f"**DTP Trades:** {len(trade_dtp)}")
        
        if len(trade_otp) > 0:
            summary_parts.append("\n**Recent OTP Trades:**")
            for idx, row in trade_otp.head(5).iterrows():
                amt = row.get('trade_amount', 0)
                try:
                    amt_val = float(amt) if pd.notna(amt) else 0.0
                except Exception:
                    amt_val = 0.0
                summary_parts.append(f"- Trade Date: {row.get('trade_date', 'N/A')}, Amount: ${amt_val:,.2f}")
        
        if len(trade_dtp) > 0:
            summary_parts.append("\n**Recent DTP Trades:**")
            for idx, row in trade_dtp.head(5).iterrows():
                amt = row.get('trade_amount', 0)
                try:
                    amt_val = float(amt) if pd.notna(amt) else 0.0
                except Exception:
                    amt_val = 0.0
                summary_parts.append(f"- Trade Date: {row.get('trade_date', 'N/A')}, Amount: ${amt_val:,.2f}")
    else:
        summary_parts.append("**Status:** No trading activity data available (N/A)")
    
    summary_parts.append("\n---\n")
    summary_parts.append("## SUMMARY STATISTICS")
    summary_parts.append(f"**Total Data Points:** {len(all_records)} records across {all_records['_dataset'].nunique()} datasets")
    summary_parts.append(f"**Datasets with Data:** {', '.join(all_records['_dataset'].unique())}")
    
    return "\n".join(summary_parts)

# ============================================================================
# ANALYTICS FUNCTIONS
# ============================================================================

def has_section_data(df: pd.DataFrame, required_cols: list = None) -> bool:
    """
    Return True if the dataframe has at least one non-empty value in the required columns
    or any non-empty column if required_cols is None.
    Treats NaN and empty strings as empty.
    """
    if df is None or df.empty:
        return False

    # If specific columns are required, only consider those that exist
    if required_cols:
        existing = [c for c in required_cols if c in df.columns]
        if not existing:
            return False
        for c in existing:
            series = df[c]
            # drop NaN, strip empty strings and check if any remain
            non_empty = series.dropna().astype(str).str.strip().replace('', pd.NA).dropna()
            if not non_empty.empty:
                return True
        return False
    else:
        # If no required_cols specified, check if any column has data
        for c in df.columns:
            series = df[c]
            non_empty = series.dropna().astype(str).str.strip().replace('', pd.NA).dropna()
            if not non_empty.empty:
                return True
        return False

def create_analytics_dashboard(data: Dict[str, pd.DataFrame]):
    """Create comprehensive analytics dashboard"""
    
    st.subheader("📊 Key Metrics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Clients", f"{len(data['clients']):,}")
    with col2:
        total_bal = 0
        if len(data['core']) > 0 and 'closing_balance' in data['core'].columns:
            try:
                total_bal = pd.to_numeric(data['core']['closing_balance'], errors='coerce').fillna(0).sum()
            except Exception:
                total_bal = 0
        st.metric("Total Balance", f"${total_bal:,.0f}")
    with col3:
        total_loans = 0
        if len(data['loans']) > 0 and 'outstanding_amount' in data['loans'].columns:
            try:
                total_loans = pd.to_numeric(data['loans']['outstanding_amount'], errors='coerce').fillna(0).sum()
            except Exception:
                total_loans = 0
        st.metric("Total Loans", f"${total_loans:,.0f}")
    with col4:
        active_datasets = len([d for d in data.values() if len(d) > 0])
        st.metric("Active Datasets", active_datasets)
    
    st.divider()
    
    # Client Analytics
    col1, col2 = st.columns(2)
    
    with col1:
        if has_section_data(data.get('clients', pd.DataFrame()), required_cols=['cust_seg_desc']):
            st.subheader("Client Distribution by Segment")
            seg_dist = data['clients']['cust_seg_desc'].value_counts()
            if not seg_dist.empty:
                fig = px.pie(values=seg_dist.values, names=seg_dist.index,
                            title="Customer Segments")
                st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        if has_section_data(data.get('clients', pd.DataFrame()), required_cols=['cust_type_desc']):
            st.subheader("Client Type Distribution")
            type_dist = data['clients']['cust_type_desc'].value_counts()
            if not type_dist.empty:
                fig = px.bar(x=type_dist.index, y=type_dist.values,
                            title="Customer Types",
                            labels={'x': 'Type', 'y': 'Count'})
                st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    
    # Loan Analytics
    col1, col2 = st.columns(2)
    
    with col1:
        # <-- FIXED: require both columns exist before groupby to avoid KeyError
        loans_df = data.get('loans', pd.DataFrame())
        if (has_section_data(loans_df, required_cols=['loan_product', 'outstanding_amount'])
            and 'loan_product' in loans_df.columns and 'outstanding_amount' in loans_df.columns):
            st.subheader("Loans by Product Type")
            loan_by_product = loans_df.groupby('loan_product')['outstanding_amount'].sum().sort_values(ascending=False)
            if not loan_by_product.empty:
                fig = px.bar(x=loan_by_product.index, y=loan_by_product.values,
                            title="Outstanding Loans by Product",
                            labels={'x': 'Product', 'y': 'Outstanding Amount ($)'})
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        if has_section_data(data.get('loans', pd.DataFrame()), required_cols=['loan_status']):
            st.subheader("Loan Status Distribution")
            status_dist = data['loans']['loan_status'].value_counts()
            if not status_dist.empty:
                fig = px.pie(values=status_dist.values, names=status_dist.index,
                            title="Loan Status")
                st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    
    # Fixed Deposit Analysis
    col1, col2 = st.columns(2)
    
    with col1:
        if has_section_data(data.get('fxd', pd.DataFrame()), required_cols=['maturity_date', 'principal_amount']):
            st.subheader("Fixed Deposits Analysis")
            
            if 'maturity_date' in data['fxd'].columns:
                fxd_copy = data['fxd'].copy()
                fxd_copy['maturity_date'] = pd.to_datetime(fxd_copy['maturity_date'], errors='coerce')
                fxd_copy['days_to_maturity'] = (fxd_copy['maturity_date'] - pd.Timestamp.now()).dt.days
                
                fxd_copy['maturity_bucket'] = pd.cut(fxd_copy['days_to_maturity'], 
                                                      bins=[-float('inf'), 30, 90, 180, 365, float('inf')],
                                                      labels=['<30 days', '30-90 days', '90-180 days', '180-365 days', '>365 days'])
                
                maturity_analysis = fxd_copy.groupby('maturity_bucket')['principal_amount'].sum()
                if not maturity_analysis.empty:
                    fig = px.bar(x=maturity_analysis.index, y=maturity_analysis.values,
                                title="FXD by Maturity Period",
                                labels={'x': 'Maturity Period', 'y': 'Principal Amount ($)'})
                    st.plotly_chart(fig, use_container_width=True)
            
            if 'interest_rate' in data['fxd'].columns:
                fig = px.histogram(data['fxd'], x='interest_rate', 
                                  title="Interest Rate Distribution",
                                  labels={'interest_rate': 'Interest Rate (%)'})
                st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        if has_section_data(data.get('core', pd.DataFrame()), required_cols=['closing_balance', 'account_id']):
            st.subheader("Account Balance Distribution")
            
            # Protect against missing closing_balance
            if 'closing_balance' in data['core'].columns:
                top_accounts = data['core'].nlargest(10, 'closing_balance')
                if not top_accounts.empty:
                    fig = px.bar(top_accounts, x='account_id', y='closing_balance',
                                title="Top 10 Accounts by Balance",
                                labels={'account_id': 'Account ID', 'closing_balance': 'Balance ($)'})
                    fig.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True)
            
            if 'product_desc' in data['core'].columns:
                product_balance = data['core'].groupby('product_desc')['closing_balance'].sum().sort_values(ascending=False)
                if not product_balance.empty:
                    fig = px.pie(values=product_balance.values, names=product_balance.index,
                                title="Balance by Product Type")
                    st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    
    # Investment & Trading Analytics
    col1, col2 = st.columns(2)
    
    with col1:
        if has_section_data(data.get('custody', pd.DataFrame()), required_cols=['market_value', 'security_name']):
            st.subheader("Custody Holdings Analysis")
            
            if 'market_value' in data['custody'].columns and 'security_name' in data['custody'].columns:
                top_holdings = data['custody'].nlargest(10, 'market_value')
                if not top_holdings.empty:
                    fig = px.bar(top_holdings, x='security_name', y='market_value',
                                title="Top 10 Holdings by Market Value",
                                labels={'security_name': 'Security', 'market_value': 'Market Value ($)'})
                    fig.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        if has_section_data(data.get('funds', pd.DataFrame()), required_cols=['fund_name', 'current_nav']):
            st.subheader("Investment Funds Analysis")
            
            if 'fund_name' in data['funds'].columns and 'current_nav' in data['funds'].columns:
                fund_nav = data['funds'].groupby('fund_name')['current_nav'].sum().sort_values(ascending=False).head(10)
                if not fund_nav.empty:
                    fig = px.bar(x=fund_nav.index, y=fund_nav.values,
                                title="Top 10 Funds by NAV",
                                labels={'x': 'Fund Name', 'y': 'Total NAV ($)'})
                    fig.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    
    # Facility Utilization
    if has_section_data(data.get('facilities', pd.DataFrame()), required_cols=['facility_limit', 'utilized_amount']):
        st.subheader("Credit Facility Utilization")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if 'facility_limit' in data['facilities'].columns and 'utilized_amount' in data['facilities'].columns:
                facilities_copy = data['facilities'].copy()
                facilities_copy['utilization_pct'] = (facilities_copy['utilized_amount'] / facilities_copy['facility_limit'] * 100).fillna(0)
                
                fig = px.scatter(facilities_copy, x='facility_limit', y='utilization_pct',
                               size='utilized_amount', color='facility_type' if 'facility_type' in facilities_copy.columns else None,
                               title="Facility Utilization Analysis",
                               labels={'facility_limit': 'Facility Limit ($)', 'utilization_pct': 'Utilization %'})
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            if 'facility_type' in data['facilities'].columns:
                facility_type_util = data['facilities'].groupby('facility_type').agg({
                    'facility_limit': 'sum',
                    'utilized_amount': 'sum'
                })
                if not facility_type_util.empty:
                    fig = go.Figure(data=[
                        go.Bar(name='Limit', x=facility_type_util.index, y=facility_type_util['facility_limit']),
                        go.Bar(name='Utilized', x=facility_type_util.index, y=facility_type_util['utilized_amount'])
                    ])
                    fig.update_layout(barmode='group', title='Facility Limit vs Utilization by Type',
                                    xaxis_title='Facility Type', yaxis_title='Amount ($)')
                    st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    
    # Collateral Coverage
    if has_section_data(data.get('collateral', pd.DataFrame()), required_cols=['collateral_type', 'collateral_value']):
        st.subheader("Collateral Analysis")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if 'collateral_type' in data['collateral'].columns and 'collateral_value' in data['collateral'].columns:
                collateral_by_type = data['collateral'].groupby('collateral_type')['collateral_value'].sum().sort_values(ascending=False)
                if not collateral_by_type.empty:
                    fig = px.pie(values=collateral_by_type.values, names=collateral_by_type.index,
                                title="Collateral Distribution by Type")
                    st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            if 'coverage_ratio' in data['collateral'].columns:
                fig = px.histogram(data['collateral'], x='coverage_ratio',
                                 title="Coverage Ratio Distribution",
                                 labels={'coverage_ratio': 'Coverage Ratio (%)'})
                st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    st.markdown('<h1 class="main-header">🔍 Client 360 Intelligence POC</h1>', 
                unsafe_allow_html=True)
    st.markdown("**Enhanced with: ChromaDB RAG + Full Dataset Search + Smart Field Extraction + Universal Exact Lookup**")
    
    # Sidebar Configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        anthropic_key = st.text_input(
            "Anthropic API Key", 
            type="password",
            help="Required for Claude AI",
            value=os.getenv("ANTHROPIC_API_KEY", "")
        )
        
        langsmith_key = st.text_input(
            "LangSmith API Key (Optional)",
            type="password",
            help="Optional: For query tracing",
            value=os.getenv("LANGSMITH_API_KEY", "")
        )
        
        st.divider()
        
        if st.button("🚀 Initialize System", type="primary", key="init_system_btn"):
            if not anthropic_key:
                st.error("Anthropic API key required!")
            else:
                with st.spinner("Loading data and initializing vector DB..."):
                    st.session_state.data = load_all_data()
                    st.session_state.data_loaded = True
                    
                    total_records = sum(len(df) for df in st.session_state.data.values())
                    st.info(f"✅ Loaded {total_records:,} total records from {len(st.session_state.data)} datasets")
                    
                    st.session_state.vectordb = VectorDBManager()
                    st.session_state.vectordb.initialize_vectordb(st.session_state.data)
                    st.session_state.vectordb_initialized = True
                    
                    # Pass project name to LangSmithTracer
                    st.session_state.langsmith = LangSmithTracer(langsmith_key, project="Client_360_Positions_Summarize")
                    
                    st.session_state.query_analyzer = QueryAnalyzer(st.session_state.data)
                    
                    anthropic_client = Anthropic(api_key=anthropic_key)
                    st.session_state.query_engine = RAGQueryEngine(
                        st.session_state.vectordb,
                        anthropic_client,
                        st.session_state.query_analyzer,
                        st.session_state.langsmith
                    )
                    
                    st.success("✅ System initialized successfully!")
                    st.balloons()
        
        st.divider()
        
        st.subheader("📊 System Status")
        if st.session_state.data_loaded:
            total_records = sum(len(df) for df in st.session_state.data.values())
            st.write(f"✅ Data Loaded: {total_records:,} records")
        else:
            st.write("❌ Data Loaded: No")
        st.write(f"{'✅' if st.session_state.vectordb_initialized else '❌'} Vector DB: {'Ready' if st.session_state.vectordb_initialized else 'Not Ready'}")
        st.write(f"{'✅' if langsmith_key else '⚠️'} LangSmith: {'Enabled' if langsmith_key else 'Optional'}")
        
        if st.session_state.data_loaded:
            st.divider()
            st.subheader("📁 Dataset Summary")
            for name, df in st.session_state.data.items():
                if len(df) > 0:
                    st.write(f"• **{name}**: {len(df):,} records")
    
    # Main content
    if not st.session_state.vectordb_initialized:
        st.info("👈 Please initialize the system using the sidebar")
        st.markdown("""
        ### 🎯 Features:
        - ✅ **Full Dataset Search**: Searches across ALL records (not limited to 20)
        - ✅ **Smart Field Extraction**: Returns only requested field value (not full JSON)
        - ✅ **Comprehensive Summaries**: Detailed section-wise breakdowns
        - ✅ **Advanced Vector Search**: Semantic search across full indexed data
        - ✅ **Rich Analytics**: Multiple visualization charts
        - ✅ **Universal Exact Lookup**: Query ANY column, ANY dataset
        
        ### 💡 Example Queries:
        - "What is the customer name for client_id C100079?"
        - "Show me the segment for le_id LE082"
        - "What is the status for account AC001234?"
        - "Find all records for customer 'Zenith Manufacturing'"
        """)
        return
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "💬 Intelligent Q&A",
        "📋 Comprehensive Summary",
        "🔎 Advanced Search",
        "📊 Analytics"
    ])
    
    # ========================================================================
    # TAB 1: INTELLIGENT Q&A
    # ========================================================================
    with tab1:
        st.header("💬 Ask Anything About Your Data")
        
        st.markdown("""
        **Example Queries (on ANY column):**
        - "What is the customer name for client_id C100089?"
        - "Show me all records for customer 'Zenith Manufacturing Pte Ltd'"
        - "What is the status for account AC001234?"
        - "Show me loans for le_id LE001"
        - "What is the segment for client_id C100079?"
        - "Find records where facility_type is 'Term Loan'"
        """)
        
        user_question = st.text_area(
            "Your Question:",
            height=100,
            placeholder="e.g., What is the customer name for client_id C100089?"
        )
        
        col1, col2, col3 = st.columns([1, 2, 2])
        with col1:
            search_button = st.button("🔍 Search", type="primary", key="search_tab1_btn")
        with col2:
            if st.button("Clear History", key="clear_history_btn"):
                st.session_state.chat_history = []
                st.rerun()
        
        if search_button and user_question:
            with st.spinner("Searching across FULL dataset and analyzing..."):
                result = st.session_state.query_engine.query(user_question)
                
                st.markdown("### 📝 Answer")
                st.markdown(
                    f'<div class="answer-box">{result["answer"].replace(chr(10), "<br>")}</div>', 
                    unsafe_allow_html=True
                )
                
                lookup_type = result.get("lookup_type", "unknown").upper()
                st.caption(f"🔍 **Lookup Type:** {lookup_type} | 📊 **Records Found:** {result['num_results']}")
                
                if result['search_results']:
                    with st.expander(f"🔎 View Search Results ({result['num_results']} found from FULL dataset)"):
                        for i, search_result in enumerate(result['search_results'], 1):
                            st.markdown(f"**Result {i}** (from `{search_result['metadata'].get('dataset')}`)")
                            st.code(search_result['document'], language='text')
                            st.caption(f"Relevance Score: {(1 - search_result.get('distance', 0)) * 100:.1f}%")
                            st.divider()
                
                st.session_state.chat_history.append({
                    'question': user_question,
                    'answer': result['answer'],
                    'num_results': result['num_results'],
                    'lookup_type': lookup_type,
                    'timestamp': datetime.now()
                })
        
        if st.session_state.chat_history:
            st.divider()
            st.subheader("📜 Recent Query History")
            for i, chat in enumerate(reversed(st.session_state.chat_history[-5:]), 1):
                with st.expander(f"{i}. {chat['question'][:80]}" + 
                                (" [Read more]" if len(chat['question']) > 80 else "")):
                    st.markdown(f"**Question:** {chat['question']}")
                    st.markdown(f"**Answer:** {chat['answer']}")
                    st.caption(f"🕒 {chat['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} | "
                             f"📊 {chat['num_results']} results | "
                             f"🔍 {chat.get('lookup_type', 'unknown').upper()}")
    
    # ========================================================================
    # TAB 2: COMPREHENSIVE SUMMARY
    # ========================================================================
    with tab2:
        st.header("📋 Generate Comprehensive Client Summary")
        st.markdown("*Generate detailed reports with section-wise breakdown across all datasets*")
        
        col1, col2 = st.columns(2)
        
        with col1:
            identifier_type = st.selectbox(
                "Select Identifier Type",
                ["client_id", "le_id", "customer_name", "account_id", "loan_id"],
                help="Choose how to identify the client"
            )
        
        with col2:
            identifier_value = st.text_input(
                f"Enter {identifier_type}",
                placeholder=f"e.g., C100055 or LE001 or Zenith Manufacturing",
                help="Enter the exact identifier value"
            )
        
        if st.button("📊 Generate Detailed Summary", type="primary", key="generate_summary_btn"):
            if not identifier_value:
                st.error("Please enter an identifier value")
            else:
                with st.spinner("Generating comprehensive summary across all datasets..."):
                    summary = generate_comprehensive_summary(
                        st.session_state.query_engine,
                        identifier_type,
                        identifier_value
                    )
                    
                    st.markdown(summary)
                    
                    # Download button
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        st.download_button(
                            "💾 Download Summary",
                            summary,
                            file_name=f"client_summary_{identifier_value}_{datetime.now().strftime('%Y%m%d')}.md",
                            mime="text/markdown",
                            key="download_summary_btn"
                        )
    
    # ========================================================================
    # TAB 3: ADVANCED SEARCH
    # ========================================================================
    with tab3:
        st.header("🔎 Advanced Vector Search")
        st.markdown("*Semantic search with filtering across the entire*")
        search_query = st.text_input(
            "Search Query:", 
            placeholder="Enter keywords, questions, or specific criteria",
            help="Use natural language to search across all records"
        )
        
        col1, col2, col3 = st.columns(3)
        with col1:
            dataset_filter = st.selectbox(
                "Filter by Dataset", 
                ["All", "clients", "core", "loans", "facilities", "collateral", 
                 "custody", "fxd", "funds", "trade_otp", "trade_dtp"],
                help="Narrow search to specific dataset"
            )
        with col2:
            num_results = st.slider("Number of Results", 5, 50, 20,
                                   help="Maximum results to return")
        with col3:
            show_metadata = st.checkbox("Show Metadata", value=True)
        
        if st.button("🔍 Search", type="primary", key="search_tab3_btn"):
            if search_query:
                filters = {'dataset': dataset_filter} if dataset_filter != "All" else None
                
                with st.spinner(f"Searching across {dataset_filter if dataset_filter != 'All' else 'all datasets'}..."):
                    results = st.session_state.vectordb.search(
                        search_query, 
                        n_results=num_results,
                        filters=filters
                    )
                
                st.success(f"✅ Found {len(results)} results from full dataset")
                
                if len(results) > 0:
                    # Summary statistics
                    datasets_found = {}
                    for r in results:
                        ds = r['metadata'].get('dataset', 'unknown')
                        datasets_found[ds] = datasets_found.get(ds, 0) + 1
                    
                    st.info(f"📊 Results span {len(datasets_found)} dataset(s): " + 
                           ", ".join([f"{k} ({v})" for k, v in datasets_found.items()]))
                    
                    # Display results
                    for i, result in enumerate(results, 1):
                        with st.expander(f"📄 Result {i} - [{result['metadata'].get('dataset', 'unknown')}] "
                                       f"(Relevance: {(1 - result.get('distance', 0)) * 100:.1f}%)"):
                            st.code(result['document'], language='text')
                            
                            if show_metadata:
                                st.markdown("**Metadata:**")
                                st.json(result['metadata'])
                else:
                    st.warning("No results found. Try different search terms or remove filters.")
    
    # ========================================================================
    # TAB 4: ANALYTICS
    # ========================================================================
    with tab4:
        st.header("📊 Comprehensive Analytics Dashboard")
        create_analytics_dashboard(st.session_state.data)

if __name__ == "__main__":
    main()