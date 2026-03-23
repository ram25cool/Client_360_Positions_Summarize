"""
Tab 1: Intelligent Q&A
=====================
Handles the Q&A tab functionality.
"""

import streamlit as st
from datetime import datetime


def render_qa_tab(query_engine):
    """Render the Intelligent Q&A tab"""
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
            result = query_engine.query(user_question)
            
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
