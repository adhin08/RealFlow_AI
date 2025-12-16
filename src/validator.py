"""
Workflow Validator for V3
Validates that generated workflows use real n8n operations
"""

from typing import Dict, Any, Tuple, List

# Valid operations for common n8n nodes
# Source: n8n documentation
VALID_NODE_OPERATIONS = {
    # Google Suite
    "n8n-nodes-base.googleDrive": [
        "copy", "createFolder", "delete", "download", "list", 
        "move", "share", "update", "upload"
    ],
    "n8n-nodes-base.googleSheets": [
        "append", "appendOrUpdate", "clear", "create", "delete",
        "lookup", "read", "update"
    ],
    "n8n-nodes-base.gmail": [
        "draft", "send", "get", "getAll", "delete", 
        "addLabels", "removeLabels", "markAsRead", "markAsUnread"
    ],
    
    # Communication
    "n8n-nodes-base.telegram": [
        "sendMessage", "sendPhoto", "sendDocument", "sendAudio",
        "sendVideo", "sendSticker", "sendAnimation", "sendLocation",
        "editMessageText", "deleteMessage", "pinChatMessage",
        "unpinChatMessage", "answerCallbackQuery", "getChat",
        "getChatMember", "leaveChat", "setChatDescription"
    ],
    "n8n-nodes-base.slack": [
        "create", "archive", "close", "get", "getAll", "history",
        "invite", "join", "kick", "leave", "member", "open",
        "rename", "replies", "setPurpose", "setTopic", "unarchive",
        "post", "postEphemeral", "postMessage", "sendMessage", "update", "delete", "getPermalink",
        "upload", "getFile"
    ],
    "n8n-nodes-base.discord": [
        "sendMessage", "getMessages", "deleteMessage"
    ],
    
    # E-commerce
    "n8n-nodes-base.shopify": [
        "create", "delete", "get", "getAll", "update"
    ],
    "n8n-nodes-base.wooCommerce": [
        "create", "delete", "get", "getAll", "update"
    ],
    
    # CRM
    "n8n-nodes-base.hubspot": [
        "create", "delete", "get", "getAll", "update", 
        "getRecentlyCreated", "getRecentlyModified", "search"
    ],
    "n8n-nodes-base.salesforce": [
        "create", "delete", "get", "getAll", "update", "upsert"
    ],
    
    # Databases
    "n8n-nodes-base.postgres": [
        "executeQuery", "insert", "update", "delete"
    ],
    "n8n-nodes-base.mysql": [
        "executeQuery", "insert", "update", "delete"
    ],
    "n8n-nodes-base.mongodb": [
        "aggregate", "delete", "find", "findAndReplace",
        "findAndUpdate", "insert", "update"
    ],
    
    # Dev Tools
    "n8n-nodes-base.github": [
        "create", "createRelease", "delete", "edit", "get", 
        "getIssues", "getRepositories", "lock", "unlock"
    ],
    "n8n-nodes-base.gitlab": [
        "create", "delete", "edit", "get", "getAll"
    ],
    "n8n-nodes-base.jira": [
        "create", "delete", "get", "getAll", "notify", "update"
    ],
    
    # HTTP/Webhook
    "n8n-nodes-base.httpRequest": [
        "delete", "get", "head", "options", "patch", "post", "put"
    ],
    
    # Airtable/Notion
    "n8n-nodes-base.airtable": [
        "append", "delete", "list", "read", "update"
    ],
    "n8n-nodes-base.notion": [
        "append", "create", "get", "getAll", "search", "update"
    ],
    
    # AI
    "n8n-nodes-base.openAi": [
        "complete", "edit", "image", "moderate"
    ],
}

# Trigger nodes (no operation parameter)
TRIGGER_NODES = [
    "n8n-nodes-base.webhook",
    "n8n-nodes-base.telegramTrigger",
    "n8n-nodes-base.gmailTrigger",
    "n8n-nodes-base.googleDriveTrigger",
    "n8n-nodes-base.shopifyTrigger",
    "n8n-nodes-base.slackTrigger",
    "n8n-nodes-base.githubTrigger",
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.cronTrigger",
    "n8n-nodes-base.cron",
    "n8n-nodes-base.schedule",
    "n8n-nodes-base.interval",
    "n8n-nodes-base.manualTrigger",
    "n8n-nodes-base.airtableTrigger",
    "n8n-nodes-base.notionTrigger",
    "n8n-nodes-base.formTrigger",
    "n8n-nodes-base.wooCommerceTrigger",
    "n8n-nodes-base.stripeTrigger",
    "n8n-nodes-base.hubspotTrigger",
    "n8n-nodes-base.typeformTrigger",
    "n8n-nodes-base.jiraTrigger",
    "n8n-nodes-base.gitlabTrigger",
    "n8n-nodes-base.trelloTrigger",
]

