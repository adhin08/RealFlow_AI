"""
AI Workflow Builder Module

This module provides functions to:
1. Build structured prompts from user queries and retrieved workflows
2. Call the LLM API to generate n8n workflows (supports OpenRouter + OpenAI)
3. Parse LLM responses to extract workflow JSON
4. Validate generated workflow structures
"""

import os
import re
import json
from typing import Any, Dict, List, Tuple, Optional
from dotenv import load_dotenv
import requests

# Load environment variables from .env if present (works for CLI + API)
# override=True ensures the .env value replaces any stale process env value.
load_dotenv(override=True)

# Try to import OpenAI client (works with OpenRouter too)
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


# ============================================================================
# OpenRouter Configuration
# ============================================================================

# OpenRouter API base URL
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Best FREE models on OpenRouter (ranked by quality for code/JSON generation)
# Updated: These models are free tier on OpenRouter
FREE_MODELS = {
    # Top Tier - Best for JSON/Code generation
    "mistralai/devstral-2512:free": {
        "name": "Devstral (Free)",
        "context": 32768,
        "quality": "excellent",
        "speed": "fast",
        "notes": "Mistral's coding-focused model - BEST for JSON/workflows"
    },
    "google/gemini-2.0-flash-exp:free": {
        "name": "Gemini 2.0 Flash (Free)",
        "context": 1048576,
        "quality": "excellent",
        "speed": "fast"
    },
    "google/gemma-2-9b-it:free": {
        "name": "Gemma 2 9B (Free)",
        "context": 8192,
        "quality": "very good",
        "speed": "fast"
    },
    "meta-llama/llama-3.1-8b-instruct:free": {
        "name": "Llama 3.1 8B (Free)",
        "context": 131072,
        "quality": "very good",
        "speed": "fast"
    },
    
    # Good Tier
    "qwen/qwen-2-7b-instruct:free": {
        "name": "Qwen 2 7B (Free)",
        "context": 32768,
        "quality": "good",
        "speed": "fast"
    },
    "microsoft/phi-3-mini-128k-instruct:free": {
        "name": "Phi-3 Mini 128K (Free)",
        "context": 128000,
        "quality": "good",
        "speed": "very fast"
    },
    "mistralai/mistral-7b-instruct:free": {
        "name": "Mistral 7B (Free)",
        "context": 32768,
        "quality": "good",
        "speed": "fast"
    },
    
    # Backup options
    "huggingfaceh4/zephyr-7b-beta:free": {
        "name": "Zephyr 7B (Free)",
        "context": 4096,
        "quality": "decent",
        "speed": "fast"
    },
    "openchat/openchat-7b:free": {
        "name": "OpenChat 7B (Free)",
        "context": 8192,
        "quality": "decent",
        "speed": "fast"
    }
}

# Default model (best free option for JSON generation)
DEFAULT_FREE_MODEL = "mistralai/devstral-2512:free"


def load_workflow_json_content(filename: str) -> str:
    """
    Load the raw JSON content from a workflow file.
    """
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "{}"
    except Exception as e:
        print(f"[WARN] Error reading {filename}: {e}")
        return "{}"


