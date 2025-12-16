import json
import os
import chromadb
from chromadb.utils import embedding_functions
import pandas as pd
from typing import List, Dict, Any
import glob

# Import metadata utilities
from metadata_utils import infer_services_from_workflow, infer_categories_from_workflow

# Configuration
DATA_DIR = "."  # Root directory where json/jsonl files are
DB_PATH = "./chroma_db"
COLLECTION_NAME = "n8n_workflows"

def load_data() -> List[Dict]:
    """
    Reads template_descriptions.jsonl and pairs it with raw JSON content.
    Returns a list of dicts ready for processing.
    """
    descriptions_path = os.path.join(DATA_DIR, "template_descriptions.jsonl")
    
    if not os.path.exists(descriptions_path):
        raise FileNotFoundError(f"Could not find {descriptions_path}")

    print(f"Loading metadata from {descriptions_path}...")
    print(f"Scanning for v1 templates in: {os.path.abspath(DATA_DIR)}")
    
    # Read JSONL
    data = []
    try:
        with open(descriptions_path, 'r', encoding='utf-8-sig') as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    # Skip lines that look like binary data or garbage
                    if not line.startswith('{'):
                        continue
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        data.append(obj)
                except json.JSONDecodeError:
                    print(f"Skipping invalid JSON on line {i+1}")
                    continue
    except UnicodeDecodeError:
        # Fallback for mixed encoding files
        print("UTF-8 SIG failed, trying permissive encoding...")
        with open(descriptions_path, 'r', encoding='latin-1') as f:
             for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                if not line.startswith('{'):
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        data.append(obj)
                except:
                    continue

    print(f"Found {len(data)} valid workflow descriptions.")
    return data

def extract_node_metadata(json_path: str) -> Dict[str, Any]:
    """
    Analyzes the workflow JSON to extract detailed node usage,
    including services and categories.
    """
    defaults = {
        "has_ai": False,
        "triggers": [],
        "destinations": [],
        "services": [],
        "categories": []
    }
    
    if not os.path.exists(json_path):
        return defaults
        
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            wf = json.load(f)
            
        nodes = wf.get('nodes', [])
        if not isinstance(nodes, list):
            return defaults
            
        has_ai = False
        triggers = set()
        destinations = set()
        
        # Node type keywords for destinations
        dest_keywords = {
            "googlesheets": "googleSheets",
            "slack": "slack",
            "hubspot": "hubspot",
            "mysql": "mySql",
            "airtable": "airtable",
            "odoo": "odoo",
            "onfleet": "onfleet",
            "zendesk": "zendesk",
            "mautic": "mautic",
            "telegram": "telegram",
            "discord": "discord"
        }
        
        # AI keywords
        ai_keywords = ["openai", "aiagent", "chainllm", "chatgpt", "llm"]
        
        for node in nodes:
            node_type = node.get("type", "").lower()
            node_name = node.get("name", "").lower()
            
            # Check AI
            is_ai = False
            # 1. Direct match in type or name
            if any(k in node_type for k in ai_keywords) or any(k in node_name for k in ai_keywords):
                is_ai = True
            # 2. Variations like "ai agent", "ai-agent"
            elif "ai agent" in node_name or "ai-agent" in node_name:
                is_ai = True
            # 3. Special case for noOp AI nodes
            elif "noop" in node_type and ("ai" in node_name or "agent" in node_name):
                is_ai = True
                
            if is_ai:
                has_ai = True
                
            # Check Triggers
            if "trigger" in node_type or "webhook" in node_type or "cron" in node_type:
                # Store the full type or a simplifed version
                # Here we just store the type name found in the file
                # e.g. "n8n-nodes-base.shopifyTrigger" -> "shopifytrigger"
                # But let's keep it a bit cleaner: take the last part
                short_type = node_type.split('.')[-1]
                triggers.add(short_type)
                
            # Check Destinations
            for key, label in dest_keywords.items():
                if key in node_type:
                    destinations.add(label)
        
        # Extract services and categories using the new helpers
        services = infer_services_from_workflow(wf)
        categories = infer_categories_from_workflow(wf, services)
                    
        return {
            "has_ai": has_ai,
            "triggers": list(triggers),
            "destinations": list(destinations),
            "services": services,
            "categories": categories
        }
            
    except Exception as e:
        print(f"Error parsing {json_path}: {e}")
        return defaults

def prepare_chunks(data: List[Dict]) -> List[Dict]:
    """
    Converts raw data into chunks for embedding.
    Strategy: Combine Title, One-Liner, and Summary into a single semantic chunk.
    """
    chunks = []
    
    for item in data:
        # Construct the text to embed
        # We focus on what the workflow DOES, so semantic search finds it.
        text_content = f"""
Title: {item.get('title', '')}
One Liner: {item.get('one_liner', '')}
Summary: {item.get('long_summary', '')}
Integrations: {", ".join(item.get('integrations', []))}
Steps: {", ".join(item.get('steps', []))}
        """.strip()

        # Enriched metadata
        json_path = os.path.join(DATA_DIR, item.get("sanitized_file", ""))
        node_meta = extract_node_metadata(json_path)

        # Metadata for filtering/retrieval
        # Chroma metadata must be primitives (str, int, float, bool)
        # We join lists into strings
        metadata = {
            "id": item.get('id', 'unknown'),
            "filename": item.get('sanitized_file', ''),
            "integrations": ",".join(item.get('integrations', [])), 
            "tags": ",".join(item.get('tags', [])),
            
            # Existing fields
            "has_ai": node_meta["has_ai"],
            "triggers": ",".join(node_meta["triggers"]),
            "destinations": ",".join(node_meta["destinations"]),
            
            # New fields: services and categories
            "services": ",".join(node_meta["services"]),
            "categories": ",".join(node_meta["categories"])
        }

        chunks.append({
            "id": item.get('id'),
            "text": text_content,
            "metadata": metadata
        })
        
    return chunks

def ingest():
    # 1. Load Data
    raw_data = load_data()
    
    # 2. Prepare Chunks
    chunks = prepare_chunks(raw_data)
    
    # 3. Initialize ChromaDB (Local persistent)
    print(f"Initializing Vector DB at {DB_PATH}...")
    client = chromadb.PersistentClient(path=DB_PATH)
    
    # Delete if exists to start fresh (for dev)
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"Deleted existing collection '{COLLECTION_NAME}' to ensure fresh ingest.")
    except Exception as e:
        print(f"Collection clean start (or not found): {e}")
        
    # Create collection
    # Default embedding function is all-MiniLM-L6-v2 (runs locally, no API key needed)
    collection = client.create_collection(name=COLLECTION_NAME)
    
    print(f"Embedding and indexing {len(chunks)} items...")
    
    # 4. Add to DB
    # ChromaDB add can handle lists, but for better error handling/progress we can batch if needed.
    # For <1000 items, one shot is fine.
    
    if chunks:
        collection.add(
            documents=[c['text'] for c in chunks],
            metadatas=[c['metadata'] for c in chunks],
            ids=[c['id'] for c in chunks]
        )
        print("Ingestion complete! Data stored in ./chroma_db")
    else:
        print("No chunks to ingest.")

if __name__ == "__main__":
    ingest()
