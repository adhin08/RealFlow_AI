"""
STEP 3: Extract Deterministic Metadata
STEP 4: Generate DESCRIPTION (NO LLM)
STEP 5: Labeling (STRICT ENUMS)

Extracts metadata from sanitized workflow JSONs using deterministic rules.
NO hallucinations. NO guessing.
"""

import re
from typing import Dict, Any, List, Set


# ============================================================================
# STEP 5: STRICT CATEGORY ENUMS
# ============================================================================

CATEGORIES = [
    "ecommerce",
    "notification",
    "data-sync",
    "file-management",
    "error-handling",
    "ai",
    "communication",
    "database",
    "webhook",
    "unknown"
]

# Node type to category mapping
NODE_TO_CATEGORY = {
    # E-commerce
    "shopify": "ecommerce",
    "woocommerce": "ecommerce",
    "stripe": "ecommerce",
    "paypal": "ecommerce",
    "magento": "ecommerce",
    
    # Notification
    "telegram": "notification",
    "slack": "notification",
    "discord": "notification",
    "email": "notification",
    "gmail": "notification",
    "twilio": "notification",
    "mattermost": "notification",
    "pushover": "notification",
    
    # Communication
    "telegramtrigger": "communication",
    "slacktrigger": "communication",
    "whatsapp": "communication",
    
    # Data Sync
    "googlesheets": "data-sync",
    "airtable": "data-sync",
    "notion": "data-sync",
    "spreadsheetfile": "data-sync",
    
    # File Management
    "googledrive": "file-management",
    "dropbox": "file-management",
    "box": "file-management",
    "ftp": "file-management",
    "s3": "file-management",
    "awss3": "file-management",
    
    # Database
    "postgres": "database",
    "mysql": "database",
    "mongodb": "database",
    "redis": "database",
    "elasticsearch": "database",
    
    # AI
    "openai": "ai",
    "anthropic": "ai",
    "gemini": "ai",
    "huggingface": "ai",
    
    # Webhook
    "webhook": "webhook",
    "respondtowebhook": "webhook",
    
    # Error Handling
    "stopanderror": "error-handling",
    "errorworkflow": "error-handling",
}

# Trigger type inference
TRIGGER_TYPES = {
    "webhook": ["webhook", "respondtowebhook"],
    "schedule": ["cron", "schedule", "interval", "scheduletrigger"],
    "service": [
        "telegramtrigger", "slacktrigger", "gmailTrigger", "shopifytrigger",
        "githubtrigger", "airtabletrigger", "typeformtrigger", "formtrigger",
        "hubspottrigger", "stripetrigger", "googlesheetstrigger", "notionTrigger"
    ],
    "manual": ["manualtrigger", "manualTrigger", "executeworkflowtrigger"]
}

# Integration name mapping (node type -> display name)
INTEGRATION_NAMES = {
    "googlesheets": "Google Sheets",
    "googledrive": "Google Drive",
    "googlecalendar": "Google Calendar",
    "gmail": "Gmail",
    "gmailTrigger": "Gmail",
    "telegram": "Telegram",
    "telegramtrigger": "Telegram",
    "slack": "Slack",
    "slacktrigger": "Slack",
    "discord": "Discord",
    "airtable": "Airtable",
    "notion": "Notion",
    "shopify": "Shopify",
    "shopifytrigger": "Shopify",
    "woocommerce": "WooCommerce",
    "stripe": "Stripe",
    "paypal": "PayPal",
    "github": "GitHub",
    "githubtrigger": "GitHub",
    "gitlab": "GitLab",
    "jira": "Jira",
    "trello": "Trello",
    "asana": "Asana",
    "hubspot": "HubSpot",
    "salesforce": "Salesforce",
    "mongodb": "MongoDB",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "redis": "Redis",
    "openai": "OpenAI",
    "http": "HTTP Request",
    "httprequest": "HTTP Request",
    "webhook": "Webhook",
    "cron": "Cron",
    "schedule": "Schedule",
    "emailsend": "Email",
    "emailreadimap": "Email (IMAP)",
    "dropbox": "Dropbox",
    "awss3": "AWS S3",
    "typeform": "Typeform",
    "typeformtrigger": "Typeform",
    "mattermost": "Mattermost",
    "twilio": "Twilio",
    "whatsapp": "WhatsApp",
}


