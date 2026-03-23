"""
Tab 3: Advanced Search
====================
Handles the advanced vector search tab functionality.
"""

import streamlit as st


def render_search_tab(vectordb):
    """Render the Advanced Vector Search tab"""
    st.header("🔎 Advanced Vector Search")
    st.markdown("*Semantic search with filtering across the entire database*")
    
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
                results = vectordb.search(
                    search_query, 
                    n_results=num_results,
                    filters=filters
                )
                
                st.success(f"Found **{len(results)}** results")
                
                for i, result in enumerate(results, 1):
                    with st.expander(f"**Result {i}** - {result['metadata'].get('dataset', 'unknown').upper()}"):
                        st.code(result['document'], language='text')
                        
                        if show_metadata:
                            st.write("**Metadata:**")
                            st.json(result['metadata'])
                        
                        if result['distance'] is not None:
                            relevance = max(0, (1 - result['distance']) * 100)
                            st.progress(relevance / 100, text=f"Relevance: {relevance:.1f}%")
