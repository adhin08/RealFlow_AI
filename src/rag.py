import chromadb
import sys
import os
import re
from typing import List, Dict, Any, Tuple

# Import metadata utilities for reranking
from metadata_utils import (
    extract_services_from_query,
    infer_desired_categories_from_query,
    rerank_by_service_and_category
)

# Configuration
DB_PATH = "./chroma_db"
COLLECTION_NAME = "n8n_workflows"
COLLECTION_NAME_V3 = "n8n_workflows_v3"
OUTPUT_FILE = "last_prompt.txt"

# Use V3 by default if available, or set RAG_VERSION=v2 to use old collection
RAG_VERSION = os.environ.get("RAG_VERSION", "v3")

def get_retriever(version: str = None):
    """Get ChromaDB collection. Use version='v2' or 'v3', or auto-detect."""
    client = chromadb.PersistentClient(path=DB_PATH)
    
    if version is None:
        version = RAG_VERSION
    
    collection_name = COLLECTION_NAME_V3 if version == "v3" else COLLECTION_NAME
    
    try:
        return client.get_collection(name=collection_name)
    except Exception:
        # Fallback to V2 if V3 doesn't exist
        return client.get_collection(name=COLLECTION_NAME)

def select_relevant_results(query: str, metadatas: List[Dict[str, Any]], documents: List[str], ids: List[str], max_final: int = 3):
    """
    Post-process raw Chroma results to enforce simple constraints like:
    - If query mentions Slack, ensure at least one Slack workflow.
    - If query mentions Shopify, ensure at least one Shopify workflow.
    - If query mentions MySQL, ensure at least one MySQL workflow.
    - If query mentions AI/summarize/classify, ensure at least one AI workflow.

    Returns filtered (ids, documents, metadatas) lists of length <= max_final.
    """
    query_lower = query.lower()
    need_slack = "slack" in query_lower
    need_shopify = "shopify" in query_lower
    need_mysql = "mysql" in query_lower
    need_ai = any(word in query_lower for word in [" ai", "ai ", "llm", "summarize", "classify"])

    # Track first candidate index that can satisfy each need
    slack_idx = None
    shopify_idx = None
    mysql_idx = None
    ai_idx = None

    # Pre-scan all candidates
    for i, meta in enumerate(metadatas):
        dest = str(meta.get("destinations", "")).lower()
        trig = str(meta.get("triggers", "")).lower()
        integrations = str(meta.get("integrations", "")).lower()
        has_ai_meta = str(meta.get("has_ai", "")).lower()

        if slack_idx is None and "slack" in dest:
            slack_idx = i
        
        if shopify_idx is None and ("shopify" in integrations or "shopifytrigger" in trig):
            shopify_idx = i
            
        if mysql_idx is None and "mysql" in dest:
            mysql_idx = i
            
        if ai_idx is None and (has_ai_meta == "true" or has_ai_meta == "1"):
            ai_idx = i

    # 1. Identify indices we absolutely want to include
    forced_indices = set()
    if need_slack and slack_idx is not None: forced_indices.add(slack_idx)
    if need_shopify and shopify_idx is not None: forced_indices.add(shopify_idx)
    if need_mysql and mysql_idx is not None: forced_indices.add(mysql_idx)
    if need_ai and ai_idx is not None: forced_indices.add(ai_idx)

    # 2. Define base preference order (original ranking 0, 1, 2...)
    base_indices = list(range(len(metadatas)))

    # 3. Construct final list
    # Start with forced indices, sorted by their original rank (so best matches come first among forced)
    final_indices = sorted(list(forced_indices))

    # Fill remaining slots with top-ranked base indices
    for idx in base_indices:
        if len(final_indices) >= max_final:
            break
        if idx not in final_indices:
            final_indices.append(idx)

    # 4. Final Trim (Edge Case Handling)
    # If forced indices > max_final (rare), we keep the lowest-ranked ones (best matches).
    # Sorting ensures we respect original relevance ranking.
    final_indices = sorted(final_indices)[:max_final]

    sel_ids = [ids[i] for i in final_indices]
    sel_docs = [documents[i] for i in final_indices]
    sel_metas = [metadatas[i] for i in final_indices]

    return sel_ids, sel_docs, sel_metas

