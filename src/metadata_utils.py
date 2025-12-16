"""
Metadata utilities for n8n workflow RAG system.
Provides helpers to extract services, categories, and perform reranking.
"""

from typing import List, Dict, Any, Set
import re

# ============================================================================
# SERVICE DETECTION
# ============================================================================

# Map of normalized service IDs to their detection patterns (node types, names)
SERVICE_PATTERNS = {
    "shopify": ["shopify"],
    "woocommerce": ["woocommerce"],
    "stripe": ["stripe"],
    "paypal": ["paypal"],
    "slack": ["slack"],
    "telegram": ["telegram"],
    "discord": ["discord"],
    "whatsapp": ["whatsapp"],
    "gmail": ["gmail"],
    "googlesheets": ["googlesheets", "google sheets", "spreadsheet"],
    "googledrive": ["googledrive", "google drive"],
    "googlecalendar": ["googlecalendar", "google calendar"],
    "airtable": ["airtable"],
    "notion": ["notion"],
    "nocodb": ["nocodb"],
    "hubspot": ["hubspot"],
    "salesforce": ["salesforce"],
    "zendesk": ["zendesk"],
    "mautic": ["mautic"],
    "mailchimp": ["mailchimp"],
    "sendgrid": ["sendgrid"],
    "twilio": ["twilio"],
    "openai": ["openai", "chatgpt", "gpt"],
    "mysql": ["mysql"],
    "postgres": ["postgres", "postgresql"],
    "mongodb": ["mongodb", "mongo"],
    "redis": ["redis"],
    "webhook": ["webhook"],
    "http": ["httprequest", "http request"],
    "typeform": ["typeform"],
    "jotform": ["jotform"],
    "webflow": ["webflow"],
    "wordpress": ["wordpress"],
    "twitter": ["twitter"],
    "facebook": ["facebook"],
    "linkedin": ["linkedin"],
    "dropbox": ["dropbox"],
    "onedrive": ["onedrive"],
    "box": ["box.com", "boxnode"],
    "trello": ["trello"],
    "asana": ["asana"],
    "jira": ["jira"],
    "github": ["github"],
    "gitlab": ["gitlab"],
    "bitbucket": ["bitbucket"],
    "aws": ["aws", "amazon"],
    "azure": ["azure"],
    "gcp": ["gcp", "googlecloud"],
    "cron": ["cron", "schedule", "interval"],
    "onfleet": ["onfleet"],
    "mqtt": ["mqtt"],
    "graphql": ["graphql"],
    "ftp": ["ftp", "sftp"],
}

def infer_services_from_workflow(workflow_json: Dict[str, Any]) -> List[str]:
    """
    Inspects a workflow JSON and extracts a list of service identifiers.
    Looks at node types, node names, and credentials to infer services.
    
    Args:
        workflow_json: The parsed n8n workflow JSON
        
    Returns:
        List of normalized service IDs (lowercase, e.g., ["shopify", "slack", "googlesheets"])
    """
    detected_services: Set[str] = set()
    
    nodes = workflow_json.get("nodes", [])
    if not isinstance(nodes, list):
        return []
    
    for node in nodes:
        node_type = node.get("type", "").lower()
        node_name = node.get("name", "").lower()
        
        # Check against all service patterns
        for service_id, patterns in SERVICE_PATTERNS.items():
            for pattern in patterns:
                if pattern in node_type or pattern in node_name:
                    detected_services.add(service_id)
                    break
        
        # Also check credentials field if present
        credentials = node.get("credentials", {})
        if isinstance(credentials, dict):
            for cred_key in credentials.keys():
                cred_lower = cred_key.lower()
                for service_id, patterns in SERVICE_PATTERNS.items():
                    for pattern in patterns:
                        if pattern in cred_lower:
                            detected_services.add(service_id)
                            break
    
    return sorted(list(detected_services))


# ============================================================================
# CATEGORY DETECTION
# ============================================================================

