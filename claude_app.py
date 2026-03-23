"""
Client 360 Intelligence POC
============================
Enhanced version with RAG (ChromaDB) + LangSmith Tracing

Main application entry point that orchestrates all modules.
"""

import os
import streamlit as st
from anthropic import Anthropic
from dotenv import load_dotenv

# Import modules
from modules import (
    load_all_data,
    QueryAnalyzer,
    VectorDBManager,
    LangSmithTracer,
    RAGQueryEngine,
)
from modules.ui import apply_styles
from modules.ui.tabs import (
    render_qa_tab,
    render_summary_tab,
    render_search_tab,
    render_analytics_tab,
)

# Load environment variables
load_dotenv()

# Page config
st.set_page_config(
    page_title="Client 360 Intelligence - RAG POC",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply custom styling
apply_styles()

# Initialize session state
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'vectordb_initialized' not in st.session_state:
    st.session_state.vectordb_initialized = False


def main():
    """Main application function"""
    st.markdown('<h1 class="main-header">🔍 Client 360 Intelligence POC</h1>', 
                unsafe_allow_html=True)
    st.markdown("**Enhanced with: ChromaDB RAG + Full Dataset Search + Smart Field Extraction + Universal Exact Lookup**")
    
    # ========================================================================
    # SIDEBAR: Configuration & System Status
    # ========================================================================
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
        
        # Initialize button
        if st.button("🚀 Initialize System", type="primary", key="init_system_btn"):
            if not anthropic_key:
                st.error("Anthropic API key required!")
            else:
                with st.spinner("Loading data and initializing vector DB..."):
                    # Load data
                    st.session_state.data = load_all_data()
                    st.session_state.data_loaded = True
                    
                    total_records = sum(len(df) for df in st.session_state.data.values())
                    st.info(f"✅ Loaded {total_records:,} total records from {len(st.session_state.data)} datasets")
                    
                    # Initialize vector DB
                    st.session_state.vectordb = VectorDBManager()
                    st.session_state.vectordb.initialize_vectordb(st.session_state.data)
                    st.session_state.vectordb_initialized = True
                    
                    # Initialize tracer
                    st.session_state.langsmith = LangSmithTracer(langsmith_key, project="Client_360_Positions_Summarize")
                    
                    # Initialize query analyzer
                    st.session_state.query_analyzer = QueryAnalyzer(st.session_state.data)
                    
                    # Initialize query engine
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
        
        # System Status
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
    
    # ========================================================================
    # MAIN CONTENT
    # ========================================================================
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
    
    # ========================================================================
    # TABS
    # ========================================================================
    tab1, tab2, tab3, tab4 = st.tabs([
        "💬 Intelligent Q&A",
        "📋 Comprehensive Summary",
        "🔎 Advanced Search",
        "📊 Analytics"
    ])
    
    with tab1:
        render_qa_tab(st.session_state.query_engine)
    
    with tab2:
        render_summary_tab(st.session_state.query_engine)
    
    with tab3:
        render_search_tab(st.session_state.vectordb)
    
    with tab4:
        render_analytics_tab(st.session_state.data)


if __name__ == "__main__":
    main()
