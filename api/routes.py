"""
API route handlers for Spike AI.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime
import logging

from langchain_core.output_parsers import JsonOutputParser

from models import QueryRequest, QueryResponse, HealthResponse, QueryType
from utils import sanitize_for_json

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# Global orchestrator reference (will be set by main.py)
_orchestrator = None


def set_orchestrator(orchestrator):
    """Set the global orchestrator instance."""
    global _orchestrator
    _orchestrator = orchestrator


def get_orchestrator():
    """Get the global orchestrator instance."""
    return _orchestrator


@router.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint - health check."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        services={
            "orchestrator": "initialized" if get_orchestrator() else "not initialized",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    orchestrator = get_orchestrator()
    services_status = {
        "orchestrator": "healthy" if orchestrator else "unavailable",
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Check if orchestrator is available
    if not orchestrator:
        return HealthResponse(
            status="degraded",
            version="0.1.0",
            services=services_status
        )
    
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        services=services_status
    )


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    Main query endpoint for processing natural language queries.
    
    Accepts:
    - GA4 queries: {"propertyId": "123456789", "query": "top pages last week"}
    - SEO queries: {"query": "how many pages are not indexable?"}
    - Fusion queries: {"propertyId": "123456789", "query": "top traffic pages with SEO issues"}
    
    Returns structured response with natural language answer and optional data payload.
    """
    logger.info(f"Received query: {request.query[:100]}...")
    
    orchestrator = get_orchestrator()
    if not orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Service unavailable: Orchestrator not initialized"
        )
    
    try:
        # Process query through orchestrator
        start_time = datetime.utcnow()
        
        final_state = await orchestrator.process_query(
            query=request.query,
            property_id=request.propertyId
        )
        
        end_time = datetime.utcnow()
        duration_ms = (end_time - start_time).total_seconds() * 1000
        
        # Add timing metadata
        if not final_state.metadata:
            final_state.metadata = {}
        final_state.metadata["processing_time_ms"] = round(duration_ms, 2)
        
        # Sanitize data to prevent JSON serialization errors (NaN, Infinity)
        sanitized_data = sanitize_for_json(final_state.structured_data) if final_state.structured_data else None
        sanitized_metadata = sanitize_for_json(final_state.metadata)
        
        # Detect and parse JSON answers using LangChain's JsonOutputParser
        answer_type = "text"
        final_answer = final_state.answer or "No answer generated"
        
        if final_state.answer:
            answer_stripped = final_state.answer.strip()
            
            # Check if it looks like JSON (with or without markdown)
            if ('```' in answer_stripped or 
                answer_stripped.startswith('{') or 
                answer_stripped.startswith('[')):
                try:
                    # LangChain's JsonOutputParser handles markdown code blocks automatically
                    json_parser = JsonOutputParser()
                    parsed_json = json_parser.parse(answer_stripped)
                    final_answer = sanitize_for_json(parsed_json)
                    answer_type = "json"
                    logger.info(f"Parsed JSON answer: {type(parsed_json).__name__} with {len(str(parsed_json))} chars")
                except Exception as e:
                    # If parsing fails, leave as text
                    logger.warning(f"Failed to parse as JSON: {e}")
                    answer_type = "text"
        
        # Check if LLM service failed (quota exhausted, timeout, etc.)
        llm_service_error = sanitized_metadata.get("llm_service_error", False)
        
        if llm_service_error:
            # Return 500 Internal Server Error for LLM service failures
            logger.error(f"LLM service error in {duration_ms:.2f}ms")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "query_type": "unknown",
                    "answer": final_answer,
                    "answer_type": "text",
                    "data": None,
                    "metadata": sanitized_metadata,
                    "error": "LLM service temporarily unavailable (quota exceeded or timeout)"
                }
            )
        
        # Check if validation failed
        validation_failed = sanitized_metadata.get("validation_failed", False)
        
        if validation_failed:
            # Return 422 Unprocessable Entity for validation errors
            logger.warning(f"Query validation failed in {duration_ms:.2f}ms")
            return JSONResponse(
                status_code=422,
                content={
                    "success": False,
                    "query_type": final_state.query_type.value,
                    "answer": final_answer,
                    "answer_type": "text",
                    "data": None,
                    "metadata": sanitized_metadata,
                    "error": "Missing required parameter: propertyId"
                }
            )
        
        # Build response
        response = QueryResponse(
            success=bool(final_state.answer and not final_state.ga4_error and not final_state.seo_error),
            query_type=final_state.query_type,
            answer=final_answer,
            answer_type=answer_type,
            data=sanitized_data,
            metadata=sanitized_metadata,
            error=final_state.ga4_error or final_state.seo_error
        )
        
        logger.info(
            f"Query processed successfully in {duration_ms:.2f}ms. "
            f"Type: {final_state.query_type.value}"
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Query processing failed: {e}", exc_info=True)
        
        return QueryResponse(
            success=False,
            query_type=QueryType.UNKNOWN,
            answer=f"Error: {str(e)}",
            error=str(e),
            metadata={"error_type": type(e).__name__}
        )

