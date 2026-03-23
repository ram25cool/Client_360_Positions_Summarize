"""
UI Styles Module
================
Custom CSS styling for Streamlit app.
"""

import streamlit as st


def apply_styles():
    """Apply custom CSS styling to the app"""
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
