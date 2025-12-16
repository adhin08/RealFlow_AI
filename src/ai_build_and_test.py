#!/usr/bin/env python3
"""
AI Workflow Builder CLI

This script provides an end-to-end workflow for:
1. Taking a natural language query
2. Using RAG to retrieve reference workflows
3. Building a prompt and calling an LLM (OpenRouter or OpenAI)
4. Parsing and validating the generated workflow
5. Optionally uploading to n8n

Usage:
    python src/ai_build_and_test.py "When a new Shopify order comes in, log to Google Sheets and notify Slack"
    python src/ai_build_and_test.py --list-models  # Show available free models
    
Environment Variables:
    OPENROUTER_API_KEY - Recommended! Supports FREE models (https://openrouter.ai)
    OPENAI_API_KEY     - Alternative: OpenAI directly (paid)
    N8N_URL            - Optional, for uploading workflows
    N8N_API_KEY        - Optional, for uploading workflows
"""

import sys
import os
import json
import argparse
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag import search_workflows
from ai_builder import (
    build_prompt_from_query_and_workflows,
    call_llm_with_prompt,
    parse_llm_response_for_workflow,
    validate_workflow_json,
    generate_workflow_name,
    list_free_models,
    DEFAULT_FREE_MODEL
)
from n8n_client import (
    get_n8n_config,
    upload_workflow_to_n8n,
    get_workflow_url,
    maybe_run_test_execution,
    check_n8n_connection
)
from validator import (
    validate_workflow,
    calculate_confidence
)


# Output directory for generated workflows
OUTPUT_DIR = "generated_workflows"


def ensure_output_dir():
    """Create the output directory if it doesn't exist."""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"[INFO] Created output directory: {OUTPUT_DIR}/")


def save_workflow_to_file(workflow: dict, query: str) -> str:
    """
    Save a workflow to a JSON file.
    
    Returns the file path.
    """
    ensure_output_dir()
    
    # Generate filename from query
    slug = query[:40].lower()
    slug = ''.join(c if c.isalnum() else '_' for c in slug)
    slug = '_'.join(filter(None, slug.split('_')))  # Remove empty parts
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{OUTPUT_DIR}/{slug}_{timestamp}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(workflow, f, indent=2)
    
    return filename


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{'='*60}")
    print(f" {text}")
    print(f"{'='*60}\n")


def print_section(title: str):
    """Print a section title."""
    print(f"\n--- {title} ---\n")