# Utility nodes (no operation parameter)
UTILITY_NODES = [
    "n8n-nodes-base.set",
    "n8n-nodes-base.if",
    "n8n-nodes-base.switch",
    "n8n-nodes-base.merge",
    "n8n-nodes-base.splitInBatches",
    "n8n-nodes-base.splitOut",
    "n8n-nodes-base.function",
    "n8n-nodes-base.functionItem",
    "n8n-nodes-base.code",
    "n8n-nodes-base.noOp",
    "n8n-nodes-base.stopAndError",
    "n8n-nodes-base.stickyNote",
    "n8n-nodes-base.filter",
    "n8n-nodes-base.sort",
    "n8n-nodes-base.limit",
    "n8n-nodes-base.removeDuplicates",
    "n8n-nodes-base.itemLists",
    "n8n-nodes-base.dateTime",
    "n8n-nodes-base.crypto",
    "n8n-nodes-base.xml",
    "n8n-nodes-base.html",
    "n8n-nodes-base.markdown",
    "n8n-nodes-base.rssFeedRead",
    "n8n-nodes-base.httpRequest",
    "n8n-nodes-base.wait",
    "n8n-nodes-base.executeCommand",
    "n8n-nodes-base.readBinaryFile",
    "n8n-nodes-base.writeBinaryFile",
    "n8n-nodes-base.spreadsheetFile",
    "n8n-nodes-base.convertToFile",
    "n8n-nodes-base.extractFromFile",
    "n8n-nodes-base.aggregate",
    "n8n-nodes-base.summarize",
    "n8n-nodes-base.compareDatasets",
]


