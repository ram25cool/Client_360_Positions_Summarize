"""
Tab 2: Comprehensive Summary
===========================
Handles the comprehensive summary tab functionality.
"""

import streamlit as st
from datetime import datetime
from modules.analytics import generate_comprehensive_summary


def render_summary_tab(query_engine):
    """Render the Comprehensive Summary tab"""
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
                    query_engine,
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
