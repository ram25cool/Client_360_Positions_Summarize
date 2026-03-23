"""
Vector Database Module
=====================
Manages ChromaDB for RAG (Retrieval Augmented Generation).
"""

import chromadb
from chromadb.config import Settings
import pandas as pd
from typing import Dict, List, Optional


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
                                       dataset_name: Optional[str] = None) -> pd.DataFrame:
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
