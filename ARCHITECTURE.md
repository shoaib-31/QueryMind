# Spike AI - Architecture Documentation

## System Overview

Spike AI is a natural language query system that intelligently routes user queries to appropriate data sources (Google Analytics 4, SEO data, or both) using LLM-powered orchestration with LangGraph.

## Architecture Diagram

### Complete System Flow

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

### Orchestrator State Machine (LangGraph)

```mermaid
stateDiagram-v2
    [*] --> RouteQuery: Receive Query
    
    RouteQuery --> IntentClassification: Use LLM
    IntentClassification --> DetermineType: Parse Intent
    
    DetermineType --> ValidatePropertyId: Check Requirements
    
    ValidatePropertyId --> ProcessGA4: GA4_ONLY + has propertyId
    ValidatePropertyId --> ProcessSEO: SEO_ONLY
    ValidatePropertyId --> ProcessFusion: FUSION + has propertyId
    ValidatePropertyId --> ValidationError: GA4/FUSION without propertyId
    ValidatePropertyId --> ServiceError: LLM Service Failed
    
    ProcessGA4 --> GenerateResponse: GA4 Data Retrieved
    ProcessSEO --> GenerateResponse: SEO Data Retrieved
    ProcessFusion --> GenerateResponse: Combined Data
    
    ValidationError --> [*]: Return 422 Error
    ServiceError --> [*]: Return 500 Error
    
    GenerateResponse --> [*]: Return Success Response
    
    note right of IntentClassification
        LLM analyzes query to determine:
        - GA4: Traffic/analytics queries
        - SEO: Technical SEO queries  
        - FUSION: Combined queries
    end note
    
    note right of ValidatePropertyId
        Validation Rules:
        - GA4_ONLY requires propertyId
        - FUSION requires propertyId
        - SEO_ONLY does not require propertyId
    end note
```

### Intent Classification Flow

```mermaid
flowchart TD
    Start([User Query]) --> LLM[LLM Intent Classifier]
    
    LLM --> Analyze{Analyze Query Content}
    
    Analyze -->|Contains traffic metrics<br/>users, sessions, pageviews| GA4Check{Mentions<br/>Technical SEO?}
    Analyze -->|Contains SEO terms<br/>status codes, meta tags| SEOCheck{Mentions<br/>Traffic/Analytics?}
    Analyze -->|Contains both<br/>traffic + technical| Fusion[FUSION Type]
    
    GA4Check -->|No| GA4[GA4_ONLY Type]
    GA4Check -->|Yes| Fusion
    
    SEOCheck -->|No| SEO[SEO_ONLY Type]
    SEOCheck -->|Yes| Fusion
    
    GA4 --> Validate{Has<br/>propertyId?}
    SEO --> Process[Process SEO Query]
    Fusion --> Validate
    
    Validate -->|Yes| ProcessGA4[Process GA4/Fusion Query]
    Validate -->|No| Error[Return 422:<br/>propertyId Required]
    
    ProcessGA4 --> End([Return Response])
    Process --> End
    Error --> End
    
    style GA4 fill:#9C27B0,color:#fff
    style SEO fill:#FF5722,color:#fff
    style Fusion fill:#009688,color:#fff
    style Error fill:#f44336,color:#fff
```

### GA4 Agent Workflow

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant G as GA4 Agent
    participant L as LLM Client
    participant API as GA4 API
    
    O->>G: Process GA4 Query
    
    G->>L: Parse Query to Plan
    Note over L: Convert NL to structured plan:<br/>metrics, dimensions, date_range
    L-->>G: Return Plan (JSON)
    
    G->>G: Validate Metrics
    Note over G: Check for deprecated metrics<br/>Auto-substitute if needed
    
    alt Has Deprecated Metrics
        G->>G: Substitute Metrics
        Note over G: bounceRate → engagementRate<br/>averageSessionDuration → userEngagementDuration
    end
    
    G->>API: Execute GA4 Query
    API-->>G: Return Data
    
    alt Empty Data
        G->>G: Log Warning
        Note over G: No data returned
    end
    
    G->>L: Generate Answer
    Note over L: Summarize data in natural language<br/>or return as JSON
    L-->>G: Return Answer
    
    G-->>O: Return Result + Data
