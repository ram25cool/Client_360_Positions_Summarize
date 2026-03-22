# streamlit_app.py

import os
import glob
import shutil
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
import traceback
import warnings
import logging

# === ORIGINAL IMPORTS (unchanged) ===
from langchain_community.document_loaders import DataFrameLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS, Chroma
from langchain_openai.chat_models import ChatOpenAI
from langchain_classic.chains import ConversationalRetrievalChain
from langchain_classic.memory import ConversationBufferMemory
from langchain_classic.callbacks.manager import tracing_v2_enabled

# === CONFIG ===
logging.getLogger("streamlit").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=DeprecationWarning)

load_dotenv(override=True)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("OPENAI_API_KEY not found. Please set it in .env or environment.")
    st.stop()

LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
MODEL = os.getenv("MODEL", "gpt-5-nano")
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "Client_360_Positions_Summarize")

CSV_GLOB = "Data/ai_generated_data/upload_dataset/*.csv"
INDEX_PATH = "chroma_client360_index"

st.set_page_config(page_title="Client360 RAG Chat", layout="wide")
st.title("Client360 — Build FAISS + RAG Chat (single file)")

# === LOAD & PREPARE DOCS ===
def load_and_prepare_docs():
    csv_files = glob.glob(CSV_GLOB)
    if not csv_files and os.path.exists("client_master.csv"):
        csv_files = ["client_master.csv"]

    if not csv_files:
        raise FileNotFoundError("No CSV files found. Please provide input data.")

    dfs = [pd.read_csv(f, dtype=str).fillna("") for f in csv_files]
    combined = pd.concat(dfs, ignore_index=True).astype(str)

    def row_to_text(row):
        parts = []
        if "client_id" in row:
            parts.append(f"client_id: {row['client_id']}")
        if "customer_name" in row:
            parts.append(f"customer_name: {row['customer_name']}")
        for col in row.index:
            if col not in ["client_id", "customer_name"]:
                parts.append(f"{col}: {row[col]}")
        return " | ".join(parts)

    combined["page_content"] = combined.apply(row_to_text, axis=1)
    loader = DataFrameLoader(combined, page_content_column="page_content")
    docs = loader.load()
    print(f"[load_and_prepare_docs] Loaded {len(combined)} rows, {len(docs)} docs.")
    return combined, docs


@st.cache_resource(show_spinner="Building or loading vector DB...")
def get_vectordb():
    emb = OpenAIEmbeddings()
    combined, docs = load_and_prepare_docs()
    if os.path.isdir(INDEX_PATH):
        try:
            db = Chroma(persist_directory=INDEX_PATH, embedding_function=emb)
            s = db.similarity_search("test", k=1)
            if s:
                return db
        except Exception:
            shutil.rmtree(INDEX_PATH, ignore_errors=True)

    vectordb = Chroma.from_documents(docs, embedding=emb, persist_directory=INDEX_PATH)
    vectordb.persist()
    return vectordb


def make_chain(vectordb, k=10):
    llm = ChatOpenAI(model_name=MODEL, temperature=0)
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    retriever = vectordb.as_retriever(search_kwargs={"k": k})
    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        verbose=False,
    )
    print(f"[make_chain] Created with k={k}")
    return chain


# === APP INIT ===
try:
    with st.spinner("Loading or building vector DB..."):
        vectordb = get_vectordb()
    st.success("Vector DB ready.")
except Exception as e:
    st.error(f"Error: {e}")
    st.text(traceback.format_exc())
    st.stop()

combined_df, _ = load_and_prepare_docs()
st.session_state["combined_df"] = combined_df

if "chain" not in st.session_state:
    st.session_state["chain"] = make_chain(vectordb)
    st.session_state["messages"] = []

chain = st.session_state["chain"]

# === SIDEBAR ===
with st.sidebar:
    st.header("Settings")
    st.write("Model:", MODEL)
    if LANGSMITH_API_KEY:
        st.write(f"LangSmith: ON ({LANGSMITH_PROJECT})")
    else:
        st.write("LangSmith: OFF")
    if st.button("Reset conversation"):
        for key in ["chain", "messages"]:
            st.session_state.pop(key, None)
        st.experimental_rerun()


