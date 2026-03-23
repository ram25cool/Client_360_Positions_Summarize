"""
Analytics Module
=================
Functions for generating summaries and dashboards.
"""

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from typing import Dict

from .rag_engine import RAGQueryEngine
from .utils import has_section_data


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
    summary_parts.append("## SUMMARY STATISTICS")
    summary_parts.append(f"**Total Data Points:** {len(all_records)} records across {all_records['_dataset'].nunique()} datasets")
    summary_parts.append(f"**Datasets with Data:** {', '.join(all_records['_dataset'].unique())}")
    
    return "\n".join(summary_parts)


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
    
    with col2:
        if has_section_data(data.get('core', pd.DataFrame()), required_cols=['closing_balance', 'account_id']):
            st.subheader("Account Balance Distribution")
            
            if 'closing_balance' in data['core'].columns:
                top_accounts = data['core'].nlargest(10, 'closing_balance')
                if not top_accounts.empty:
                    fig = px.bar(top_accounts, x='account_id', y='closing_balance',
                                title="Top 10 Accounts by Balance",
                                labels={'account_id': 'Account ID', 'closing_balance': 'Balance ($)'})
                    fig.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True)
