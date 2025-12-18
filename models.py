"""
Pydantic models for request/response validation.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, TypedDict, Union
from enum import Enum


class QueryType(str, Enum):
    """Type of query being processed."""
    GA4_ONLY = "ga4_only"
    SEO_ONLY = "seo_only"
    FUSION = "fusion"
    UNKNOWN = "unknown"


class QueryRequest(BaseModel):
    """Request model for /query endpoint."""
    
    query: str = Field(
        ...,
        description="Natural language query from the user",
        min_length=1,
        examples=["What are the top pages by traffic last week?"]
    )
    
    propertyId: Optional[str] = Field(
        None,
        description="GA4 property ID (required for GA4 queries)",
        examples=["123456789"]
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "query": "Show me top 10 pages by pageviews last 7 days",
                    "propertyId": "123456789"
                },
                {
                    "query": "How many pages are not indexable?"
                }
            ]
        }


class QueryResponse(BaseModel):
    """Response model for /query endpoint."""
    
    success: bool = Field(
        ...,
        description="Whether the query was processed successfully"
    )
    
    query_type: QueryType = Field(
        ...,
        description="Type of query that was detected and processed"
    )
    
    answer: Any = Field(
        ...,
        description="Answer to the query - string for text, parsed object/array for json"
    )
    
    answer_type: str = Field(
        "text",
        description="Format of the answer: 'text' (string) or 'json' (parsed object/array)"
    )
    
    data: Optional[Dict[str, Any]] = Field(
        None,
        description="Structured data payload (if applicable)"
    )
    
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional metadata about the query execution"
    )
    
    error: Optional[str] = Field(
        None,
        description="Error message if success=False"
    )


class HealthResponse(BaseModel):
    """Response model for health check."""
    
    status: str = Field(default="healthy")
    version: str = Field(default="0.1.0")
    services: Dict[str, str] = Field(
        default_factory=dict,
        description="Status of dependent services"
    )


class GraphState(TypedDict, total=False):
    """State object passed through LangGraph nodes as a dict."""
    
    # Input
    query: str
    property_id: Optional[str]
    
    # Routing
    query_type: QueryType
    
    # GA4 Agent Results
    ga4_plan: Optional[Dict[str, Any]]
    ga4_data: Optional[Dict[str, Any]]
    ga4_error: Optional[str]
    
    # SEO Agent Results
    seo_data: Optional[Dict[str, Any]]
    seo_error: Optional[str]
    
    # Final Output
    answer: str
    structured_data: Optional[Dict[str, Any]]
    metadata: Dict[str, Any]


class GraphStateModel(BaseModel):
    """Pydantic model version of GraphState for validation."""
    
    # Input
    query: str
    property_id: Optional[str] = None
    
    # Routing
    query_type: QueryType = QueryType.UNKNOWN
    
    # GA4 Agent Results
    ga4_plan: Optional[Dict[str, Any]] = None
    ga4_data: Optional[Dict[str, Any]] = None
    ga4_error: Optional[str] = None
    
    # SEO Agent Results
    seo_data: Optional[Dict[str, Any]] = None
    seo_error: Optional[str] = None
    
    # Final Output
    answer: str = ""
    structured_data: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        arbitrary_types_allowed = True