def validate_operations(workflow: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate that all node operations in the workflow actually exist in n8n.
    
    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    warnings = []
    
    nodes = workflow.get("nodes", [])
    
    for node in nodes:
        node_type = node.get("type", "")
        node_name = node.get("name", "Unknown")
        params = node.get("parameters", {})
        operation = params.get("operation")
        
        # Skip trigger and utility nodes
        if node_type in TRIGGER_NODES or node_type in UTILITY_NODES:
            continue
        
        # Check if we know this node type
        if node_type in VALID_NODE_OPERATIONS:
            valid_ops = VALID_NODE_OPERATIONS[node_type]
            
            # If operation is specified, check if it's valid
            if operation and operation not in valid_ops:
                errors.append(
                    f"[{node_name}] Invalid operation '{operation}' for {node_type}. "
                    f"Valid: {', '.join(valid_ops[:5])}..."
                )
        else:
            # Unknown node type - might be valid, just not in our registry
            warnings.append(f"[{node_name}] Unknown node type: {node_type}")
    
    is_valid = len(errors) == 0
    return is_valid, errors + warnings


def validate_connections(workflow: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate that connections reference existing nodes by name.
    """
    errors = []
    
    nodes = workflow.get("nodes", [])
    connections = workflow.get("connections", {})
    
    # Get all node names
    node_names = {node.get("name") for node in nodes}
    
    # Check each connection
    for source_node, outputs in connections.items():
        # Check source exists
        if source_node not in node_names:
            errors.append(f"Connection source '{source_node}' not found in nodes")
            continue
        
        # Check targets exist
        if "main" in outputs:
            for output_list in outputs["main"]:
                for connection in output_list:
                    target = connection.get("node")
                    if target and target not in node_names:
                        errors.append(f"Connection target '{target}' not found in nodes")
    
    is_valid = len(errors) == 0
    return is_valid, errors


def validate_required_fields(workflow: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate that all nodes have required fields.
    """
    errors = []
    
    nodes = workflow.get("nodes", [])
    
    for i, node in enumerate(nodes):
        if not node.get("name"):
            errors.append(f"Node {i} missing 'name' field")
        if not node.get("type"):
            errors.append(f"Node {i} missing 'type' field")
        if not node.get("id"):
            errors.append(f"Node '{node.get('name', i)}' missing 'id' field")
    
    is_valid = len(errors) == 0
    return is_valid, errors


def validate_workflow(workflow: Dict[str, Any]) -> Tuple[bool, List[str], str]:
    """
    Full workflow validation.
    
    Returns:
        (is_valid, all_issues, summary)
    """
    all_issues = []
    
    # Basic structure
    if not workflow.get("nodes"):
        return False, ["Workflow has no nodes"], "INVALID: No nodes"
    
    if not workflow.get("connections"):
        all_issues.append("Warning: Workflow has no connections (nodes not linked)")
    
    # Validate each aspect
    valid_fields, field_errors = validate_required_fields(workflow)
    all_issues.extend(field_errors)
    
    valid_ops, op_errors = validate_operations(workflow)
    all_issues.extend(op_errors)
    
    valid_conns, conn_errors = validate_connections(workflow)
    all_issues.extend(conn_errors)
    
    # Determine overall validity
    is_valid = valid_fields and valid_ops and valid_conns
    
    # Summary
    if is_valid and not all_issues:
        summary = "VALID: All checks passed"
    elif is_valid:
        summary = f"VALID with warnings: {len(all_issues)} issue(s)"
    else:
        error_count = len([i for i in all_issues if not i.startswith("Warning")])
        summary = f"INVALID: {error_count} error(s)"
    
    return is_valid, all_issues, summary


def calculate_confidence(
    workflow: Dict[str, Any], 
    top_similarity: float = 0.0
) -> Tuple[float, str]:
    """
    Calculate confidence score for a generated workflow.
    
    Returns:
        (confidence_score 0-1, explanation)
    """
    score = 0.5  # Base score
    reasons = []
    
    # Factor 1: Validation passes
    is_valid, issues, _ = validate_workflow(workflow)
    if is_valid:
        score += 0.2
        reasons.append("+0.2 validation passed")
    else:
        score -= 0.2
        reasons.append("-0.2 validation failed")
    
    # Factor 2: High similarity to references
    if top_similarity > 0.7:
        score += 0.15
        reasons.append(f"+0.15 high similarity ({top_similarity:.2f})")
    elif top_similarity > 0.5:
        score += 0.05
        reasons.append(f"+0.05 medium similarity ({top_similarity:.2f})")
    elif top_similarity < 0.3:
        score -= 0.1
        reasons.append(f"-0.1 low similarity ({top_similarity:.2f})")
    
    # Factor 3: Workflow complexity
    node_count = len(workflow.get("nodes", []))
    if node_count <= 3:
        score += 0.1
        reasons.append(f"+0.1 simple workflow ({node_count} nodes)")
    elif node_count > 8:
        score -= 0.1
        reasons.append(f"-0.1 complex workflow ({node_count} nodes)")
    
    # Factor 4: All node types recognized
    nodes = workflow.get("nodes", [])
    unknown_types = sum(
        1 for n in nodes 
        if n.get("type") not in VALID_NODE_OPERATIONS 
        and n.get("type") not in TRIGGER_NODES 
        and n.get("type") not in UTILITY_NODES
    )
    if unknown_types == 0:
        score += 0.05
        reasons.append("+0.05 all node types recognized")
    else:
        score -= 0.05 * unknown_types
        reasons.append(f"-{0.05 * unknown_types:.2f} unknown node types")
    
    # Clamp to 0-1
    score = max(0.0, min(1.0, score))
    
    # Generate explanation
    if score >= 0.8:
        level = "HIGH"
    elif score >= 0.6:
        level = "MEDIUM"
    else:
        level = "LOW"
    
    explanation = f"{level} ({score:.0%}): " + ", ".join(reasons)
    
    return score, explanation


# CLI test
if __name__ == "__main__":
    # Test workflow
    test_workflow = {
        "name": "Test Workflow",
        "nodes": [
            {
                "id": "1",
                "name": "Telegram Trigger",
                "type": "n8n-nodes-base.telegramTrigger",
                "parameters": {}
            },
            {
                "id": "2", 
                "name": "Reply",
                "type": "n8n-nodes-base.telegram",
                "parameters": {
                    "operation": "sendMessage",
                    "text": "Hello!",
                    "chatId": "={{$json.message.chat.id}}"
                }
            }
        ],
        "connections": {
            "Telegram Trigger": {
                "main": [[{"node": "Reply", "type": "main", "index": 0}]]
            }
        }
    }
    
    is_valid, issues, summary = validate_workflow(test_workflow)
    print(f"Validation: {summary}")
    for issue in issues:
        print(f"  - {issue}")
    
    confidence, explanation = calculate_confidence(test_workflow, 0.85)
    print(f"\nConfidence: {explanation}")

