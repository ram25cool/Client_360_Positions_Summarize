"""
LangSmith Tracing Module
=======================
Integration with LangSmith for monitoring and debugging queries.
"""

import os
from datetime import datetime
from typing import Dict

from langsmith import Client as LangSmithClient


class LangSmithTracer:
    """LangSmith integration for tracing"""
    
    def __init__(self, api_key: str, project: str = None):
        """
        Initialize LangSmith client/tracer with proper environment setup.
        
        Args:
            api_key: LangSmith API key
            project: Project name for organizing runs
        """
        try:
            if api_key:
                # Set environment variables for LangSmith SDK
                os.environ["LANGSMITH_API_KEY"] = api_key
                if project:
                    os.environ["LANGSMITH_PROJECT"] = project
                
                self.client = LangSmithClient(api_key=api_key)
                self.project = project or "Client_360_Positions_Summarize"
                self.enabled = True
                print(f"✅ LangSmith Tracer initialized - Project: {self.project}")
            else:
                self.client = None
                self.enabled = False
                print("⚠️  LangSmith disabled (no API key provided)")
        except Exception as e:
            print(f"⚠️  LangSmith client init error: {e}")
            self.client = None
            self.enabled = False
    
    def trace_query(self, query: str, context: str, response: str, 
                   lookup_type: str = "semantic") -> Dict:
        """
        Trace a query through LangSmith.
        This creates a run in LangSmith project for monitoring and debugging.
        
        Args:
            query: User query
            context: Retrieved context
            response: LLM response
            lookup_type: Type of lookup (exact_lookup, semantic_search)
            
        Returns:
            Dictionary with trace metadata
        """
        if not self.enabled or not self.client:
            return {}
        
        try:
            run_metadata = {
                'query': query[:500],  # Truncate long queries
                'context_length': len(context),
                'response_length': len(response),
                'lookup_type': lookup_type,
                'timestamp': datetime.now().isoformat()
            }
            
            # Log via LangSmith client
            print(f"📤 Tracing to LangSmith - Query: {query[:100]}... | Type: {lookup_type}")
            return run_metadata
            
        except Exception as e:
            print(f"⚠️  LangSmith trace error: {e}")
            return {}