def has_any_ai_workflow(metadatas: List[Dict[str, Any]]) -> bool:
    """Helper to check if any AI workflow is present in the current results"""
    for meta in metadatas:
        val = str(meta.get("has_ai", "")).lower()
        if val in ("true", "1", "yes"):
            return True
    return False

def search_workflows(query: str, n_results: int = 3):
    collection = get_retriever()
    
    print(f"\nSearching for: '{query}'...")
    
    # Increase initial fetch to allow for post-filtering
    fetch_k = 10
    
    results = collection.query(
        query_texts=[query],
        n_results=fetch_k
    )
    
    if not results['documents']:
        return []
        
    documents = results['documents'][0]
    metadatas = results['metadatas'][0]
    ids = results['ids'][0]
    # We lose distance mapping with simple re-ranking unless we track it
    
    # --- PART 2: Check for missing AI ---
    query_lower = query.lower()
    need_ai = any(word in query_lower for word in [" ai", "ai ", "llm", "summarize", "summary", "summarise", "classify"])
    
    has_ai_in_initial = has_any_ai_workflow(metadatas)
    
    # --- PART 3: Run backup query if needed ---
    if need_ai and not has_ai_in_initial:
        print("  > 'AI' requested but no AI workflow found in top results. Running backup query...")
        ai_results = collection.query(
            query_texts=[query],
            n_results=5,
            where={"has_ai": True}, # Chroma filter syntax
        )
        
        if ai_results["documents"] and ai_results["documents"][0]:
            ai_docs = ai_results["documents"][0]
            ai_metas = ai_results["metadatas"][0]
            ai_ids = ai_results["ids"][0]
            
            # Merge logic
            existing_ids = set(ids)
            for i, ai_id in enumerate(ai_ids):
                if ai_id in existing_ids:
                    continue
                
                # Append new candidates
                ids.append(ai_id)
                documents.append(ai_docs[i])
                metadatas.append(ai_metas[i])
                existing_ids.add(ai_id)
                
            print(f"  > Merged {len(ai_ids)} AI workflows into candidate pool.")

    # Apply Hybrid Filtering (PART 4 logic remains same)
    final_ids, final_docs, final_metas = select_relevant_results(
        query, metadatas, documents, ids, max_final=n_results
    )
    
    # Fill distances with 0.0 initially
    final_dists = [0.0] * len(final_ids)
    
    # Convert to list of tuples for reranking
    results_for_rerank = list(zip(final_docs, final_metas, final_dists))
    
    # Apply service and category reranking
    reranked_results = rerank_by_service_and_category(query, results_for_rerank)
    
    return reranked_results

def load_workflow_json(filename: str) -> str:
    """
    Loads the raw JSON content from the file.
    """
    try:
        # Assuming files are in the current working directory or relative to it
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"[WARN] Could not find workflow file: {filename}")
        return "{}"
    except Exception as e:
        print(f"[WARN] Error reading file {filename}: {e}")
        return "{}"

def generate_prompt(user_query: str, retrieved_items: list):
    """
    Constructs the final prompt for the LLM, including full JSON content.
    retrieved_items: List of tuples (summary_text, filename)
    """
    system_prompt = """You are an expert n8n workflow architect.
Your goal is to help the user build an automation based on their request.
Use the provided Reference Workflows as a base/inspiration.
Always output valid JSON if asked for code.
"""
    
    context_parts = []
    for i, (summary, filename) in enumerate(retrieved_items):
        json_content = load_workflow_json(filename)
        
        # Build the section for this workflow
        part = f"--- WORKFLOW {i+1} ---\n{summary}"
        
        # Append JSON if available
        # Ensure NO truncation is applied
        part += f"\n\nREFERENCE WORKFLOW JSON ({filename}):\n```json\n{json_content}\n```"
            
        context_parts.append(part)
    
    context_str = "\n\n".join(context_parts)
    
    final_prompt = f"""
{system_prompt}

USER REQUEST: {user_query}

REFERENCE WORKFLOWS FOUND:
{context_str}

Please analyze the request and suggest an implementation plan or specific nodes to use.
"""
    return final_prompt

