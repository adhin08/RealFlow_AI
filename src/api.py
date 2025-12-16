"""
RAG V3 REST API

FastAPI server for the n8n workflow generator.
This is the foundation for your SaaS.
"""

import os
import sys
import json
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env if present (override existing to ensure freshest keys)
load_dotenv(override=True)

# Set RAG version
os.environ["RAG_VERSION"] = "v3"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_INDEX = os.path.join(os.path.dirname(BASE_DIR), "frontend", "index.html")

from rag import search_workflows
from ai_builder import (
    build_prompt_from_query_and_workflows,
    call_llm_with_prompt,
    parse_llm_response_for_workflow,
    validate_workflow_json,
)
from validator import validate_workflow, calculate_confidence
from n8n_client import get_n8n_config, upload_workflow_to_n8n

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="RealFlow AI API",
    description="AI-powered n8n workflow generation using RAG. Generate production-ready automations from natural language.",
    version="3.0.0"
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Models
# ============================================================================

class GenerateRequest(BaseModel):
    query: str
    top_k: int = 3
    upload_to_n8n: bool = False

class WorkflowResponse(BaseModel):
    id: str
    query: str
    status: str  # "success", "warning", "error"
    confidence: float
    confidence_label: str
    implementation_plan: str
    workflow: dict
    validation: dict
    references: List[dict]
    n8n_url: Optional[str] = None
    created_at: str

class HealthResponse(BaseModel):
    status: str
    rag_version: str
    workflow_count: int

# ============================================================================
# Storage (In-memory for demo, use DB for production)
# ============================================================================

generated_workflows = {}

# ============================================================================
# Endpoints
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the landing page frontend (static HTML)."""
    if os.path.exists(FRONTEND_INDEX):
        return FileResponse(FRONTEND_INDEX)
    return HTMLResponse(
        "<h1>RealFlow AI</h1><p>Frontend not found. Add frontend/index.html.</p>",
        status_code=404,
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check API health and RAG status."""
    try:
        import chromadb
        client = chromadb.PersistentClient(path="./chroma_db")
        collection = client.get_collection("n8n_workflows_v3")
        count = collection.count()
    except:
        count = 0
    
    return {
        "status": "healthy",
        "rag_version": "v3",
        "workflow_count": count
    }


@app.post("/generate", response_model=WorkflowResponse)
async def generate_workflow(request: GenerateRequest):
    """
    Generate an n8n workflow from natural language.
    
    This is the main endpoint for your SaaS.
    """
    workflow_id = str(uuid.uuid4())[:8]
    
    try:
        # Step 1: RAG Retrieval
        results = list(search_workflows(request.query, n_results=request.top_k))
        
        if not results:
            raise HTTPException(status_code=404, detail="No reference workflows found")
        
        references = []
        for doc, meta, score in results:
            references.append({
                "filename": meta.get("filename", "unknown"),
                "score": round(score, 4),
                "categories": meta.get("categories", ""),
                "integrations": meta.get("integrations", "")
            })
        
        # Step 2: Build prompt and call LLM
        prompt = build_prompt_from_query_and_workflows(request.query, results)
        response = call_llm_with_prompt(prompt)
        
        if not response:
            raise HTTPException(status_code=500, detail="LLM returned empty response")
        
        # Step 3: Parse response
        implementation_plan, workflow = parse_llm_response_for_workflow(response)
        
        if workflow is None:
            raise HTTPException(status_code=500, detail="Failed to parse workflow JSON from LLM response")
        
        # Step 4: Validate
        is_valid, error_msg = validate_workflow_json(workflow)
        adv_valid, issues, summary = validate_workflow(workflow)
        
        top_similarity = results[0][2] if results else 0.0
        confidence, conf_explanation = calculate_confidence(workflow, top_similarity)
        
        # Determine status
        if not is_valid:
            status = "error"
        elif not adv_valid:
            status = "warning"
        else:
            status = "success"
        
        # Confidence label
        if confidence >= 0.8:
            conf_label = "HIGH"
        elif confidence >= 0.6:
            conf_label = "MEDIUM"
        else:
            conf_label = "LOW"
        
        validation = {
            "basic_valid": is_valid,
            "basic_error": error_msg if not is_valid else None,
            "advanced_valid": adv_valid,
            "advanced_summary": summary,
            "issues": issues[:5]  # First 5 issues
        }
        
        # Step 5: Optional n8n upload
        n8n_url = None
        if request.upload_to_n8n and is_valid:
            config = get_n8n_config()
            if config:
                try:
                    name = f"AI_Generated_{request.query[:40].replace(' ', '_')}"
                    success, upload_result = upload_workflow_to_n8n(workflow, name, config)
                    if success and upload_result and "id" in upload_result:
                        n8n_url = f"{config['url']}/workflow/{upload_result['id']}"
                except Exception:
                    # Keep silent in API response to avoid failing generation flow
                    pass  # Silent fail for n8n upload
        
        # Build response
        result = WorkflowResponse(
            id=workflow_id,
            query=request.query,
            status=status,
            confidence=round(confidence, 2),
            confidence_label=conf_label,
            implementation_plan=implementation_plan or "No plan provided",
            workflow=workflow,
            validation=validation,
            references=references,
            n8n_url=n8n_url,
            created_at=datetime.utcnow().isoformat()
        )
        
        # Store for retrieval
        generated_workflows[workflow_id] = result.dict()
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workflow/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Retrieve a previously generated workflow."""
    if workflow_id not in generated_workflows:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return generated_workflows[workflow_id]


@app.get("/workflows")
async def list_workflows(limit: int = 10):
    """List recent generated workflows."""
    workflows = list(generated_workflows.values())[-limit:]
    return {"workflows": workflows, "total": len(generated_workflows)}


# ============================================================================
# Run with: uvicorn src.api:app --reload --port 8000
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