def truncate_text(text: str, max_length: int = 500) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def main():
    parser = argparse.ArgumentParser(
        description="AI Workflow Builder - Generate n8n workflows from natural language",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  OPENROUTER_API_KEY  - For OpenRouter (recommended, has free models)
  OPENAI_API_KEY      - For OpenAI directly
  N8N_URL             - n8n instance URL (optional)
  N8N_API_KEY         - n8n API key (optional)

Examples:
  python src/ai_build_and_test.py "When a new Shopify order comes in, send a Slack notification"
  python src/ai_build_and_test.py "..." --model google/gemma-2-9b-it:free
  python src/ai_build_and_test.py --list-models
        """
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Natural language description of the workflow to build"
    )
    parser.add_argument(
        "--model",
        default="auto",
        help="LLM model to use (default: auto - picks best available)"
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of reference workflows to retrieve (default: 3)"
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Don't upload to n8n even if configured"
    )
    parser.add_argument(
        "--test-run",
        action="store_true",
        help="Attempt a test execution after uploading"
    )
    parser.add_argument(
        "--save-prompt",
        action="store_true",
        help="Save the generated prompt to a file"
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available free models on OpenRouter and exit"
    )
    parser.add_argument(
        "--rag-version",
        type=str,
        default="v3",
        choices=["v2", "v3"],
        help="RAG version to use (default: v3 with 1927 workflows)"
    )
    
    args = parser.parse_args()
    
    # Handle --list-models
    if args.list_models:
        list_free_models()
        return 0
    
    # Get query from args or prompt user
    if args.query:
        query = args.query
    else:
        print("Enter your workflow description:")
        query = input("> ").strip()
        if not query:
            print("[ERROR] No query provided.")
            sys.exit(1)
    
    print_header("AI WORKFLOW BUILDER")
    
    # Display query
    print(f"Query:")
    print(f"  {query}\n")
    
    # =========================================================================
    # Step 1: RAG Retrieval
    # =========================================================================
    print_section("Step 1: Retrieving Reference Workflows")
    
    # Set RAG version in environment
    os.environ["RAG_VERSION"] = args.rag_version
    
    try:
        results = list(search_workflows(query, n_results=args.top_k))
        print(f"  Using RAG {args.rag_version.upper()}")
    except Exception as e:
        print(f"[ERROR] RAG retrieval failed: {e}")
        sys.exit(1)
    
    if not results:
        print("[WARN] No reference workflows found. Proceeding with empty context.")
        results = []
    
    print("Top references:")
    for i, (doc, meta, score) in enumerate(results, 1):
        filename = meta.get('filename', 'unknown')
        services = meta.get('services', 'N/A')
        categories = meta.get('categories', 'N/A')
        print(f"  {i}) {filename}")
        print(f"     Score: {score:.4f} | Services: {services}")
        if categories:
            print(f"     Categories: {categories}")
    
    # =========================================================================
    # Step 2: Build Prompt
    # =========================================================================
    print_section("Step 2: Building LLM Prompt")
    
    prompt = build_prompt_from_query_and_workflows(query, results)
    print(f"  Prompt length: {len(prompt)} characters")
    
    # Always save the prompt
    ensure_output_dir()
    prompt_file = f"{OUTPUT_DIR}/last_prompt.txt"
    with open(prompt_file, 'w', encoding='utf-8') as f:
        f.write(prompt)
    print(f"  Saved to: {prompt_file}")
    
    # =========================================================================
    # Step 3: Call LLM
    # =========================================================================
    print_section("Step 3: Calling LLM")
    
    # Check for API key (OpenRouter or OpenAI)
    has_openrouter = os.environ.get("OPENROUTER_API_KEY")
    has_openai = os.environ.get("OPENAI_API_KEY")
    
    if not has_openrouter and not has_openai:
        print("[ERROR] No LLM API key configured.")
        print()
        print("  Option 1 (Recommended - FREE models):")
        print("    export OPENROUTER_API_KEY=sk-or-...")
        print("    Get your key at: https://openrouter.ai/keys")
        print()
        print("  Option 2 (OpenAI - Paid):")
        print("    export OPENAI_API_KEY=sk-...")
        print()
        print("  Run --list-models to see available free models.")
        sys.exit(1)
    
    if has_openrouter:
        print(f"  Using: OpenRouter API")
    else:
        print(f"  Using: OpenAI API")
    
    response = call_llm_with_prompt(prompt, model=args.model)
    
    if response is None:
        print("[ERROR] LLM call failed. See errors above.")
        sys.exit(1)
    
    print(f"  Response received: {len(response)} characters")
    
    # =========================================================================
    # Step 4: Parse Response
    # =========================================================================
    print_section("Step 4: Parsing LLM Response")
    
    implementation_plan, workflow = parse_llm_response_for_workflow(response)
    
    if implementation_plan:
        print("Implementation Plan:")
        print(truncate_text(implementation_plan, 600))
    
    if workflow is None:
        print("\n[ERROR] Failed to extract workflow JSON from response.")
        print("\nRaw response (first 1000 chars):")
        print(truncate_text(response, 1000))
        sys.exit(1)
    
    print(f"\n  Extracted workflow with {len(workflow.get('nodes', []))} nodes")
    
    # Always save the generated workflow JSON
    workflow_json_file = f"{OUTPUT_DIR}/last_workflow.json"
    with open(workflow_json_file, 'w', encoding='utf-8') as f:
        json.dump(workflow, f, indent=2)
    print(f"  Saved to: {workflow_json_file}")
    
    # =========================================================================
    # Step 5: Validate Workflow
    # =========================================================================
    print_section("Step 5: Validating Workflow")
    
    # Basic validation
    is_valid, error_msg = validate_workflow_json(workflow)
    
    if not is_valid:
        print(f"[ERROR] Validation FAILED: {error_msg}")
        
        # Save invalid workflow for debugging
        debug_file = save_workflow_to_file(workflow, f"INVALID_{query}")
        print(f"  Saved invalid workflow for debugging: {debug_file}")
        sys.exit(1)
    
    print("  Validation: PASSED [OK]")
    print(f"  - Nodes: {len(workflow.get('nodes', []))}")
    print(f"  - Connections: {len(workflow.get('connections', {}))} node(s) connected")
    
    # List node types
    node_types = [n.get('type', 'unknown').split('.')[-1] for n in workflow.get('nodes', [])]
    print(f"  - Node types: {', '.join(node_types)}")
    
    # Advanced validation (V3)
    print("\n  --- Advanced Validation (V3) ---")
    adv_valid, issues, summary = validate_workflow(workflow)
    print(f"  Operations: {summary}")
    for issue in issues[:3]:  # Show first 3 issues
        print(f"    - {issue}")
    if len(issues) > 3:
        print(f"    ... and {len(issues) - 3} more issues")
    
    # Confidence score
    top_similarity = results[0][2] if results else 0.0
    confidence, conf_explanation = calculate_confidence(workflow, top_similarity)
    print(f"\n  Confidence: {conf_explanation}")
    
    # =========================================================================
    # Step 6: Upload or Save
    # =========================================================================
    print_section("Step 6: Output")
    
    n8n_config = get_n8n_config()
    workflow_name = generate_workflow_name(query)
    
    if n8n_config and not args.no_upload:
        # Try to upload to n8n
        print("n8n configuration detected!")
        
        connected, conn_msg = check_n8n_connection(n8n_config)
        if not connected:
            print(f"  [WARN] Cannot connect to n8n: {conn_msg}")
            print("  Falling back to local save...")
            n8n_config = None
    
    if n8n_config and not args.no_upload:
        success, result = upload_workflow_to_n8n(workflow, workflow_name, n8n_config)
        
        if success:
            workflow_id = result.get('id', 'unknown')
            workflow_url = get_workflow_url(workflow_id, n8n_config)
            
            print(f"\n  [OK] Workflow uploaded successfully!")
            print(f"    ID: {workflow_id}")
            print(f"    Name: {result.get('name', workflow_name)}")
            print(f"    URL: {workflow_url}")
            
            # Optional test execution
            if args.test_run:
                print("\n  Attempting test execution...")
                attempted, exec_result = maybe_run_test_execution(result, n8n_config)
                
                if not attempted:
                    print("    Test execution not available")
                elif exec_result.get('success'):
                    print(f"    [OK] Test execution started: {exec_result.get('message')}")
                else:
                    print(f"    [FAIL] Test execution failed: {exec_result.get('message')}")
        else:
            print(f"\n  [FAIL] Upload failed: {result.get('error', 'Unknown error')}")
            print("  Saving locally instead...")
            
            filepath = save_workflow_to_file(workflow, query)
            print(f"    Saved to: {filepath}")
    else:
        # Save locally
        if n8n_config is None:
            print("  N8N_URL/N8N_API_KEY not set -> saving locally")
        else:
            print("  --no-upload flag set -> saving locally")
        
        filepath = save_workflow_to_file(workflow, query)
        print(f"\n  [OK] Workflow saved to: {filepath}")
    
    # =========================================================================
    # Summary
    # =========================================================================
    print_header("COMPLETE")
    print("Workflow generation successful!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

