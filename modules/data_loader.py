"""
Data Loader Module
=================
Handles loading CSV data from the data directory.
"""

import pandas as pd
import streamlit as st
from typing import Dict

DATA_PATH = "Data/ai_generated_data/upload_dataset_other_files/"

FILES = {
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


@st.cache_data
def load_all_data() -> Dict[str, pd.DataFrame]:
    """
    Load all CSV files into dataframes.
    
    Returns:
        Dict[str, pd.DataFrame]: Dictionary of datasets
    """
    data = {}
    
    for name, path in FILES.items():
        try:
            file_name = DATA_PATH + path
            data[name] = pd.read_csv(file_name)
        except FileNotFoundError:
            st.warning(f"File not found: {path}, using empty DataFrame")
            data[name] = pd.DataFrame()
    
    return data