# Categories and their detection rules
# Each category has keywords that might appear in node types, names, descriptions
CATEGORY_RULES = {
    "ecommerce": {
        "services": ["shopify", "woocommerce", "stripe", "paypal"],
        "keywords": ["order", "product", "cart", "checkout", "purchase", "payment"]
    },
    "notification": {
        "services": ["slack", "telegram", "discord", "whatsapp", "email"],
        "keywords": ["notify", "alert", "message", "send", "notification"]
    },
    "data-sync": {
        "services": ["googlesheets", "airtable", "nocodb", "notion"],
        "keywords": ["sync", "update", "append", "row", "record", "database"]
    },
    "lead-processing": {
        "services": ["hubspot", "salesforce", "mautic", "mailchimp"],
        "keywords": ["lead", "contact", "crm", "prospect", "customer", "signup"]
    },
    "file-management": {
        "services": ["googledrive", "dropbox", "onedrive", "box", "ftp"],
        "keywords": ["file", "attachment", "upload", "download", "document", "pdf"]
    },
    "form-processing": {
        "services": ["typeform", "jotform", "webhook"],
        "keywords": ["form", "submission", "response", "survey"]
    },
    "ai-summary": {
        "services": ["openai"],
        "keywords": ["ai", "summarize", "summary", "classify", "generate", "llm", "gpt", "chatgpt"]
    },
    "error-handling": {
        "services": [],
        "keywords": ["error", "fail", "failure", "exception", "retry", "catch", "errorhandler"]
    },
    "scheduling": {
        "services": ["cron"],
        "keywords": ["schedule", "cron", "interval", "timer", "periodic", "hourly", "daily", "weekly"]
    },
    "calendar": {
        "services": ["googlecalendar"],
        "keywords": ["calendar", "event", "meeting", "appointment", "schedule"]
    },
    "social-media": {
        "services": ["twitter", "facebook", "linkedin"],
        "keywords": ["tweet", "post", "social", "share"]
    },
    "dev-tools": {
        "services": ["github", "gitlab", "bitbucket", "jira"],
        "keywords": ["git", "commit", "issue", "pull request", "repository", "deploy"]
    },
    "support": {
        "services": ["zendesk"],
        "keywords": ["ticket", "support", "helpdesk", "customer service"]
    }
}


def infer_categories_from_workflow(workflow_json: Dict[str, Any], services: List[str] = None) -> List[str]:
    """
    Infers use-case categories for a workflow based on its nodes, services, and content.
    
    Args:
        workflow_json: The parsed n8n workflow JSON
        services: Optional pre-computed list of services (if None, will be inferred)
        
    Returns:
        List of category IDs (e.g., ["ecommerce", "notification", "data-sync"])
    """
    if services is None:
        services = infer_services_from_workflow(workflow_json)
    
    detected_categories: Set[str] = set()
    
    # Build a searchable text blob from the workflow
    text_blob = ""
    nodes = workflow_json.get("nodes", [])
    if isinstance(nodes, list):
        for node in nodes:
            text_blob += " " + node.get("type", "").lower()
            text_blob += " " + node.get("name", "").lower()
            notes = node.get("notes", "")
            if notes:
                text_blob += " " + notes.lower()
    
    # Also check workflow name and tags
    text_blob += " " + workflow_json.get("name", "").lower()
    tags = workflow_json.get("tags", [])
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict):
                text_blob += " " + tag.get("name", "").lower()
            elif isinstance(tag, str):
                text_blob += " " + tag.lower()
    
    # Check each category
    for category, rules in CATEGORY_RULES.items():
        # Check if any of the required services are present
        if rules["services"]:
            if any(s in services for s in rules["services"]):
                detected_categories.add(category)
                continue
        
        # Check keywords in text blob
        for keyword in rules["keywords"]:
            if keyword in text_blob:
                detected_categories.add(category)
                break
    
    return sorted(list(detected_categories))


# ============================================================================
# QUERY PARSING
# ============================================================================

def extract_services_from_query(query: str) -> List[str]:
    """
    Extracts service identifiers mentioned in a user query.
    Used for reranking search results.
    
    Args:
        query: The user's natural language query
        
    Returns:
        List of detected service IDs
    """
    query_lower = query.lower()
    detected: Set[str] = set()
    
    # Direct service name matching
    for service_id, patterns in SERVICE_PATTERNS.items():
        for pattern in patterns:
            # Use word boundary check to avoid partial matches
            # e.g., "shop" shouldn't match "shopify"
            if re.search(r'\b' + re.escape(pattern) + r'\b', query_lower):
                detected.add(service_id)
                break
    
    return sorted(list(detected))