def extract_node_types(workflow: Dict[str, Any]) -> List[str]:
    """
    Extract unique node types from workflow.
    """
    node_types = set()
    
    for node in workflow.get('nodes', []):
        node_type = node.get('type', '')
        # Extract the simple type name (e.g., "googleSheets" from "n8n-nodes-base.googleSheets")
        if '.' in node_type:
            simple_type = node_type.split('.')[-1]
        else:
            simple_type = node_type
        
        if simple_type:
            node_types.add(simple_type.lower())
    
    return sorted(list(node_types))


def infer_trigger_type(workflow: Dict[str, Any]) -> str:
    """
    Infer the trigger type from the workflow.
    Rules-based, NO guessing.
    """
    nodes = workflow.get('nodes', [])
    
    for node in nodes:
        node_type = node.get('type', '').lower()
        node_name = node.get('name', '').lower()
        
        # Extract simple type
        if 'n8n-nodes-base.' in node_type:
            simple_type = node_type.split('.')[-1]
        else:
            simple_type = node_type
        
        # Check against known trigger types
        for trigger_category, trigger_types in TRIGGER_TYPES.items():
            for t in trigger_types:
                if t.lower() in simple_type or t.lower() in node_name:
                    return trigger_category
    
    # If no clear trigger found
    return "unknown"


def infer_integrations(workflow: Dict[str, Any]) -> List[str]:
    """
    Infer integration names from node types.
    """
    integrations = set()
    
    for node in workflow.get('nodes', []):
        node_type = node.get('type', '').lower()
        
        # Extract simple type
        if 'n8n-nodes-base.' in node_type:
            simple_type = node_type.split('.')[-1]
        else:
            simple_type = node_type
        
        # Look up integration name
        for key, name in INTEGRATION_NAMES.items():
            if key.lower() in simple_type:
                integrations.add(name)
                break
    
    return sorted(list(integrations))


def infer_categories(workflow: Dict[str, Any]) -> List[str]:
    """
    Infer categories using STRICT ENUMS only.
    """
    categories = set()
    
    for node in workflow.get('nodes', []):
        node_type = node.get('type', '').lower()
        
        # Extract simple type
        if 'n8n-nodes-base.' in node_type:
            simple_type = node_type.split('.')[-1]
        else:
            simple_type = node_type
        
        # Look up category
        for key, category in NODE_TO_CATEGORY.items():
            if key.lower() in simple_type:
                categories.add(category)
                break
    
    # If no categories found, use unknown
    if not categories:
        categories.add("unknown")
    
    # Validate all categories are in CATEGORIES enum
    categories = {c for c in categories if c in CATEGORIES}
    if not categories:
        categories.add("unknown")
    
    return sorted(list(categories))


def check_has_error_handler(workflow: Dict[str, Any]) -> bool:
    """
    Check if workflow has an error handler node.
    """
    for node in workflow.get('nodes', []):
        node_type = node.get('type', '').lower()
        node_name = node.get('name', '').lower()
        
        if 'error' in node_type or 'error' in node_name:
            return True
        if 'stopanderror' in node_type:
            return True
    
    return False


# ============================================================================
# STEP 3: EXTRACT METADATA
# ============================================================================