# === FLEXIBLE LOOKUP (improved + debug enabled) ===
def flexible_lookup(query: str):
    """
    Robust flexible lookup:
    - bidirectional phrasing (what is X for Y / for Y what is X)
    - fuzzy column name mapping (exact match -> contains -> guess)
    - robust LE id normalization and matching
    """
    if "combined_df" not in st.session_state:
        return None

    df = st.session_state["combined_df"]
    q = str(query).strip()

    col_aliases = {
        "client_id": ["client_id", "client id", "clientid", "client"],
        "le_id": ["le_id", "le id", "leid", "le"],
        "customer_name": ["customer_name", "name", "client_name", "customer name", "clientname"],
        "segment": ["segment", "customer_segment", "client_segment", "market_segment"],
    }

    def find_col(alias_list):
        lc = [c.lower().strip() for c in df.columns]
        for a in alias_list:
            a_norm = a.lower().strip()
            for i, c in enumerate(df.columns):
                if lc[i] == a_norm:
                    return c
        for a in alias_list:
            a_norm = a.lower().strip()
            for c in sorted(df.columns, key=lambda x: -len(x)):
                if a_norm in c.lower():
                    return c
        return None

    def guess_col_from_text(text):
        txt = text.lower().strip()
        for c in df.columns:
            if txt in c.lower():
                return c
        for c in df.columns:
            for token in txt.split():
                if token and token in c.lower():
                    return c
        return None

    import re
    q_low = q.lower()

    pattern1 = re.search(
        r'what\s+(?:is|\'s)\s+(?:the\s+)?(?P<target>[\w\s]+?)\s+for\s+(?P<source>client id|le id|le|customer name|customer|name|client)\s*[:\-]?\s*(?P<token>["\']?[A-Za-z0-9\-_ &\.\,]{1,80}["\']?)',
        q,
        re.IGNORECASE,
    )
    pattern2 = re.search(
        r'for\s+(?P<source>client id|le id|le|customer name|customer|name|client)\s*[:\-]?\s*(?P<token>["\']?[A-Za-z0-9\-_ &\.\,]{1,80}["\']?)\s+(?:what\s+(?:is|\'s)\s+(?:the\s+)?)?(?P<target>[\w\s]+?)\??',
        q,
        re.IGNORECASE,
    )
    pattern = pattern1 or pattern2

    requested_field = None
    token = None
    source_type = None

    if pattern:
        requested_text = pattern.group("target").strip().lower()
        source_type = pattern.group("source").strip().lower()
        token = pattern.group("token").strip().strip('"\'')
        for logical, aliases in col_aliases.items():
            for a in aliases:
                if a in requested_text:
                    requested_field = logical
                    break
            if requested_field:
                break

        cid_match = re.search(r'(C\d{3,8})', token, re.IGNORECASE)
        leid_match = re.search(r'(LE[\-_]?\d{1,8})', token, re.IGNORECASE)
        if cid_match:
            token = cid_match.group(1).upper()
            source_type = "client_id"
        elif leid_match:
            token = leid_match.group(1).upper().replace("-", "").replace("_", "")
            source_type = "le_id"

    if not token:
        cid_m = re.search(r'(C\d{3,8})', q, re.IGNORECASE)
        leid_m = re.search(r'(LE[\-_]?\d{1,8})', q, re.IGNORECASE)
        name_m = re.search(r'["\']([^"\']{2,80})["\']', q)
        if cid_m:
            token = cid_m.group(1).upper()
            source_type = "client_id"
        elif leid_m:
            token = leid_m.group(1).upper().replace("-", "").replace("_", "")
            source_type = "le_id"
        elif name_m:
            token = name_m.group(1).strip()
            source_type = "customer_name"

    found = None
    match_field = None

    def find_and_match_exact(col_key, val):
        col = find_col(col_aliases.get(col_key, [col_key]))
        if not col:
            return None, None
        series = df[col].astype(str).fillna("").str.upper().str.strip()
        v = val.upper().strip()
        if col_key == "le_id":
            series = series.str.replace(r'[-_]', '', regex=True)
            v = v.replace("-", "").replace("_", "").strip()
        matched = df.loc[series == v]
        if not matched.empty:
            return matched.iloc[0], col
        return None, col

    if token and source_type == "client_id":
        found, used_col = find_and_match_exact("client_id", token)
        if found is not None:
            match_field = ("client_id", token)
    if found is None and token and source_type == "le_id":
        found, used_col = find_and_match_exact("le_id", token)
        if found is not None:
            match_field = ("le_id", token)
    if found is None and token and source_type == "customer_name":
        ncol = find_col(col_aliases["customer_name"])
        if ncol:
            matched = df.loc[df[ncol].astype(str).str.upper().str.contains(token.upper(), na=False)]
            if not matched.empty:
                found = matched.iloc[0]
                match_field = ("customer_name", token)
    if found is None and token:
        tok_up = token.upper()
        mask = pd.Series(False, index=df.index)
        for c in df.columns:
            mask = mask | df[c].astype(str).str.upper().str.contains(re.escape(tok_up), na=False)
        matched = df.loc[mask]
        if not matched.empty:
            found = matched.iloc[0]
            match_field = ("token", token)

    if found is None:
        print("[flexible_lookup] No match for token:", token)
        print("[flexible_lookup] df.columns:", list(df.columns))
        return None

    actual_requested_col = None
    if requested_field:
        actual_requested_col = find_col(col_aliases.get(requested_field, [requested_field]))
        if not actual_requested_col:
            actual_requested_col = guess_col_from_text(requested_field)

    if actual_requested_col is None:
        for logical in ["segment", "customer_name", "client_id", "le_id"]:
            for alias in col_aliases.get(logical, []):
                if alias in q_low:
                    actual_requested_col = find_col(col_aliases.get(logical, [logical]))
                    if actual_requested_col:
                        requested_field = logical
                        break
            if actual_requested_col:
                break

    print("[flexible_lookup] matched field:", match_field, "requested_field:", requested_field, "actual_col:", actual_requested_col)

    if actual_requested_col and actual_requested_col in df.columns:
        val = found.get(actual_requested_col, "")
        return f"{requested_field} for matched row ({match_field[1]}): {val}"

    summary_parts = []
    for logical in ["client_id", "le_id", "customer_name", "segment"]:
        col = find_col(col_aliases.get(logical, [logical]))
        if col and col in df.columns:
            summary_parts.append(f"{col}: {found.get(col, '')}")
    if summary_parts:
        return " | ".join(summary_parts)

    return " | ".join([f"{c}: {found.get(c,'')}" for c in df.columns[:12]])