def infer_desired_categories_from_query(query: str) -> List[str]:
    """
    Infers what categories a query might be looking for.
    Used for category-based reranking.
    
    Args:
        query: The user's natural language query
        
    Returns:
        List of desired category IDs
    """
    q = query.lower()
    desired: Set[str] = set()
    
    # Error handling / monitoring
    if any(word in q for word in ["error", "fail", "failure", "exception", "retry", "alert"]):
        desired.add("error-handling")
    
    # Lead processing
    if any(word in q for word in ["lead", "signup", "prospect", "contact", "crm"]):
        desired.add("lead-processing")
    
    # File management
    if any(word in q for word in ["file", "attachment", "pdf", "document", "upload", "download"]):
        desired.add("file-management")
    
    # Notification
    if any(word in q for word in ["notify", "notification", "alert", "message"]):
        desired.add("notification")
    
    # Form processing
    if any(word in q for word in ["form", "typeform", "submission", "response", "survey"]):
        desired.add("form-processing")
    
    # AI / Summary
    if any(word in q for word in ["summary", "summarize", "openai", "ai ", " ai", "llm", "gpt", "classify", "generate"]):
        desired.add("ai-summary")
    
    # E-commerce
    if any(word in q for word in ["order", "shopify", "woocommerce", "product", "cart", "checkout"]):
        desired.add("ecommerce")
    
    # Data sync
    if any(word in q for word in ["sync", "spreadsheet", "sheet", "row", "record", "database", "append"]):
        desired.add("data-sync")
    
    # Calendar
    if any(word in q for word in ["calendar", "event", "meeting", "appointment"]):
        desired.add("calendar")
    
    # Scheduling
    if any(word in q for word in ["schedule", "cron", "hourly", "daily", "weekly", "interval"]):
        desired.add("scheduling")
    
    # Support
    if any(word in q for word in ["ticket", "support", "helpdesk", "zendesk"]):
        desired.add("support")
    
    return sorted(list(desired))


# ============================================================================
# RERANKING
# ============================================================================

def rerank_by_service_and_category(
    query: str, 
    results: List[tuple],
    service_bonus: float = 0.15,
    category_bonus: float = 0.08
) -> List[tuple]:
    """
    Reranks search results based on service and category matching.
    
    If the query mentions specific services (e.g., "Shopify"), workflows
    that use those services get a score boost. Similarly, if the query
    implies certain categories (e.g., "error handling"), matching workflows
    are boosted.
    
    Args:
        query: The user's query
        results: List of (document, metadata, score) tuples from search
        service_bonus: Score bonus for matching services (default 0.05)
        category_bonus: Score bonus for matching categories (default 0.03)
        
    Returns:
        Reranked list of (document, metadata, adjusted_score) tuples
    """
    requested_services = extract_services_from_query(query)
    desired_categories = infer_desired_categories_from_query(query)
    
    if not requested_services and not desired_categories:
        return results
    
    reranked = []
    for item in results:
        doc, meta, score = item
        
        # Parse services from metadata (stored as comma-separated string)
        services_str = meta.get("services", "")
        services = [s.strip() for s in services_str.split(",") if s.strip()]
        
        # Parse categories from metadata
        categories_str = meta.get("categories", "")
        categories = [c.strip() for c in categories_str.split(",") if c.strip()]
        
        bonus = 0.0
        
        # Service matching bonus
        if requested_services and any(s in services for s in requested_services):
            bonus += service_bonus
        
        # Category matching bonus
        if desired_categories and any(c in categories for c in desired_categories):
            bonus += category_bonus
        
        # Note: In Chroma, lower distance = better match
        # So we subtract the bonus to improve ranking
        adjusted_score = score - bonus
        
        reranked.append((doc, meta, adjusted_score))
    
    # Sort by adjusted score (ascending for distance-based scores)
    reranked.sort(key=lambda x: x[2])
    
    return reranked