def extract_metadata(workflow: Dict[str, Any], filename: str) -> Dict[str, Any]:
    """
    Extract deterministic metadata from a workflow.
    NO hallucinations. NO guessing.
    """
    node_types = extract_node_types(workflow)
    
    metadata = {
        "filename": filename,
        "node_count": len(workflow.get('nodes', [])),
        "node_types": node_types,
        "trigger_type": infer_trigger_type(workflow),
        "integrations": infer_integrations(workflow),
        "categories": infer_categories(workflow),
        "has_error_handler": check_has_error_handler(workflow),
        "connection_count": len(workflow.get('connections', {}))
    }
    
    return metadata


# ============================================================================
# STEP 4: GENERATE DESCRIPTION (NO LLM)
# ============================================================================

def generate_description(workflow: Dict[str, Any], metadata: Dict[str, Any]) -> str:
    """
    Generate a template description using rules, NOT AI.
    NO creative wording. NO assumptions. If unknown -> say "unknown".
    """
    trigger_type = metadata.get('trigger_type', 'unknown')
    integrations = metadata.get('integrations', [])
    has_error = metadata.get('has_error_handler', False)
    
    # Build trigger description
    trigger_desc = {
        "webhook": "via a webhook",
        "schedule": "on a schedule",
        "service": "when a service event occurs",
        "manual": "manually",
        "unknown": "with an unknown trigger"
    }.get(trigger_type, "with an unknown trigger")
    
    # Build integration description
    if integrations:
        if len(integrations) == 1:
            integration_desc = f"using {integrations[0]}"
        elif len(integrations) == 2:
            integration_desc = f"using {integrations[0]} and {integrations[1]}"
        else:
            integration_desc = f"using {', '.join(integrations[:-1])}, and {integrations[-1]}"
    else:
        integration_desc = "using internal nodes"
    
    # Build error handling description
    error_desc = " It includes error handling." if has_error else ""
    
    # Compose description
    description = f"This workflow triggers {trigger_desc}. It processes data {integration_desc}.{error_desc}"
    
    return description


def generate_title(workflow: Dict[str, Any], metadata: Dict[str, Any]) -> str:
    """
    Generate a simple title based on integrations.
    """
    name = workflow.get('name', '')
    if name and name != 'Unnamed Workflow':
        # Clean up the name
        name = re.sub(r'[_-]+', ' ', name)
        return name.title()
    
    # Generate from integrations
    integrations = metadata.get('integrations', [])
    trigger_type = metadata.get('trigger_type', 'unknown')
    
    if integrations:
        if len(integrations) >= 2:
            return f"{integrations[0]} to {integrations[1]} Workflow"
        else:
            return f"{integrations[0]} Workflow"
    
    return f"{trigger_type.title()} Triggered Workflow"


def generate_one_liner(metadata: Dict[str, Any]) -> str:
    """
    Generate a one-line summary.
    """
    integrations = metadata.get('integrations', [])
    trigger_type = metadata.get('trigger_type', 'unknown')
    
    if integrations:
        integration_str = " and ".join(integrations[:2])
        return f"Automates {integration_str} integration with {trigger_type} trigger."
    
    return f"Workflow with {trigger_type} trigger."


if __name__ == "__main__":
    # Test metadata extraction
    test_workflow = {
        "name": "Test_Workflow",
        "nodes": [
            {"type": "n8n-nodes-base.webhook", "name": "Webhook"},
            {"type": "n8n-nodes-base.googleSheets", "name": "Google Sheets"},
            {"type": "n8n-nodes-base.slack", "name": "Slack"},
            {"type": "n8n-nodes-base.stopAndError", "name": "Error Handler"}
        ],
        "connections": {
            "Webhook": {"main": [[{"node": "Google Sheets"}]]},
            "Google Sheets": {"main": [[{"node": "Slack"}]]}
        }
    }
    
    metadata = extract_metadata(test_workflow, "test_workflow.json")
    description = generate_description(test_workflow, metadata)
    title = generate_title(test_workflow, metadata)
    one_liner = generate_one_liner(metadata)
    
    print(f"Title: {title}")
    print(f"One-liner: {one_liner}")
    print(f"Description: {description}")
    print(f"Metadata: {metadata}")










