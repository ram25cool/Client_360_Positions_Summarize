"""
Tab 4: Analytics Dashboard
=========================
Handles the analytics dashboard tab functionality.
"""

import streamlit as st
from modules.analytics import create_analytics_dashboard


def render_analytics_tab(data):
    """Render the Analytics tab"""
    st.header("📊 Analytics Dashboard")
    st.markdown("*Comprehensive analytics and visualizations across all datasets*")
    
    create_analytics_dashboard(data)
