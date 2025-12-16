"""
STEP 1: Scan & Index Workflow Files

Recursively scans all workflow JSON files and excludes those already ingested.
"""

import os
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Set, Tuple


def load_existing_ids(jsonl_path: str) -> Set[str]:
    """
    Load existing workflow IDs/filenames from template_descriptions.jsonl
    
    Returns:
        Set of filenames already ingested
    """
    existing = set()
    
    if not os.path.exists(jsonl_path):
        return existing
    
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                # Match by 'id' field (which is the filename)
                if 'id' in entry:
                    existing.add(entry['id'])
                # Also check 'sanitized_file' field
                if 'sanitized_file' in entry:
                    existing.add(entry['sanitized_file'])
                # Also check 'filename' if present
                if 'filename' in entry:
                    existing.add(entry['filename'])
            except json.JSONDecodeError:
                continue
    
    return existing


def scan_workflow_files(
    base_dirs: List[str],
    exclude_ids: Set[str]
) -> List[Dict[str, str]]:
    """
    Recursively scan directories for workflow JSON files.
    
    Args:
        base_dirs: List of directories to scan
        exclude_ids: Set of filenames to exclude (already ingested)
    
    Returns:
        List of dicts with 'path' and 'filename' for new workflows
    """
    new_files = []
    
    for base_dir in base_dirs:
        if not os.path.exists(base_dir):
            continue
            
        for root, dirs, files in os.walk(base_dir):
            # Skip certain directories
            skip_dirs = {'chroma_db', 'generated_workflows', 'test_prompts', 
                        'test_prompts_30', '__pycache__', '.git', 'src', 'node_modules'}
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            
            for file in files:
                if not file.endswith('.json'):
                    continue
                
                # Skip if already ingested
                if file in exclude_ids:
                    continue
                
                filepath = os.path.join(root, file)
                
                # Quick validation: must be a valid JSON with nodes
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if 'nodes' not in data:
                        continue
                except (json.JSONDecodeError, IOError):
                    continue
                
                new_files.append({
                    'path': filepath,
                    'filename': file,
                    'abs_path': os.path.abspath(filepath)
                })
    
    return new_files


def get_file_hash(filepath: str) -> str:
    """Generate SHA256 hash of file content for deduplication."""
    with open(filepath, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def scan_and_index(
    project_root: str,
    existing_jsonl: str = 'template_descriptions.jsonl'
) -> Tuple[List[Dict[str, str]], int, int]:
    """
    Main function to scan and index all new workflow files.
    
    Returns:
        (new_workflow_files, total_scanned, already_exists_count)
    """
    # Load existing IDs
    jsonl_path = os.path.join(project_root, existing_jsonl)
    existing_ids = load_existing_ids(jsonl_path)
    
    print(f"[SCAN] Found {len(existing_ids)} existing workflows in {existing_jsonl}")
    
    # Directories to scan
    scan_dirs = [
        project_root,  # Root directory (has ~130 JSONs)
        os.path.join(project_root, 'workflows'),  # Subfolders
    ]
    
    # Scan for new files
    new_files = scan_workflow_files(scan_dirs, existing_ids)
    
    # Deduplicate by hash
    seen_hashes = set()
    unique_files = []
    duplicates = 0
    
    for f in new_files:
        file_hash = get_file_hash(f['path'])
        if file_hash not in seen_hashes:
            seen_hashes.add(file_hash)
            f['hash'] = file_hash
            unique_files.append(f)
        else:
            duplicates += 1
    
    print(f"[SCAN] Found {len(unique_files)} new unique workflows")
    print(f"[SCAN] Skipped {len(existing_ids)} already ingested")
    print(f"[SCAN] Skipped {duplicates} duplicates")
    
    return unique_files, len(unique_files) + len(existing_ids), len(existing_ids)


if __name__ == "__main__":
    # Test the scanner
    import sys
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    new_files, total, existing = scan_and_index(project_root)
    
    print(f"\n[RESULT] New workflows to process: {len(new_files)}")
    if new_files:
        print("\nFirst 10 new files:")
        for f in new_files[:10]:
            print(f"  - {f['filename']}")