```

### SEO Agent Workflow

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant S as SEO Agent
    participant L as LLM Client
    participant API as Sheets API
    
    O->>S: Process SEO Query
    
    S->>S: Get Available Worksheets
    Note over S: List all sheets:<br/>internal_all, response_codes_all, etc.
    
    S->>S: Get Worksheet Columns
    Note over S: Fetch column names from each sheet
    
    S->>L: Select Relevant Worksheets
    Note over L: Based on query, choose which<br/>worksheets contain relevant data
    L-->>S: Return Selected Worksheets
    
    loop For Each Selected Worksheet
        S->>API: Fetch Worksheet Data
        API-->>S: Return DataFrame
        S->>S: Cache Data
    end
    
    S->>L: Parse Query Intent
    Note over L: Determine operations:<br/>filter, group, aggregate, describe
    L-->>S: Return Analysis Plan
    
    S->>S: Execute Analysis
    Note over S: Apply filters, groupings,<br/>aggregations on DataFrame
    
    S->>L: Generate Summary
    Note over L: Convert results to<br/>natural language answer
    L-->>S: Return Answer
    
    S-->>O: Return Result + Data
```

### Fusion Query Workflow

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant F as Fusion Flow
    participant G as GA4 Agent
    participant S as SEO Agent
    participant L as LLM Client
    
    O->>F: Process Fusion Query
    
    par Fetch GA4 Data
        F->>G: Query GA4 for Traffic Data
        Note over G: Get pageviews, users<br/>by pagePath
        G-->>F: Return GA4 Data + URLs
    and Select SEO Worksheet
        F->>S: Determine SEO Worksheet
        S-->>F: Return Worksheet Name
    end
    
    F->>F: Extract URLs from GA4 Data
    Note over F: Get pagePath from<br/>GA4 dimension data
    
    F->>S: Lookup URLs in SEO Data
    Note over S: Match URLs using:<br/>1. Exact match<br/>2. Path-based match
    S-->>F: Return Matching SEO Data
    
    alt No Matches Found
        F->>F: Log Warning
        Note over F: URL formats may not match
    end
    
    F->>F: Combine Data
    Note over F: Merge GA4 metrics with<br/>SEO technical data by URL
    
    F->>L: Generate Fusion Answer
    Note over L: Analyze combined data:<br/>traffic + technical health
    L-->>F: Return Comprehensive Answer
    
    F-->>O: Return Result + Combined Data
```

### LLM Client with Fallback

```mermaid
flowchart TD
    Start([LLM Request]) --> Primary[Try Primary: LiteLLM]
    
    Primary --> Check1{Success?}
    Check1 -->|Yes| Return1[Return Response]
    Check1 -->|No| Error1{Rate Limit<br/>429?}
    
    Error1 -->|Yes| Retry1{Attempt < 3?}
    Retry1 -->|Yes| Wait1[Wait 30 seconds]
    Wait1 --> Primary
    Retry1 -->|No| Fallback[Try Fallback: Gemini SDK]
    
    Error1 -->|No, Other Error| Fallback
    
    Fallback --> Check2{Success?}
    Check2 -->|Yes| Return2[Return Response]
    Check2 -->|No| Error2{Rate Limit<br/>429?}
    
    Error2 -->|Yes| Retry2{Attempt < 2?}
    Retry2 -->|Yes| Wait2[Wait 30 seconds]
    Wait2 --> Fallback
    Retry2 -->|No| Failed
    
    Error2 -->|No, Other Error| Failed[Both LLMs Failed]
    
    Failed --> ErrorState[Set llm_service_error Flag]
    ErrorState --> Return3[Return 500 Error]
    
    Return1 --> End([Success])
    Return2 --> End
    Return3 --> End
    
    style Primary fill:#2196F3,color:#fff
    style Fallback fill:#FFC107,color:#000
    style Failed fill:#f44336,color:#fff