# === CHAT UI ===
q = st.text_input("Ask a question about the data:")
show_retrieval = st.checkbox("Show retrieved docs (debug)", value=False)

if st.button("Send") and q.strip():
    with st.spinner("Thinking..."):
        try:
            flex = flexible_lookup(q)
            if flex:
                st.session_state["messages"].append(("You", q))
                st.session_state["messages"].append(("Bot", flex))
            else:
                if show_retrieval:
                    retrieved = vectordb.similarity_search(q, k=10)
                    st.markdown(f"**Retrieved {len(retrieved)} docs (preview):**")
                    for i, d in enumerate(retrieved, 1):
                        st.markdown(f"**Doc {i}:** {d.page_content[:300]}")
                out = chain({"question": q, "chat_history": []})
                resp = out.get("answer", str(out))
                st.session_state["messages"].append(("You", q))
                st.session_state["messages"].append(("Bot", resp))
        except Exception as e:
            st.error(f"Query failed: {type(e).__name__}: {e}")
            st.text(traceback.format_exc())


# === CHAT HISTORY ===
st.markdown("### Chat history")
for who, msg in st.session_state.get("messages", []):
    if who == "You":
        st.markdown(f"**You:** {msg}")
    else:
        st.markdown(f"**Bot:** {msg}")

# === DEBUG PRINTS ===
if st.checkbox("Show internal debug info (console only)"):
    print("columns:", list(st.session_state["combined_df"].columns))
    print(
        st.session_state["combined_df"]
        .loc[st.session_state["combined_df"]
        .apply(lambda r: r.astype(str).str.upper().str.contains("LE012").any(), axis=1)]
        .to_dict(orient="records")
    )
    print(
        st.session_state["combined_df"]
        .loc[st.session_state["combined_df"]["client_id"]
        .astype(str).str.contains("C100006", na=False)]
        .to_dict(orient="records")
    )

st.caption("Run: python -m streamlit run streamlit_app.py (activate env with langchain, streamlit, faiss/chroma)")