def build_prompt_from_query_and_workflows(
    query: str,
    workflows: List[Tuple[str, Dict[str, Any], float]],
) -> str:
    """
    Build a structured prompt for the LLM.
    
    Args:
        query: The user's natural language request
        workflows: List of (document, metadata, score) tuples from RAG retrieval
        
    Returns:
        A formatted prompt string for the LLM
    """
    # Build the reference workflows section
    workflow_sections = []
    
    for i, (doc, meta, score) in enumerate(workflows, 1):
        filename = meta.get('filename', 'unknown')
        services = meta.get('services', '')
        categories = meta.get('categories', '')
        integrations = meta.get('integrations', '')
        
        # Load the full JSON content
        json_content = load_workflow_json_content(filename)
        
        section = f"""### Reference Workflow {i}: {filename}
- **Services**: {services if services else 'N/A'}
- **Categories**: {categories if categories else 'N/A'}
- **Integrations**: {integrations if integrations else 'N/A'}

**Description:**
{doc[:500]}{'...' if len(doc) > 500 else ''}

**Full Workflow JSON:**
```json
{json_content}
```
"""
        workflow_sections.append(section)
    
    reference_content = "\n".join(workflow_sections)
    
    prompt = f"""You are an expert n8n workflow architect with deep knowledge of automation patterns, integrations, and best practices.

## User Request
{query}

## Reference Workflows
The following are similar workflows from our template library that you should use as inspiration and reference:

{reference_content}

## Your Task
1. **Analyze** the user's request carefully to understand what they want to automate.
2. **Compare** with the reference workflows to identify relevant patterns, node types, and configurations.
3. **Design** a complete n8n workflow that fulfills the user's request.
4. **Keep it simple** - only include nodes that are necessary for the task.

## CRITICAL RULES

### Node Connections
- Only connect nodes that should execute in sequence
- Do NOT put error/stop nodes in the main success flow
- The last action node should have NO outgoing connections (empty array)

### Common n8n Expressions (USE THESE EXACTLY)

**Telegram:**
- Chat ID from trigger: `={{{{$json.message.chat.id}}}}`
- Message text from trigger: `={{{{$json.message.text}}}}`
- User name: `={{{{$json.message.from.first_name}}}}`

**Email/Gmail:**
- Sender: `={{{{$json.from}}}}`
- Subject: `={{{{$json.subject}}}}`
- Body: `={{{{$json.text}}}}`

**Webhook:**
- Access body data: `={{{{$json.fieldName}}}}`
- Access query params: `={{{{$json.query.paramName}}}}`

**Google Sheets:**
- Reference previous node: `={{{{$json.columnName}}}}`

**Slack:**
- Use channel name with #: `#channel-name`

### Error Handling Rules
- For simple workflows (2-3 nodes): Do NOT include error handlers
- For complex workflows: Use a separate error workflow, not inline error nodes
- NEVER connect stopAndError nodes to the main success path

### CRITICAL: Node Type Versions (USE EXACTLY)
**Always use these typeVersion values:**
- telegramTrigger: `typeVersion: 1`
- telegram: `typeVersion: 1`
- googleDriveTrigger: `typeVersion: 1`
- googleDrive: `typeVersion: 3`
- googleSheetsTrigger: `typeVersion: 1`
- googleSheets: `typeVersion: 4`
- slack: `typeVersion: 2`
- webhook: `typeVersion: 2`
- httpRequest: `typeVersion: 4`
- if: `typeVersion: 2`
- set: `typeVersion: 3`
- code: `typeVersion: 2`
- cron: `typeVersion: 1`
- schedule: `typeVersion: 1`
- spreadsheetFile: `typeVersion: 2`

### Google Drive File Upload (IMPORTANT)
When uploading files to Google Drive, use this structure:
```json
{{
  "type": "n8n-nodes-base.googleDrive",
  "typeVersion": 3,
  "parameters": {{
    "name": "={{{{$json.fileName}}}}",
    "driveId": {{"__rl": true, "mode": "list", "value": "My Drive"}},
    "folderId": {{"__rl": true, "mode": "list", "value": "root"}}
  }}
}}
```

### Telegram File Downloads
To receive files from Telegram, add `download: true`:
```json
{{
  "type": "n8n-nodes-base.telegramTrigger",
  "typeVersion": 1,
  "parameters": {{
    "updates": ["message"],
    "additionalFields": {{"download": true}}
  }}
}}
```

### Excel/CSV to Google Sheets Conversion (IMPORTANT)
There is NO "convert" operation in Google Drive! To convert Excel to Sheets:
1. Download the file from Google Drive (binary)
2. Use Spreadsheet File node to read Excel → JSON
3. Use Google Sheets node to write JSON data

Example pattern:
```json
[
  {{"name": "Download File", "type": "n8n-nodes-base.googleDrive", "typeVersion": 3, "parameters": {{"operation": "download", "fileId": "={{{{$json.id}}}}"}}}},
  {{"name": "Read Excel", "type": "n8n-nodes-base.spreadsheetFile", "typeVersion": 2, "parameters": {{"operation": "fromFile"}}}},
  {{"name": "Write to Sheets", "type": "n8n-nodes-base.googleSheets", "typeVersion": 4, "parameters": {{"operation": "append"}}}}
]
```

### Binary File Operations
- Download file: `googleDrive` with `operation: "download"`
- Read Excel/CSV: `spreadsheetFile` with `operation: "fromFile"`
- Write Excel/CSV: `spreadsheetFile` with `operation: "toFile"`
- Read binary: `readBinaryFile`
- Write binary: `writeBinaryFile`

## Output Format

## Implementation Plan
[Brief explanation of the workflow]

## Complete Workflow JSON
```json
{{
  "name": "<descriptive workflow name>",
  "nodes": [...],
  "connections": {{...}},
  "settings": {{}},
  "active": false
}}
```

## Example: Simple Telegram Reply Bot
```json
{{
  "name": "Telegram Hello Bot",
  "nodes": [
    {{
      "id": "1",
      "name": "Telegram Trigger", 
      "type": "n8n-nodes-base.telegramTrigger",
      "position": [250, 300],
      "parameters": {{"updates": ["message"]}},
      "typeVersion": 1
    }},
    {{
      "id": "2",
      "name": "Reply",
      "type": "n8n-nodes-base.telegram", 
      "position": [500, 300],
      "parameters": {{
        "operation": "sendMessage",
        "text": "hello",
        "chatId": "={{{{$json.message.chat.id}}}}"
      }},
      "typeVersion": 1
    }}
  ],
  "connections": {{
    "Telegram Trigger": {{
      "main": [[{{"node": "Reply", "type": "main", "index": 0}}]]
    }}
  }},
  "settings": {{}},
  "active": false
}}
```

## Requirements
1. Valid JSON only
2. Connections MUST use node NAMES not IDs. Example: "NodeName": {{"main": [[{{"node": "OtherNodeName"}}]]}}
3. Use the EXACT expressions shown above for each service
4. Keep workflows minimal - no unnecessary nodes
5. Every node must have both "id" and "name" fields
"""
    
    return prompt


