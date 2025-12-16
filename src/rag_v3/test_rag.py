"""
RAG V3 Test Script

Test the V3 vector store with sample queries.
"""

import sys
import os
import chromadb
from typing import List, Dict, Any, Tuple

# Configuration
DB_PATH = "./chroma_db"
COLLECTION_NAME_V3 = "n8n_workflows_v3"


def get_v3_collection():
    """Get the V3 ChromaDB collection."""
    client = chromadb.PersistentClient(path=DB_PATH)
    return client.get_collection(name=COLLECTION_NAME_V3)


def search_v3(query: str, top_k: int = 5) -> List[Tuple[str, Dict, float]]:
    """
    Search the V3 collection.
    
    Returns:
        List of (document, metadata, distance) tuples
    """
    collection = get_v3_collection()
    
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )
    
    # Unpack results
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    
    # Convert distance to similarity score (lower distance = higher similarity)
    # ChromaDB uses L2 distance by default
    output = []
    for doc, meta, dist in zip(documents, metadatas, distances):
        # Convert distance to similarity (approximate)
        similarity = 1 / (1 + dist)
        output.append((doc, meta, similarity))
    
    return output


def safe_print(text: str):
    """Print text safely, removing problematic characters."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Remove non-ASCII characters
        safe_text = text.encode('ascii', 'ignore').decode('ascii')
        print(safe_text)


def print_results(query: str, results: List[Tuple[str, Dict, float]]):
    """Pretty print search results."""
    safe_print(f"\n{'='*70}")
    safe_print(f"Query: {query}")
    safe_print(f"{'='*70}\n")
    
    for i, (doc, meta, score) in enumerate(results):
        filename = meta.get('filename', 'Unknown')
        title = meta.get('title', 'No title')
        trigger = meta.get('trigger_type', 'unknown')
        integrations = meta.get('integrations', '')
        categories = meta.get('categories', '')
        node_count = meta.get('node_count', 0)
        
        safe_print(f"[{i+1}] {filename}")
        safe_print(f"    Title: {title}")
        safe_print(f"    Score: {score:.4f}")
        safe_print(f"    Trigger: {trigger} | Nodes: {node_count}")
        safe_print(f"    Integrations: {integrations}")
        safe_print(f"    Categories: {categories}")
        print()


def run_tests():
    """Run a series of test queries."""
    
    test_queries = [
        "When a Telegram message is received, reply with hello",
        "Send a Slack notification when a new Shopify order comes in",
        "Sync Google Sheets data to Airtable on a schedule",
        "When a new GitHub issue is created, post to Discord",
        "Process incoming webhooks and store data in PostgreSQL",
        "Email notification when a form is submitted",
        "OpenAI chatbot with Telegram",
        "Convert Excel file to Google Sheets",
        "Monitor RSS feed and post to Slack",
        "WooCommerce order to Google Sheets",
    ]
    
    print("\n" + "="*70)
    print(" RAG V3 TEST RESULTS")
    print("="*70)
    
    # Get collection stats
    collection = get_v3_collection()
    count = collection.count()
    print(f"\nCollection: {COLLECTION_NAME_V3}")
    print(f"Total workflows: {count}")
    
    for query in test_queries:
        try:
            results = search_v3(query, top_k=3)
            print_results(query, results)
        except Exception as e:
            print(f"\n[ERROR] Query failed: {query}")
            print(f"  Error: {e}\n")


def interactive_mode():
    """Interactive query mode."""
    print("\n" + "="*70)
    print(" RAG V3 INTERACTIVE MODE")
    print("="*70)
    print("\nType a query and press Enter. Type 'quit' to exit.\n")
    
    while True:
        try:
            query = input("Query> ").strip()
            if query.lower() in ('quit', 'exit', 'q'):
                break
            if not query:
                continue
            
            results = search_v3(query, top_k=5)
            print_results(query, results)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[ERROR] {e}")
    
    print("\nGoodbye!")


if __name__ == "__main__":
    # Change to project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--interactive" or sys.argv[1] == "-i":
            interactive_mode()
        else:
            # Single query mode
            query = " ".join(sys.argv[1:])
            results = search_v3(query, top_k=5)
            print_results(query, results)
    else:
        # Run standard tests
        run_tests()