def build_and_save_prompt(query: str, output_path: str) -> None:
    """
    Uses the existing RAG pipeline to:
    - search workflows
    - build the full LLM prompt (with JSON examples)
    - write the full prompt to `output_path`
    WITHOUT modifying any existing logic.
    """
    # Reuse the same search function
    results = search_workflows(query)
    
    # Collect found items exactly as in main block
    found_items = []
    for doc, meta, dist in results:
        filename = meta.get('filename')
        found_items.append((doc, filename))
    
    # Reuse the same prompt generator
    prompt = generate_prompt(query, found_items)
    
    # Write to the specified path
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(prompt)
    
    print(f"Saved batch prompt to: {output_path}")

def smoke_test():
    """
    Runs a quick query to verify the system is working.
    """
    print("--- SMOKE TEST START ---")
    query = "Shopify order to Google Sheets"
    print(f"Query: {query}")
    
    try:
        # Force list to exhaust iterator
        results = list(search_workflows(query))
        found_items = []

        for doc, meta, dist in results:
            services = meta.get('services', '')
            categories = meta.get('categories', '')
            print(f"  [MATCH] {meta.get('filename')} (Score: {dist:.4f})")
            if services:
                print(f"          Services: {services}")
            if categories:
                print(f"          Categories: {categories}")
            found_items.append((doc, meta.get('filename')))

        if found_items:
            print("\nGenerating sample prompt...")
            prompt = generate_prompt(query, found_items)
            preview = prompt[:200].replace("\n", " ")
            print(f"  [PROMPT PREVIEW] {preview}...")
            print("--- SMOKE TEST PASSED ---")
        else:
            print("--- SMOKE TEST FAILED (No results) ---")
    except Exception as e:
        print(f"--- SMOKE TEST FAILED (Error: {e}) ---")

