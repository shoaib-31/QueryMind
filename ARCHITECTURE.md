# Spike AI - Architecture Documentation

## System Overview

Natural language query system that routes user queries to GA4, SEO data, or both using LLM-powered orchestration with LangGraph.

## Complete System Flow

```mermaid
graph TB
    Client[Client Application]
    
    subgraph "FastAPI Server"
        API[API Routes<br/>POST /query]
        Router[Query Orchestrator<br/>LangGraph State Machine]
        
        subgraph "LLM Layer"
            Primary[LiteLLM Proxy<br/>gemini-2.5-flash]
            Fallback[Gemini SDK<br/>gemini-2.5-flash]
            Primary -.fallback.-> Fallback
        end
        
        subgraph "Agent Layer"
            GA4Agent[GA4 Agent<br/>Analytics Processing]
            SEOAgent[SEO Agent<br/>Technical SEO Analysis]
            FusionFlow[Fusion Flow<br/>Combined Processing]
        end
        
        Validator[Input Validator<br/>propertyId Check]
        Sanitizer[Data Sanitizer<br/>JSON Compliance]
    end
    
    subgraph "External Services"
        GA4API[Google Analytics 4<br/>Data API]
        SheetsAPI[Google Sheets API<br/>Screaming Frog Data]
    end
    
    Client -->|HTTP POST| API
    API --> Validator
    Validator -->|Valid| Router
    Validator -->|Invalid| Client
    
    Router -->|Intent Classification| Primary
    Primary --> Router
    
    Router -->|ga4_only| GA4Agent
    Router -->|seo_only| SEOAgent
    Router -->|fusion| FusionFlow
    
    GA4Agent -->|Query Planning| Primary
    GA4Agent -->|Data Fetch| GA4API
    GA4Agent -->|Answer Generation| Primary
    
    SEOAgent -->|Worksheet Selection| Primary
    SEOAgent -->|Data Fetch| SheetsAPI
    SEOAgent -->|Data Analysis| Primary
    SEOAgent -->|Answer Generation| Primary
    
    FusionFlow -->|GA4 Query| GA4Agent
    FusionFlow -->|URL Lookup| SEOAgent
    FusionFlow -->|Combine & Summarize| Primary
    
    GA4Agent --> Sanitizer
    SEOAgent --> Sanitizer
    FusionFlow --> Sanitizer
    
    Sanitizer -->|Response| API
    API -->|JSON Response| Client
    
    style Router fill:#4CAF50,stroke:#2E7D32,color:#fff
    style Primary fill:#2196F3,stroke:#1565C0,color:#fff
    style Fallback fill:#FFC107,stroke:#F57C00,color:#000
    style GA4Agent fill:#9C27B0,stroke:#6A1B9A,color:#fff
    style SEOAgent fill:#FF5722,stroke:#D84315,color:#fff
    style FusionFlow fill:#009688,stroke:#00695C,color:#fff
```

## Request Flow

1. **Client** sends POST request with `query` and optional `propertyId`
2. **Validator** checks if propertyId is required (GA4/Fusion queries need it)
3. **Orchestrator** uses LLM to classify intent (GA4_ONLY, SEO_ONLY, or FUSION)
4. **Agent** processes query: GA4 Agent for analytics, SEO Agent for technical data, Fusion for both
5. **Sanitizer** cleans data (handles NaN, numpy types) and formats response as text or JSON
6. **Client** receives QueryResponse with answer and structured data

## Components

### API Layer (`api/routes.py`)
HTTP request handling, input validation, response formatting, error handling (422, 500 status codes)

### Orchestrator (`orchestrator.py`)
LangGraph state machine for query routing, intent classification via LLM, propertyId validation, agent coordination

### GA4 Agent (`agents/ga4_agent.py`)
Converts natural language to GA4 API queries, handles deprecated metrics (bounceRate→engagementRate, averageSessionDuration→userEngagementDuration), generates answers

### SEO Agent (`agents/seo_agent.py`)
Connects to Google Sheets, LLM-powered worksheet selection, DataFrame operations (filter/group/aggregate), URL matching for fusion queries

### LLM Client (`llm_client.py`)
Primary LiteLLM proxy with Gemini fallback, 3 retries with 30-second delay on rate limits, 30-second timeout per request

### Utilities (`utils.py`)
`sanitize_for_json()` handles NaN, Infinity, numpy types for JSON compliance

## Data Models

**GraphState** (LangGraph):
```python
{"query": str, "property_id": Optional[str], "query_type": QueryType, "answer": Optional[str], "structured_data": Optional[Dict], "metadata": Dict, "ga4_data": Optional[Dict], "seo_data": Optional[Dict]}
```

**QueryResponse** (API):
```python
{"success": bool, "query_type": str, "answer": str|object, "answer_type": "text"|"json", "data": Optional[Dict], "metadata": Dict, "error": Optional[str]}
```

## Error Handling

- **422 Unprocessable Entity**: Missing propertyId for GA4/Fusion queries
- **500 Internal Server Error**: LLM quota exceeded, both primary and fallback LLMs failed
- **200 OK with error field**: GA4 API errors, Google Sheets errors, no data found

## Performance

- **Caching**: SEO Agent caches worksheet data per request
- **Rate Limiting**: 30-second retry delay on LLM 429 errors, up to 3 attempts before fallback
- **Timeouts**: 30 seconds for LLM, GA4 API, and Google Sheets API requests

---

**Version**: 0.1.0  
**Last Updated**: December 2025
