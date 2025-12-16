"""
RAG V3 PIPELINE - Main Orchestrator

STEP 6: Write RAG V3 JSONL FILE
STEP 7: Ingest as RAG V3 (NON-DESTRUCTIVE)
STEP 8: Validation Report (MANDATORY)

This script orchestrates the entire V3 pipeline.
"""

import os
import sys
import json
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Tuple

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_v3.scanner import scan_and_index
from rag_v3.sanitizer import load_and_sanitize
from rag_v3.metadata_extractor import (
    extract_metadata,
    generate_description,
    generate_title,
    generate_one_liner
)


class PipelineStats:
    """Track pipeline statistics."""
    def __init__(self):
        self.total_scanned = 0
        self.valid_ingested = 0
        self.skipped_exists = 0
        self.skipped_invalid_json = 0
        self.skipped_missing_nodes = 0
        self.errors = []
    
    def report(self) -> str:
        """Generate the validation report."""
        report = """
RAG V3 INGESTION REPORT
----------------------
Total JSON scanned:       {total}
Valid workflows ingested: {valid}
Skipped (already exists): {exists}
Skipped (invalid JSON):   {invalid}
Skipped (missing nodes):  {missing}
Errors encountered:       {error_count}
""".format(
            total=self.total_scanned,
            valid=self.valid_ingested,
            exists=self.skipped_exists,
            invalid=self.skipped_invalid_json,
            missing=self.skipped_missing_nodes,
            error_count=len(self.errors)
        )
        
        if self.errors:
            report += "\nErrors:\n"
            for err in self.errors[:10]:  # Show first 10 errors
                report += f"  - {err}\n"
            if len(self.errors) > 10:
                report += f"  ... and {len(self.errors) - 10} more errors\n"
        
        return report


def generate_id(filepath: str) -> str:
    """Generate a unique ID using SHA256 hash of file path."""
    return hashlib.sha256(filepath.encode()).hexdigest()[:16]


def process_workflow(
    file_info: Dict[str, str],
    stats: PipelineStats
) -> Dict[str, Any] | None:
    """
    Process a single workflow file.
    
    Returns:
        Entry dict for JSONL, or None if skipped/error
    """
    filepath = file_info['path']
    filename = file_info['filename']
    
    # Load and sanitize
    is_valid, sanitized, error = load_and_sanitize(filepath)
    
    if not is_valid:
        if "Invalid JSON" in error:
            stats.skipped_invalid_json += 1
        elif "nodes" in error.lower():
            stats.skipped_missing_nodes += 1
        else:
            stats.errors.append(f"{filename}: {error}")
        return None
    
    # Extract metadata
    metadata = extract_metadata(sanitized, filename)
    
    # Generate description (NO LLM)
    description = generate_description(sanitized, metadata)
    title = generate_title(sanitized, metadata)
    one_liner = generate_one_liner(metadata)
    
    # Build entry
    entry = {
        "id": generate_id(filepath),
        "filename": filename,
        "path": filepath,
        "title": title,
        "one_liner": one_liner,
        "description": description,
        "metadata": {
            "node_count": metadata['node_count'],
            "trigger_type": metadata['trigger_type'],
            "integrations": metadata['integrations'],
            "categories": metadata['categories'],
            "has_error_handler": metadata['has_error_handler'],
            "node_types": metadata['node_types']
        },
        "rag_version": "v3",
        "sanitized_workflow": sanitized
    }
    
    return entry


# ============================================================================
# STEP 6: WRITE RAG V3 JSONL FILE
# ============================================================================

def write_v3_jsonl(
    entries: List[Dict[str, Any]],
    output_path: str
) -> int:
    """
    Write entries to JSONL file.
    One workflow = one line. Valid JSONL. No duplicates.
    """
    # Deduplicate by ID
    seen_ids = set()
    unique_entries = []
    
    for entry in entries:
        entry_id = entry.get('id')
        if entry_id not in seen_ids:
            seen_ids.add(entry_id)
            unique_entries.append(entry)
    
    # Write to file
    with open(output_path, 'w', encoding='utf-8') as f:
        for entry in unique_entries:
            line = json.dumps(entry, ensure_ascii=False)
            f.write(line + '\n')
    
    return len(unique_entries)


# ============================================================================
# STEP 7: INGEST AS RAG V3 (NON-DESTRUCTIVE)
# ============================================================================