```

### Data Flow

```mermaid
graph LR
    subgraph "Input Processing"
        A[Raw Query] --> B[Pydantic Validation]
        B --> C[GraphState Dict]
    end
    
    subgraph "Query Execution"
        C --> D[LangGraph Execution]
        D --> E[Agent Processing]
        E --> F[External API Calls]
    end
    
    subgraph "Output Processing"
        F --> G[Raw Data]
        G --> H[Data Sanitization]
        H --> I{Answer Type?}
        I -->|JSON| J[JsonOutputParser]
        I -->|Text| K[Text Cleaning]
        J --> L[Final Response]
        K --> L
    end
    
    L --> M[GraphStateModel]
    M --> N[QueryResponse]
    N --> O[HTTP Response]
    
    style D fill:#4CAF50,color:#fff
    style H fill:#FF9800,color:#fff
    style N fill:#2196F3,color:#fff
```

## Component Details

### 1. API Layer (`api/routes.py`)

**Responsibilities**:
- HTTP request handling
- Input validation
- Response formatting
- Error handling (422, 500 status codes)
- JSON parsing and sanitization

**Key Functions**:
- `POST /query`: Main query endpoint
- `GET /health`: Health check
- `GET /`: Root health check

### 2. Orchestrator (`orchestrator.py`)

**Responsibilities**:
- Query routing via LangGraph state machine
- Intent classification using LLM
- Property ID validation
- Agent coordination
- Response generation

**State Machine Nodes**:
- `route_query`: Classify query intent
- `process_ga4`: Handle GA4 queries
- `process_seo`: Handle SEO queries
- `process_fusion`: Handle combined queries
- `generate_response`: Create final answer

**Routing Logic**:
```python
GA4 Keywords: users, sessions, pageviews, traffic, conversions
SEO Keywords: status codes, meta tags, indexability, broken links
FUSION: Combination of both traffic and technical terms
```

### 3. GA4 Agent (`agents/ga4_agent.py`)

**Responsibilities**:
- Convert natural language to GA4 API queries
- Execute GA4 Data API requests
- Handle deprecated metrics
- Generate natural language answers

**Key Features**:
- Automatic metric substitution (bounceRate → engagementRate)
- Date range parsing (7daysAgo, today, etc.)
- Dimension and metric validation
- Error handling for API limits

**Supported Metrics**:
- Traffic: totalUsers, sessions, screenPageViews
- Engagement: engagementRate, userEngagementDuration
- Events: eventCount, conversions

**Supported Dimensions**:
- Time: date, year, month, day
- Content: pagePath, pageTitle
- User: country, city, deviceCategory, browser
- Traffic: source, medium, campaignName

### 4. SEO Agent (`agents/seo_agent.py`)

**Responsibilities**:
- Connect to Google Sheets with Screaming Frog data
- Intelligent worksheet selection
- Data filtering and analysis
- Generate SEO insights

**Key Features**:
- Auto-detects available worksheets
- LLM-powered worksheet selection
- DataFrame operations (filter, group, aggregate)
- URL matching for fusion queries

**Common Worksheets**:
- `internal_all`: Main crawl data
- `response_codes_all`: HTTP status
- `meta_description_all`: Meta tags
- `page_titles_all`: Title tags
- `canonicals_all`: Canonical URLs
- `images_all`: Image analysis

### 5. LLM Client (`llm_client.py`)

**Responsibilities**:
- Manage LLM API calls
- Implement retry logic with exponential backoff
- Handle fallback to Gemini
- Rate limit management

**Configuration**:
- Primary: LiteLLM proxy (customizable model)
- Fallback: Gemini native SDK
- Retry: 3 attempts with 30-second delay
- Timeout: 30 seconds per request

### 6. Utilities (`utils.py`)

**Functions**:
- `sanitize_for_json()`: Handle NaN, Infinity, numpy types for JSON compliance

## Data Models

### GraphState (LangGraph State)

```python
{
    "query": str,                    # User's natural language query
    "property_id": Optional[str],    # GA4 property ID
    "query_type": QueryType,         # GA4_ONLY | SEO_ONLY | FUSION
    "answer": Optional[str],         # Final answer
    "structured_data": Optional[Dict], # Raw data from agents
    "metadata": Dict,                # Routing info, timing, etc.
    "ga4_data": Optional[Dict],      # GA4 results
    "ga4_plan": Optional[Dict],      # GA4 query plan
    "ga4_error": Optional[str],      # GA4 error message
    "seo_data": Optional[Dict],      # SEO results
    "seo_error": Optional[str],      # SEO error message
}
```

### QueryResponse (API Response)

```python
{
    "success": bool,
    "query_type": str,
    "answer": str | object,          # Can be text or parsed JSON
    "answer_type": "text" | "json",
    "data": Optional[Dict],
    "metadata": Dict,
    "error": Optional[str]
}
```

## Error Handling

### Error Types

1. **Validation Errors (422)**:
   - Missing `propertyId` for GA4/Fusion queries
   - Invalid request format

2. **Service Errors (500)**:
   - LLM quota exceeded
   - LLM timeout
   - Both primary and fallback LLM failed

3. **Data Errors (200 with error field)**:
   - GA4 API errors
   - Google Sheets connection errors
   - No data found for query

### Error Flow

```mermaid
flowchart TD
    Request[Incoming Request] --> Validate{Validation}
    
    Validate -->|Pass| Route[Route Query]
    Validate -->|Fail| E422[422 Response<br/>Validation Error]
    
    Route -->|Success| Process[Process Query]
    Route -->|LLM Failed| E500[500 Response<br/>Service Error]
    
    Process -->|Success| Response[200 Response<br/>With Data]
    Process -->|Partial Fail| Response200[200 Response<br/>With Error Field]
    
    E422 --> End([Return to Client])
    E500 --> End
    Response --> End
    Response200 --> End
    
    style E422 fill:#FFC107,color:#000
    style E500 fill:#f44336,color:#fff
    style Response fill:#4CAF50,color:#fff