if __name__ == "__main__":
    
    # SMOKE TEST MODE
    if len(sys.argv) > 1 and sys.argv[1] == "--smoke":
        smoke_test()
        sys.exit(0)

    # BATCH MODE DETECTION
    if len(sys.argv) > 1 and sys.argv[1] == "--batch":
        
        TEST_QUERIES = [
            "When a new Shopify order comes in, log the order details to Google Sheets and send a notification to Slack.",
            "Create a workflow that turns every new Shopify order into a Zendesk ticket for the support team.",
            "Whenever a new Shopify customer places their first order, create or update the contact in HubSpot.",
            "Post a short tweet whenever a high-value Shopify order is placed, including the order total.",
            "Notify a Slack channel whenever a new WooCommerce order is received, including product names and total amount.",
            "Create an automation that tracks PayPal payment updates and logs each completed payment into a Google Sheet.",
            "Append each new Typeform response into a Google Sheets spreadsheet for analysis.",
            "Accept incoming data via a webhook and write each payload as a new row in Google Sheets.",
            "Once per hour, read a Google Sheets table and process each row through an HTTP endpoint.",
            "Whenever a new row is added to Google Sheets, create or update a corresponding CMS item in Webflow.",
            "Send a Slack message whenever a new row is added to a specific Google Sheets tab with sales data.",
            "Save incoming Gmail attachments into a specific Google Drive folder automatically.",
            "For every Gmail message with a certain label, extract key fields and store them in Google Sheets.",
            "When an email contains a date and “meeting” in the subject, create a Google Calendar event from it.",
            "Build a workflow that sends a templated email with dynamic fields filled from a Google Sheet.",
            "If a workflow execution fails, send a Slack alert and include a link to the failed execution for manual review.",
            "Every week, summarize all failed n8n executions and send a report message to Telegram.",
            "When a Telegram bot command is received, call an HTTP API, then reply back in Telegram with the result.",
            "Handle incoming WhatsApp webhook messages and forward them to another HTTP endpoint for processing.",
            "Only send a Telegram notification for executions that finished with an error status in the last 24 hours.",
            "Accept data from a webhook and create or update records in Airtable for each payload.",
            "From an incoming webhook containing event data, create Google Calendar events automatically.",
            "On a schedule, call an HTTP endpoint to fetch analytics data and push it into a data store or report.",
            "Filter a list of items to only keep those created this week, then summarize them into a single text output.",
            "Take incoming JSON items, transform or enrich them with custom JavaScript logic, then pass them to the next node.",
            "Whenever a new form submission arrives, use OpenAI to summarize the response and store the summary in a field.",
            "Use OpenAI to generate a short description or category for each row in a Google Sheets sheet and write it back.",
            "Build a Telegram bot that receives a message, sends it to OpenAI for a response, and replies back to the user.",
            "When a new lead email comes in, extract the lead data, append it to Google Sheets, and ping a Slack channel.",
            "On new records created in Nocodb via a webhook, send a formatted notification to Slack, including key fields."
        ]
        
        output_dir = "test_prompts_30"
        # Ensure output directory exists
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        print(f"Starting batch generation for {len(TEST_QUERIES)} queries...")
        
        for i, query in enumerate(TEST_QUERIES):
            # Create a safe filename slug
            slug = re.sub(r'[^a-zA-Z0-9]', '_', query).lower().strip('_')
            # Shorten if too long
            if len(slug) > 50:
                slug = slug[:50]
                
            filename = f"{output_dir}/{i+1:02d}_{slug}.txt"
            
            print(f"[{i+1}/{len(TEST_QUERIES)}] {query}")
            build_and_save_prompt(query, filename)
            
        print(f"\\nBatch generation complete! Check ./{output_dir}/")
        sys.exit(0)

    # NORMAL MODE
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        print("Enter your query (e.g. 'sync shopify to google sheets'):")
        query = input("> ")
        
    results = search_workflows(query)
    
    found_items = []
    print("\n" + "="*60)
    print("Top retrieved workflows:")
    print("="*60 + "\n")
    
    for i, (doc, meta, dist) in enumerate(results, 1):
        filename = meta.get('filename', 'unknown')
        found_items.append((doc, filename))
        
        # Get services and categories (comma-separated strings)
        services = meta.get('services', '')
        categories = meta.get('categories', '')
        integrations = meta.get('integrations', '')
        
        # Format the output
        print(f"[{i}] {filename}")
        print(f"    Similarity: {1 - dist:.4f}" if dist != 0 else f"    Score: (reranked)")
        
        if services:
            print(f"    Services: {services}")
        if categories:
            print(f"    Categories: {categories}")
        if integrations:
            print(f"    Integrations: {integrations}")
        
        # Replace newlines for cleaner output in preview
        preview = doc[:120].replace("\n", " ")
        # Handle encoding for Windows console
        safe_preview = preview.encode('ascii', 'ignore').decode('ascii')
        print(f"    Excerpt: {safe_preview}...")
        print()

    print("="*40)
    print("GENERATING PROMPT...")
    
    # Generate prompt with full JSONs
    prompt = generate_prompt(query, found_items)
    
    # Write to file for safety/inspection
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(prompt)
        
    print(f"Full prompt written to {OUTPUT_FILE}")
    print("="*40)
    
    # Print safely for Windows console - outputting first 2000 chars as preview
    # The full content is in the file.
    # If the user really wants the full console output, they can cat the file or we can print it all.
    # The instructions said: "It is OK if the console printout is huge."
    # So I will print it all, handling encoding.
    try:
        print(prompt.encode('ascii', 'ignore').decode('ascii'))
    except Exception as e:
        print(f"[WARN] Could not print full prompt to console due to encoding issues: {e}")
        print(f"Please check {OUTPUT_FILE} for the full content.")