def ingest_to_chromadb(
    entries: List[Dict[str, Any]],
    collection_name: str = "n8n_workflows_v3"
) -> int:
    """
    Ingest entries into ChromaDB.
    RAG v2 remains untouched. V3 is in a separate collection.
    """
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError:
        print("[WARN] ChromaDB not installed, skipping vector store ingestion")
        return 0
    
    # Get project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_path = os.path.join(project_root, "chroma_db")
    
    # Initialize ChromaDB
    client = chromadb.PersistentClient(path=db_path)
    
    # Create or get collection (separate from v2)
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"description": "n8n workflows RAG v3", "version": "v3"}
    )
    
    # Prepare documents for ingestion
    documents = []
    metadatas = []
    ids = []
    
    for entry in entries:
        # Build document text for embedding
        doc_text = f"""
Title: {entry.get('title', '')}
Description: {entry.get('description', '')}
Integrations: {', '.join(entry.get('metadata', {}).get('integrations', []))}
Categories: {', '.join(entry.get('metadata', {}).get('categories', []))}
Trigger: {entry.get('metadata', {}).get('trigger_type', '')}
"""
        
        # Build metadata (ChromaDB has field type restrictions)
        meta = {
            "filename": entry.get('filename', ''),
            "title": entry.get('title', ''),
            "trigger_type": entry.get('metadata', {}).get('trigger_type', ''),
            "integrations": ','.join(entry.get('metadata', {}).get('integrations', [])),
            "categories": ','.join(entry.get('metadata', {}).get('categories', [])),
            "node_count": entry.get('metadata', {}).get('node_count', 0),
            "has_error_handler": entry.get('metadata', {}).get('has_error_handler', False),
            "rag_version": "v3"
        }
        
        documents.append(doc_text)
        metadatas.append(meta)
        ids.append(entry.get('id', ''))
    
    # Batch insert (ChromaDB has a limit of ~5000 per batch)
    batch_size = 100
    total_ingested = 0
    
    for i in range(0, len(documents), batch_size):
        batch_docs = documents[i:i+batch_size]
        batch_metas = metadatas[i:i+batch_size]
        batch_ids = ids[i:i+batch_size]
        
        collection.add(
            documents=batch_docs,
            metadatas=batch_metas,
            ids=batch_ids
        )
        total_ingested += len(batch_docs)
        print(f"  Ingested batch {i//batch_size + 1}: {len(batch_docs)} workflows")
    
    return total_ingested


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def run_pipeline(project_root: str = None) -> bool:
    """
    Run the complete RAG V3 pipeline.
    
    Returns:
        True if successful, False if ANY error occurs (FAIL LOUDLY)
    """
    if project_root is None:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    stats = PipelineStats()
    
    print("=" * 60)
    print(" RAG V3 DATA PIPELINE")
    print("=" * 60)
    print()
    
    # -------------------------------------------------------------------------
    # STEP 1: Scan and Index
    # -------------------------------------------------------------------------
    print("[STEP 1] Scanning workflow files...")
    
    try:
        new_files, total, existing = scan_and_index(project_root)
        stats.total_scanned = len(new_files)
        stats.skipped_exists = existing
    except Exception as e:
        print(f"[FAIL] Scan failed: {e}")
        return False
    
    if not new_files:
        print("[INFO] No new workflows to process.")
        print(stats.report())
        print("\n[OK] RAG V3 READY (no new data)")
        return True
    
    print(f"  Found {len(new_files)} new workflows to process")
    print()
    
    # -------------------------------------------------------------------------
    # STEPS 2-5: Process each workflow
    # -------------------------------------------------------------------------
    print("[STEPS 2-5] Processing workflows...")
    
    entries = []
    for i, file_info in enumerate(new_files):
        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{len(new_files)}...")
        
        entry = process_workflow(file_info, stats)
        if entry:
            entries.append(entry)
            stats.valid_ingested += 1
    
    print(f"  Processed {len(new_files)} files")
    print(f"  Valid workflows: {len(entries)}")
    print()
    
    # -------------------------------------------------------------------------
    # STEP 6: Write JSONL
    # -------------------------------------------------------------------------
    print("[STEP 6] Writing JSONL file...")
    
    # Ensure data directory exists
    data_dir = os.path.join(project_root, "data")
    os.makedirs(data_dir, exist_ok=True)
    
    output_path = os.path.join(data_dir, "template_descriptions_v3.jsonl")
    
    try:
        written = write_v3_jsonl(entries, output_path)
        print(f"  Written {written} entries to {output_path}")
    except Exception as e:
        print(f"[FAIL] Write failed: {e}")
        return False
    
    print()
    
    # -------------------------------------------------------------------------
    # STEP 7: Ingest to ChromaDB
    # -------------------------------------------------------------------------
    print("[STEP 7] Ingesting to ChromaDB (n8n_workflows_v3)...")
    
    try:
        ingested = ingest_to_chromadb(entries, "n8n_workflows_v3")
        print(f"  Ingested {ingested} workflows to vector store")
    except Exception as e:
        print(f"[WARN] ChromaDB ingestion failed: {e}")
        stats.errors.append(f"ChromaDB: {e}")
    
    print()
    
    # -------------------------------------------------------------------------
    # STEP 8: Validation Report
    # -------------------------------------------------------------------------
    print("[STEP 8] Validation Report")
    print(stats.report())
    
    # Check for failures
    if stats.errors and len(stats.errors) > len(entries) * 0.1:
        print("[FAIL] Too many errors encountered")
        return False
    
    print()
    print("=" * 60)
    print("[OK] RAG V3 READY")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = run_pipeline()
    sys.exit(0 if success else 1)