```

## Performance Considerations

### Caching

- SEO Agent caches worksheet data per request
- Multiple queries to same worksheet reuse cached DataFrame

### Rate Limiting

- GA4 API: Respects Google's rate limits
- LLM: 30-second retry delay on 429 errors
- Up to 3 retry attempts before fallback

### Timeouts

- LLM requests: 30 seconds
- GA4 API: 30 seconds
- Google Sheets API: 30 seconds

## Security

### API Keys

- All API keys stored in `.env` (not committed)
- Service account credentials in `credentials.json` (gitignored)

### Data Access

- Google Service Account with minimal permissions
- Read-only access to GA4 properties
- Read-only access to Google Sheets

### Input Validation

- Pydantic models validate all inputs
- SQL injection not applicable (no SQL databases)
- API key injection prevented by environment isolation

## Deployment

### Production Considerations

1. **Environment Variables**: Use secure secret management
2. **CORS**: Configure `allow_origins` appropriately
3. **Logging**: Adjust `LOG_LEVEL` to INFO or WARNING in production
4. **Monitoring**: Track LLM usage, API quotas, error rates
5. **Scaling**: Consider load balancing for high traffic

### Docker Deployment (Optional)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python3", "main.py"]
```

## Monitoring & Observability

### Logging Levels

- **DEBUG**: Detailed data samples, intermediate steps
- **INFO**: Key milestones, routing decisions
- **WARNING**: Recoverable issues, fallbacks
- **ERROR**: Failures requiring attention

### Key Metrics

- Query processing time
- LLM response time
- Agent execution time
- Error rates by type
- LLM fallback frequency

---

**Version**: 0.1.0  
**Last Updated**: December 2025

