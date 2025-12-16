"""
n8n API Client Module

This module provides functions to interact with an n8n instance:
1. Upload workflows via REST API
2. Optionally trigger test executions
3. Retrieve workflow status
"""

import os
import json
from typing import Dict, Any, Optional, Tuple

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def get_n8n_config() -> Optional[Dict[str, str]]:
    """
    Read n8n configuration from environment variables.
    
    Required environment variables:
    - N8N_URL: Base URL of the n8n instance (e.g., http://localhost:5678)
    - N8N_API_KEY: API key for authentication
    
    Returns:
        Dict with 'url' and 'api_key', or None if not configured
    """
    url = os.environ.get("N8N_URL")
    api_key = os.environ.get("N8N_API_KEY")
    
    if not url or not api_key:
        return None
    
    # Remove trailing slash from URL
    url = url.rstrip("/")
    
    return {
        "url": url,
        "api_key": api_key
    }


def _get_headers(api_key: str) -> Dict[str, str]:
    """
    Build request headers for n8n API calls.
    """
    return {
        "Content-Type": "application/json",
        "X-N8N-API-KEY": api_key
    }


def upload_workflow_to_n8n(
    workflow: Dict[str, Any], 
    name: str,
    config: Optional[Dict[str, str]] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Upload a workflow to the n8n instance.
    
    Args:
        workflow: The workflow dictionary with nodes, connections, etc.
        name: Name for the workflow
        config: Optional n8n config (if None, reads from environment)
        
    Returns:
        Tuple of (success: bool, response_data: dict)
        - On success: (True, {"id": "...", "name": "...", ...})
        - On failure: (False, {"error": "..."})
    """
    if not HAS_REQUESTS:
        return False, {"error": "requests library not installed. Run: pip install requests"}
    
    if config is None:
        config = get_n8n_config()
    
    if config is None:
        return False, {"error": "n8n not configured. Set N8N_URL and N8N_API_KEY environment variables."}
    
    url = f"{config['url']}/api/v1/workflows"
    headers = _get_headers(config['api_key'])
    
    # Build the workflow payload
    # Note: Don't include "active" field - it's read-only in n8n API
    payload = {
        "name": name,
        "nodes": workflow.get("nodes", []),
        "connections": workflow.get("connections", {}),
        "settings": {
            "availableInMCP": True  # Enable MCP access for this workflow
        }
    }
    
    try:
        print(f"[n8n] Uploading workflow to {url}...")
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code in (200, 201):
            data = response.json()
            print(f"[n8n] Workflow uploaded successfully! ID: {data.get('id')}")
            return True, data
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            print(f"[n8n] Upload failed: {error_msg}")
            return False, {"error": error_msg}
            
    except requests.exceptions.ConnectionError:
        return False, {"error": f"Cannot connect to n8n at {config['url']}"}
    except requests.exceptions.Timeout:
        return False, {"error": "Request timed out"}
    except Exception as e:
        return False, {"error": str(e)}


def get_workflow_url(workflow_id: str, config: Optional[Dict[str, str]] = None) -> str:
    """
    Build the URL to view a workflow in the n8n UI.
    
    Args:
        workflow_id: The workflow ID
        config: Optional n8n config
        
    Returns:
        The full URL to the workflow editor
    """
    if config is None:
        config = get_n8n_config()
    
    if config is None:
        return f"<n8n-url>/workflow/{workflow_id}"
    
    return f"{config['url']}/workflow/{workflow_id}"


def maybe_run_test_execution(
    workflow_info: Dict[str, Any],
    config: Optional[Dict[str, str]] = None
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Attempt to run a test execution of the uploaded workflow.
    
    This is a best-effort operation - it may not work depending on:
    - n8n version and API availability
    - Workflow trigger type (some require external events)
    - Missing credentials
    
    Args:
        workflow_info: The response from upload_workflow_to_n8n
        config: Optional n8n config
        
    Returns:
        Tuple of (attempted: bool, result: dict or None)
        - (False, None) if test execution not possible
        - (True, {"success": bool, "message": str, ...}) if attempted
    """
    if not HAS_REQUESTS:
        return False, None
    
    if config is None:
        config = get_n8n_config()
    
    if config is None:
        return False, None
    
    workflow_id = workflow_info.get("id")
    if not workflow_id:
        return False, {"success": False, "message": "No workflow ID provided"}
    
    # n8n API endpoint to execute a workflow manually
    # This uses the /api/v1/workflows/{id}/run endpoint
    url = f"{config['url']}/api/v1/workflows/{workflow_id}/run"
    headers = _get_headers(config['api_key'])
    
    try:
        print(f"[n8n] Attempting test execution for workflow {workflow_id}...")
        
        # For workflows with triggers, we can't always run them manually
        # We'll attempt it but expect it might fail
        response = requests.post(
            url, 
            headers=headers, 
            json={},  # Empty payload - workflow should use its trigger
            timeout=60
        )
        
        if response.status_code in (200, 201):
            data = response.json()
            print(f"[n8n] Test execution started!")
            return True, {
                "success": True,
                "message": "Execution started",
                "execution_id": data.get("id"),
                "data": data
            }
        elif response.status_code == 404:
            return True, {
                "success": False,
                "message": "Test execution endpoint not available (may require n8n version 1.0+)"
            }
        else:
            return True, {
                "success": False,
                "message": f"HTTP {response.status_code}: {response.text}"
            }
            
    except requests.exceptions.Timeout:
        return True, {"success": False, "message": "Execution timed out"}
    except Exception as e:
        return True, {"success": False, "message": str(e)}


def check_n8n_connection(config: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
    """
    Check if we can connect to the n8n instance.
    
    Returns:
        Tuple of (connected: bool, message: str)
    """
    if not HAS_REQUESTS:
        return False, "requests library not installed"
    
    if config is None:
        config = get_n8n_config()
    
    if config is None:
        return False, "n8n not configured (N8N_URL and N8N_API_KEY not set)"
    
    try:
        url = f"{config['url']}/api/v1/workflows"
        headers = _get_headers(config['api_key'])
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            count = len(data.get("data", []))
            return True, f"Connected to n8n ({count} existing workflows)"
        elif response.status_code == 401:
            return False, "Authentication failed - check N8N_API_KEY"
        else:
            return False, f"HTTP {response.status_code}"
            
    except requests.exceptions.ConnectionError:
        return False, f"Cannot connect to {config['url']}"
    except Exception as e:
        return False, str(e)