def get_llm_client() -> Tuple[Optional[Any], str, str]:
    """
    Get an LLM client (OpenRouter or OpenAI).
    
    Priority:
    1. OPENROUTER_API_KEY -> Use OpenRouter
    2. OPENAI_API_KEY -> Use OpenAI directly
    
    Returns:
        Tuple of (client, provider_name, default_model)
        client will be None if not configured
    """
    if not HAS_OPENAI:
        print("[ERROR] OpenAI package not installed. Run: pip install openai")
        return None, "", ""
    
    # Check for OpenRouter first (preferred for free models)
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if openrouter_key:
        client = OpenAI(
            api_key=openrouter_key,
            base_url=OPENROUTER_BASE_URL
        )
        return client, "OpenRouter", DEFAULT_FREE_MODEL
    
    # Fall back to OpenAI
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        client = OpenAI(api_key=openai_key)
        return client, "OpenAI", "gpt-4o"
    
    print("[ERROR] No API key found. Set OPENROUTER_API_KEY or OPENAI_API_KEY")
    return None, "", ""


def list_free_models():
    """Print available free models on OpenRouter."""
    print("\n=== Available FREE Models on OpenRouter ===\n")
    print(f"{'Model ID':<45} {'Name':<25} {'Context':<10} {'Quality'}")
    print("-" * 95)
    for model_id, info in FREE_MODELS.items():
        ctx = f"{info['context']:,}"
        print(f"{model_id:<45} {info['name']:<25} {ctx:<10} {info['quality']}")
    print(f"\n[*] Recommended: {DEFAULT_FREE_MODEL}")
    print("    (Best balance of quality and speed for JSON generation)\n")


def call_llm_with_prompt(prompt: str, model: str = None) -> Optional[str]:
    """
    Call the LLM and return the raw text response.
    
    Supports both OpenRouter (free models) and OpenAI.
    
    Args:
        prompt: The full prompt to send to the LLM
        model: The model to use (if None, uses default based on provider)
        
    Returns:
        The LLM's response text, or None if the call failed
    """
    client, provider, default_model = get_llm_client()
    if client is None:
        return None
    
    # Use provided model or default
    if model is None or model == "auto":
        model = default_model
    
    # For OpenRouter, add extra headers
    extra_headers = {}
    if provider == "OpenRouter":
        extra_headers = {
            "HTTP-Referer": "https://github.com/n8n-workflow-builder",
            "X-Title": "n8n AI Workflow Builder"
        }
    
    try:
        model_display = model.split("/")[-1] if "/" in model else model
        print(f"[LLM] Provider: {provider}")
        print(f"[LLM] Model: {model_display}")
        print(f"[LLM] Calling API...")
        
        # Build request kwargs
        request_kwargs = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert n8n workflow architect. You create production-ready automation workflows. Always output valid JSON when asked."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7,
            "max_tokens": 8000
        }
        
        # Add extra headers for OpenRouter
        if extra_headers:
            request_kwargs["extra_headers"] = extra_headers
        
        response = client.chat.completions.create(**request_kwargs)
        
        result = response.choices[0].message.content
        print(f"[LLM] Response received ({len(result)} chars) OK")
        return result
        
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] LLM call failed: {error_msg}")
        
        # Helpful hints for common errors
        if "401" in error_msg or "authentication" in error_msg.lower():
            print("  -> Check your API key is correct")
        elif "429" in error_msg or "rate" in error_msg.lower():
            print("  -> Rate limited. Try a different model or wait.")
        elif "model" in error_msg.lower():
            print(f"  -> Model '{model}' may not be available. Try: --model google/gemma-2-9b-it:free")
        
        # Fallback: direct REST call to OpenRouter to bypass client quirks
        if provider == "OpenRouter":
            try:
                print("[LLM] Falling back to direct OpenRouter HTTP call...")
                headers = {
                    "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY','')}",
                    "HTTP-Referer": "https://github.com/n8n-workflow-builder",
                    "X-Title": "n8n AI Workflow Builder",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are an expert n8n workflow architect. You create production-ready automation workflows. Always output valid JSON when asked."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 8000,
                }
                resp = requests.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=60)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    print(f"[LLM] Fallback response received ({len(content)} chars) OK")
                    return content
                else:
                    print(f"[LLM] Fallback failed: HTTP {resp.status_code} - {resp.text}")
            except Exception as inner:
                print(f"[LLM] Fallback error: {inner}")
        
        return None


