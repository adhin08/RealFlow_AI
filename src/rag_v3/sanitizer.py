"""
STEP 2: Sanitize Workflow JSON (SAFE MODE)

Removes sensitive/runtime data while preserving workflow structure.
"""

import json
import copy
from typing import Dict, Any, Tuple, Optional


# Fields to KEEP
KEEP_FIELDS = {'nodes', 'connections', 'settings', 'name'}

# Fields to REMOVE (sensitive/runtime data)
REMOVE_FIELDS = {
    'id', 'versionId', 'createdAt', 'updatedAt', 'owner', 'sharedWith',
    'pinData', 'meta', 'executionData', 'staticData', 'active',
    'instanceId', 'credentials'
}

# Node-level fields to REMOVE
NODE_REMOVE_FIELDS = {
    'id', 'credentials', 'webhookId', 'notesInFlow'
}


def sanitize_node(node: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize a single node, removing sensitive data.
    """
    sanitized = {}
    
    for key, value in node.items():
        # Skip fields to remove
        if key in NODE_REMOVE_FIELDS:
            continue
        
        # Keep the rest
        sanitized[key] = value
    
    # Ensure required fields exist
    if 'name' not in sanitized:
        sanitized['name'] = 'Unknown Node'
    if 'type' not in sanitized:
        sanitized['type'] = 'unknown'
    if 'parameters' not in sanitized:
        sanitized['parameters'] = {}
    if 'position' not in sanitized:
        sanitized['position'] = [0, 0]
    
    return sanitized


def sanitize_workflow(workflow: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
    """
    Sanitize a workflow JSON, removing sensitive data.
    
    Returns:
        (is_valid, sanitized_workflow, error_message)
    """
    # Validate required fields
    if 'nodes' not in workflow:
        return False, {}, "Missing 'nodes' field"
    
    if not isinstance(workflow['nodes'], list):
        return False, {}, "'nodes' is not a list"
    
    if len(workflow['nodes']) == 0:
        return False, {}, "'nodes' is empty"
    
    if 'connections' not in workflow:
        # Some workflows have no connections (single node)
        workflow['connections'] = {}
    
    if not isinstance(workflow['connections'], dict):
        return False, {}, "'connections' is not a dict"
    
    # Build sanitized workflow
    sanitized = {}
    
    # Keep workflow name
    sanitized['name'] = workflow.get('name', 'Unnamed Workflow')
    
    # Sanitize nodes
    sanitized['nodes'] = [sanitize_node(node) for node in workflow['nodes']]
    
    # Sanitize connections - remove any node IDs, keep node names
    sanitized['connections'] = sanitize_connections(workflow['connections'])
    
    # Keep settings if present
    if 'settings' in workflow and isinstance(workflow['settings'], dict):
        # Only keep safe settings
        safe_settings = {}
        for key in ['executionOrder', 'saveManualExecutions', 'timezone']:
            if key in workflow['settings']:
                safe_settings[key] = workflow['settings'][key]
        sanitized['settings'] = safe_settings
    else:
        sanitized['settings'] = {}
    
    return True, sanitized, ""


def sanitize_connections(connections: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize connections, removing IDs but keeping structure.
    """
    sanitized = {}
    
    for source, outputs in connections.items():
        if not isinstance(outputs, dict):
            continue
        
        sanitized_outputs = {}
        for output_type, connections_list in outputs.items():
            if not isinstance(connections_list, list):
                continue
            
            sanitized_connections = []
            for conn_group in connections_list:
                if not isinstance(conn_group, list):
                    continue
                
                sanitized_group = []
                for conn in conn_group:
                    if isinstance(conn, dict) and 'node' in conn:
                        # Keep only node name, type, index
                        sanitized_conn = {
                            'node': conn.get('node', 'Unknown'),
                            'type': conn.get('type', 'main'),
                            'index': conn.get('index', 0)
                        }
                        sanitized_group.append(sanitized_conn)
                
                if sanitized_group:
                    sanitized_connections.append(sanitized_group)
            
            if sanitized_connections:
                sanitized_outputs[output_type] = sanitized_connections
        
        if sanitized_outputs:
            sanitized[source] = sanitized_outputs
    
    return sanitized


def load_and_sanitize(filepath: str) -> Tuple[bool, Dict[str, Any], str]:
    """
    Load a workflow JSON file and sanitize it.
    
    Returns:
        (is_valid, sanitized_workflow, error_message)
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        workflow = json.loads(content)
        
        return sanitize_workflow(workflow)
        
    except json.JSONDecodeError as e:
        return False, {}, f"Invalid JSON: {str(e)}"
    except IOError as e:
        return False, {}, f"IO Error: {str(e)}"
    except Exception as e:
        return False, {}, f"Error: {str(e)}"


if __name__ == "__main__":
    # Test sanitizer
    import sys
    
    test_workflow = {
        "id": "abc123",
        "name": "Test Workflow",
        "versionId": "v1",
        "createdAt": "2024-01-01",
        "updatedAt": "2024-01-02",
        "owner": "user@example.com",
        "nodes": [
            {
                "id": "node1",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "parameters": {"path": "/test"},
                "position": [100, 200],
                "credentials": {"httpBasic": "secret"}
            },
            {
                "id": "node2",
                "name": "Slack",
                "type": "n8n-nodes-base.slack",
                "parameters": {"channel": "#general"},
                "position": [300, 200]
            }
        ],
        "connections": {
            "Webhook": {
                "main": [[{"node": "Slack", "type": "main", "index": 0}]]
            }
        },
        "pinData": {"test": "data"},
        "meta": {"instanceId": "xyz"}
    }
    
    is_valid, sanitized, error = sanitize_workflow(test_workflow)
    
    print(f"Valid: {is_valid}")
    if is_valid:
        print(f"Sanitized: {json.dumps(sanitized, indent=2)}")
    else:
        print(f"Error: {error}")