def parse_llm_response_for_workflow(response_text: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Parse the LLM response to extract the implementation plan and workflow JSON.
    
    Args:
        response_text: The raw LLM response
        
    Returns:
        Tuple of (implementation_plan, workflow_dict)
        workflow_dict will be None if parsing fails
    """
    implementation_plan = ""
    workflow_dict = None
    
    # Extract Implementation Plan section
    plan_match = re.search(
        r'## Implementation Plan\s*\n(.*?)(?=## Complete Workflow JSON|## Important|$)',
        response_text,
        re.DOTALL | re.IGNORECASE
    )
    if plan_match:
        implementation_plan = plan_match.group(1).strip()
    
    # Extract JSON from code block
    # Look for ```json ... ``` pattern
    json_match = re.search(
        r'```json\s*\n(.*?)\n```',
        response_text,
        re.DOTALL
    )
    
    if json_match:
        json_str = json_match.group(1).strip()
        try:
            workflow_dict = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse JSON: {e}")
            # Try to fix common issues
            try:
                # Sometimes there are trailing commas
                fixed_json = re.sub(r',\s*}', '}', json_str)
                fixed_json = re.sub(r',\s*]', ']', fixed_json)
                workflow_dict = json.loads(fixed_json)
                print("[INFO] Fixed and parsed JSON successfully")
            except:
                workflow_dict = None
    else:
        print("[ERROR] No JSON code block found in response")
    
    return implementation_plan, workflow_dict


def validate_workflow_json(workflow: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate the basic structure of a workflow JSON.
    
    Args:
        workflow: The workflow dictionary to validate
        
    Returns:
        Tuple of (is_valid, message)
        - (True, "") if valid
        - (False, "reason") if invalid
    """
    if workflow is None:
        return False, "Workflow is None"
    
    if not isinstance(workflow, dict):
        return False, f"Workflow must be a dict, got {type(workflow).__name__}"
    
    # Check for required keys
    if "nodes" not in workflow:
        return False, "Missing required key: 'nodes'"
    
    if "connections" not in workflow:
        return False, "Missing required key: 'connections'"
    
    # Validate nodes
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        return False, f"'nodes' must be a list, got {type(nodes).__name__}"
    
    if len(nodes) == 0:
        return False, "'nodes' array is empty - workflow has no nodes"
    
    # Validate connections
    connections = workflow.get("connections")
    if not isinstance(connections, dict):
        return False, f"'connections' must be a dict, got {type(connections).__name__}"
    
    # Check each node has required fields
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            return False, f"Node at index {i} is not a dict"
        
        if "name" not in node:
            return False, f"Node at index {i} missing 'name'"
        
        if "type" not in node:
            return False, f"Node at index {i} missing 'type'"
    
    # Warn if connections are empty (but don't fail)
    if len(connections) == 0:
        print("[WARN] 'connections' is empty - nodes may not be linked")
    
    return True, ""


def generate_workflow_name(query: str) -> str:
    """
    Generate a workflow name from the user query.
    
    Args:
        query: The user's query
        
    Returns:
        A sanitized workflow name
    """
    # Take first 50 chars, clean up
    name = query[:50].strip()
    # Remove special characters
    name = re.sub(r'[^a-zA-Z0-9\s]', '', name)
    # Replace spaces with underscores
    name = re.sub(r'\s+', '_', name)
    # Add prefix
    return f"AI_Generated_{name}"

