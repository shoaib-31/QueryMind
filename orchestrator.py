"""
LangGraph orchestrator for routing and coordinating GA4 and SEO agents.
Manages the state machine for query processing.
"""

from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
from models import GraphState, GraphStateModel, QueryType
from agents import GA4Agent, SEOAgent
from llm_client import LLMClient
from config import get_settings
import logging

logger = logging.getLogger(__name__)


class QueryOrchestrator:
    """Orchestrator using LangGraph for query routing and execution."""
    
    def __init__(self):
        """Initialize orchestrator with agents and build graph."""
        settings = get_settings()
        
        # Initialize clients and agents
        self.llm_client = LLMClient()
        self.ga4_agent = GA4Agent()
        self.seo_agent = SEOAgent(
            sheet_id=settings.screaming_frog_sheet_id,
            sheet_name=settings.screaming_frog_sheet_name or "Sheet1"  # Fallback only
        )
        
        # Build the LangGraph state machine
        self.graph = self._build_graph()
        
        logger.info("Query orchestrator initialized")
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine."""
        # Create graph
        workflow = StateGraph(GraphState)
        
        # Add nodes
        workflow.add_node("route_query", self._route_query)
        workflow.add_node("process_ga4", self._process_ga4)
        workflow.add_node("process_seo", self._process_seo)
        workflow.add_node("process_fusion", self._process_fusion)
        workflow.add_node("generate_response", self._generate_response)
        
        # Set entry point
        workflow.set_entry_point("route_query")
        
        # Add conditional edges from routing
        workflow.add_conditional_edges(
            "route_query",
            self._determine_path,
            {
                "ga4": "process_ga4",
                "seo": "process_seo",
                "fusion": "process_fusion",
            }
        )
        
        # All processing nodes lead to response generation
        workflow.add_edge("process_ga4", "generate_response")
        workflow.add_edge("process_seo", "generate_response")
        workflow.add_edge("process_fusion", "generate_response")
        
        # Response generation leads to end
        workflow.add_edge("generate_response", END)
        
        return workflow.compile()
    
    def _route_query(self, state: dict) -> dict:
        """Determine query type based on content and propertyId presence."""
        query = state["query"].lower()
        has_property_id = state.get("property_id") is not None
        
        # Use LLM to detect intent
        system_prompt = """You are a query router. Determine if a query is about:

**GA4** (Google Analytics) - ONLY pure traffic/user behavior queries:
- Traffic patterns: users, sessions, pageviews, bounce rate
- User engagement: session duration, pages per session
- Conversions and events
- Geographic data (city, country)
- Device/browser analytics
- Traffic sources (source, medium, campaign)
- Time-based trends (daily, weekly, monthly)

**SEO** (Technical SEO from Screaming Frog) - ONLY pure technical/structural queries:
- HTTP status codes (404, 301, 500, etc.)
- Page content (titles, descriptions, headings, word count)
- Content types (HTML, PDF, images, etc.)
- Indexability and crawlability
- HTTPS/security issues
- Broken links and redirects
- Alt text and images
- Canonical tags
- Schema markup
- Page structure and URLs
- Mobile usability
- Page speed issues
- Technical health
- SEO issues/problems

**FUSION** - Queries combining BOTH traffic AND technical data:
- "top pages" + "SEO issues/problems/health"
- "high traffic pages" + "broken/errors/technical"
- "popular pages" + "indexable/crawlable/healthy"
- Any query asking about BOTH performance metrics AND technical quality
- Examples:
  * "Top pages by traffic and their technical health"
  * "Are my best performing pages SEO-friendly?"
  * "Show popular pages with technical issues"

CRITICAL RULES:
1. If query asks for traffic metrics AND technical/SEO data → FUSION
2. Keywords like "healthy", "technical", "SEO issues" combined with traffic → FUSION
3. "pageviews" alone → GA4, but "pageviews" + "technical health" → FUSION
4. If unsure whether it needs both sources → Choose FUSION

Output ONLY one word: GA4, SEO, or FUSION"""
        
        try:
            intent = self.llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=f"Query: {state['query']}",
                temperature=0.0,
                max_tokens=500
            ).strip().upper()
            
            logger.info(f"Classified intent: {intent}")
            
            intent_upper = intent.upper().strip()
            
            if "FUSION" in intent_upper:
                query_type = QueryType.FUSION
            elif "SEO" in intent_upper:
                query_type = QueryType.SEO_ONLY
            elif "GA4" in intent_upper:
                query_type = QueryType.GA4_ONLY
            else:
                logger.warning(f"Unclear intent '{intent}', using fallback logic")
                if has_property_id:
                    query_type = QueryType.GA4_ONLY
                else:
                    query_type = QueryType.SEO_ONLY
            
            state["query_type"] = query_type
            state["metadata"]["routing"] = {
                "detected_intent": intent,
                "query_type": query_type.value,
                "has_property_id": has_property_id
            }
            
            logger.info(f"Routed to: {query_type.value}")
            
            if query_type in [QueryType.GA4_ONLY, QueryType.FUSION] and not has_property_id:
                logger.error(f"Validation failed: {query_type.value} requires propertyId")
                state["answer"] = (
                    "This query requires Google Analytics data. "
                    "Please provide a 'propertyId' in your request to proceed."
                )
                state["metadata"]["validation_error"] = "missing_property_id"
                state["metadata"]["validation_failed"] = True
                return state
            
            logger.debug(f"Validation passed for {query_type.value}")
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Routing failed: {e}")
            
            # Check if this is an LLM service failure (quota, timeout, etc.)
            is_llm_service_error = any(keyword in error_message.lower() for keyword in [
                "quota", "resource_exhausted", "429", "rate limit", 
                "timed out", "timeout", "both primary and fallback llm failed"
            ])
            
            if is_llm_service_error:
                state["query_type"] = QueryType.UNKNOWN
                state["answer"] = "LLM service is currently unavailable due to quota limits or timeout. Please try again later."
                state["metadata"]["llm_service_error"] = True
                state["metadata"]["error_details"] = error_message
                logger.error("LLM service error - aborting request")
            else:
                state["query_type"] = QueryType.UNKNOWN
                state["answer"] = f"Error: Could not determine query type: {error_message}"
        
        return state
    
    def _determine_path(self, state: dict) -> Literal["ga4", "seo", "fusion"]:
        """Return the next node based on query type."""
        if state.get("metadata", {}).get("llm_service_error"):
            logger.error("LLM service error - skipping processing")
            return "seo"
        
        if state.get("metadata", {}).get("validation_failed"):
            logger.debug("Validation failed - skipping processing")
            return "seo"
        
        query_type = state.get("query_type", QueryType.UNKNOWN)
        if query_type == QueryType.GA4_ONLY:
            return "ga4"
        elif query_type == QueryType.SEO_ONLY:
            return "seo"
        elif query_type == QueryType.FUSION:
            return "fusion"
        else:
            logger.warning(f"Unknown query type, defaulting to SEO")
            return "seo"
    
    def _process_ga4(self, state: dict) -> dict:
        """Process GA4-only queries."""
        if state.get("metadata", {}).get("llm_service_error"):
            return state
        
        try:
            logger.info("Processing GA4 query")
            
            # Parse query to plan
            plan = self.ga4_agent.parse_query_to_plan(state["query"], self.llm_client)
            state["ga4_plan"] = plan
            
            # Store metric substitutions if any
            if "metric_substitutions" in plan:
                state["metadata"]["metric_substitutions"] = plan["metric_substitutions"]
            
            # Execute plan
            data = self.ga4_agent.execute_plan(state["property_id"], plan)
            state["ga4_data"] = data
            
            state["metadata"]["ga4_execution"] = {
                "plan": plan,
                "row_count": data.get("row_count", 0)
            }
            
        except ValueError as e:
            # ValueError is raised for deprecated/unavailable metrics
            logger.error(f"GA4 query validation failed: {e}")
            state["ga4_error"] = str(e)
            state["answer"] = str(e)  # Show the helpful error message directly
        except Exception as e:
            logger.error(f"GA4 processing failed: {e}")
            state["ga4_error"] = str(e)
            state["answer"] = f"Error processing GA4 query: {str(e)}"
        
        return state
    
    def _process_seo(self, state: dict) -> dict:
        """Process SEO-only queries."""
        if state.get("metadata", {}).get("llm_service_error"):
            return state
        
        if state.get("answer") and state.get("metadata", {}).get("validation_error"):
            return state
        
        try:
            logger.info("Processing SEO query")
            
            # Query SEO data
            result = self.seo_agent.query_data(state["query"], self.llm_client)
            
            state["seo_data"] = result.get("data")
            # Clean up the SEO answer to remove escape characters
            raw_answer = result.get("answer", "")
            state["answer"] = self._clean_llm_response(raw_answer)
            
            # Set structured_data without large rows arrays to reduce response size
            data = result.get("data", {})
            structured_data = {
                "operation": data.get("operation"),
                "row_count": data.get("row_count", 0),
                "total_rows": result.get("total_rows", 0),
                "worksheets_queried": result.get("worksheets_queried", []),
                "columns_available": result.get("columns_available", [])
            }
            # Only include summary/sample data, not full rows array
            if "sample" in data:
                structured_data["sample"] = data["sample"][:5]  # Limit to 5 rows max
            if "results" in data:
                # For multiple operations, include summary without full rows
                structured_data["operations_count"] = data.get("operations_count", 0)
            
            state["structured_data"] = structured_data
            
            state["metadata"]["seo_execution"] = {
                "columns_available": result.get("columns_available", []),
                "total_rows": result.get("total_rows", 0)
            }
            
        except Exception as e:
            logger.error(f"SEO processing failed: {e}")
            state["seo_error"] = str(e)
            state["answer"] = f"Error processing SEO query: {str(e)}"
        
        return state
    
    def _process_fusion(self, state: dict) -> dict:
        """Process fusion queries requiring both GA4 and SEO data."""
        if state.get("metadata", {}).get("llm_service_error"):
            return state
        
        try:
            logger.info("Processing fusion query")
            
            # Step 1: Get top pages from GA4
            ga4_plan = {
                "metrics": ["screenPageViews", "totalUsers"],
                "dimensions": ["pagePath"],
                "date_range": {"start": "7daysAgo", "end": "today"}
            }
            
            ga4_data = self.ga4_agent.execute_plan(state["property_id"], ga4_plan)
            state["ga4_data"] = ga4_data
            
            # Extract URLs from GA4 rows
            # GA4 data format: {"rows": [{"pagePath": "/test.html", "screenPageViews": "83", ...}], ...}
            urls = []
            for row in ga4_data.get("rows", []):
                url = row.get("pagePath")
                if url:  # Skip None or empty URLs
                    urls.append(url)
            
            logger.info(f"Extracted {len(urls)} URLs from GA4 data")
            
            # Step 2: Look up those URLs in SEO data
            seo_matches = self.seo_agent.lookup_urls(urls)
            state["seo_data"] = {"matches": seo_matches.to_dict('records')}
            
            # Step 3: Merge and analyze
            # Create structured_data without rows array to reduce response size
            state["structured_data"] = {
                "ga4_summary": {
                    "row_count": ga4_data.get("row_count", 0),
                    "metrics": ga4_data.get("query_plan", {}).get("metrics", []),
                    "dimensions": ga4_data.get("query_plan", {}).get("dimensions", []),
                    "date_range": ga4_data.get("query_plan", {}).get("date_range", {})
                },
                "seo_summary": {
                    "matches_found": len(seo_matches)
                }
            }
            
            state["metadata"]["fusion_execution"] = {
                "ga4_rows": len(ga4_data.get("rows", [])),
                "seo_matches": len(seo_matches),
                "urls_checked": len(urls)
            }
            
        except Exception as e:
            logger.error(f"Fusion processing failed: {e}")
            state["answer"] = f"Error processing fusion query: {str(e)}"
        
        return state
    
    def _generate_response(self, state: dict) -> dict:
        """Generate final natural language response."""
        # If answer already set (e.g., from SEO agent or error), return as-is
        if state.get("answer"):
            return state
        
        try:
            # Generate answer based on available data
            if state.get("ga4_data") and not state.get("seo_data"):
                # GA4-only response
                state["answer"] = self._generate_ga4_answer(state)
                # Set structured_data without rows array to reduce response size
                ga4_data = state.get("ga4_data", {})
                state["structured_data"] = {
                    "row_count": ga4_data.get("row_count", 0),
                    "metrics": ga4_data.get("query_plan", {}).get("metrics", []),
                    "dimensions": ga4_data.get("query_plan", {}).get("dimensions", []),
                    "date_range": ga4_data.get("query_plan", {}).get("date_range", {})
                }
            elif state.get("seo_data") and not state.get("ga4_data"):
                # SEO-only response (should already have answer and structured_data)
                pass
            elif state.get("ga4_data") and state.get("seo_data"):
                # Fusion response
                state["answer"] = self._generate_fusion_answer(state)
            else:
                state["answer"] = "No data available to answer the query."
            
        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            state["answer"] = f"Error generating response: {str(e)}"
        
        return state
    
    def _clean_llm_response(self, text: str) -> str:
        """Clean up unnecessary escape characters and formatting from LLM response."""
        if not text:
            return text
        
        # Check if it's valid JSON - if yes, return as-is
        try:
            import json
            json.loads(text)
            # It's valid JSON, return as-is
            return text
        except:
            # It's plain text - remove ALL formatting
            # Replace newlines with spaces
            text = text.replace('\n', ' ')
            text = text.replace('\r', ' ')
            text = text.replace('\t', ' ')
            
            # Remove markdown formatting
            text = text.replace('*', '')
            text = text.replace('_', '')
            text = text.replace('#', '')
            
            # Remove multiple spaces
            import re
            text = re.sub(r'\s+', ' ', text)
            
            return text.strip()
    
    def _generate_ga4_answer(self, state: dict) -> str:
        """Generate natural language answer for GA4 data."""
        data = state.get("ga4_data")
        
        if not data or not data.get("rows"):
            return "No data found for your GA4 query. The query was executed successfully but returned no results."
        
        # Use LLM to generate natural language answer
        user_query = state['query'].lower()
        wants_json = any(keyword in user_query for keyword in ['json', 'json format', 'as json', 'in json'])
        
        # Check if metric substitutions were made (deprecated metrics replaced)
        metric_subs = state.get("metadata", {}).get("metric_substitutions", {})
        substitution_note = ""
        if metric_subs:
            # Check if these are real substitutions (deprecated → modern) not just formatting
            deprecated_keywords = ["bounce", "bounceRate", "session duration", "averageSessionDuration", "pageviews"]
            has_real_substitution = any(
                any(keyword.lower() in old_metric.lower() for keyword in deprecated_keywords)
                for old_metric in metric_subs.keys()
            )
            
            if has_real_substitution:
                actual_metrics = ", ".join(data.get("metrics", []))
                substitution_note = f"\n\nCRITICAL INSTRUCTIONS:\n1. The requested metrics are NOT AVAILABLE in GA4\n2. Instead, the data shows these GA4 metrics: {actual_metrics}\n3. DO NOT pretend the old metrics exist\n4. DO NOT convert or translate the metric names\n5. BE HONEST: Tell the user their requested metrics are not available and show what IS available\n6. Example: 'The metrics you requested (bounce rate, session duration) are not available. Here is the available data: engagementRate = 1 (100% engagement), userEngagementDuration = 325 seconds.'"
        
        if wants_json:
            prompt = f"""Based on this GA4 data, answer the user's question in JSON format.

User's question: {state['query']}

Data: {data}{substitution_note}

CRITICAL RULES:
- Return ONLY pure JSON (no markdown, no code blocks, no backticks)
- Start directly with {{ or [
- Use clean, simple formatting
- Do NOT use escape characters like \\n or \\t
- Do NOT add any text before or after the JSON
- Format ALL dates as dd-mm-yyyy (e.g., 15-12-2024) regardless of input format"""
        else:
            prompt = f"""Based on this GA4 data, answer the user's question.

User's question: {state['query']}

Data: {data}{substitution_note}

CRITICAL RULES:
- Write in ONE continuous line of plain text (NO line breaks, NO newlines)
- Do NOT use any formatting: no bullet points, no asterisks, no markdown
- Do NOT use \\n or \\t or any escape characters
- Write as a single flowing sentence or paragraph
- Use commas to separate items instead of line breaks
- Be direct and clear (2-3 sentences max)
- Do NOT return JSON unless explicitly asked
- NEVER assume or invent data that is not in the provided data
- If data looks limited (e.g., only 1 row, or suspicious values), mention it
- Use the EXACT metric names from the data, do not translate or rename them
- Format ALL dates as dd-mm-yyyy (e.g., 15-12-2024) regardless of input format
- Example good format: "Found 3 pages with HTTP: example.com, example.com/about, example.com/blog"
- Example BAD format: "Found 3 pages:\\n* page1\\n* page2" (never do this)"""
        
        try:
            answer = self.llm_client.generate(
                system_prompt="You are a direct, honest data analyst. Report EXACTLY what is in the data. NEVER assume, invent, or translate metric names. If metrics are substituted, be clear about it. Use the EXACT metric names from the data.",
                user_prompt=prompt,
                temperature=0.2
            )
            return self._clean_llm_response(answer.strip())
        except Exception as e:
            logger.error(f"Failed to generate GA4 answer: {e}")
            return f"Query returned {len(data.get('rows', []))} results."
    
    def _generate_fusion_answer(self, state: dict) -> str:
        """Generate natural language answer for fusion queries."""
        user_query = state['query'].lower()
        wants_json = any(keyword in user_query for keyword in ['json', 'json format', 'as json', 'in json'])
        
        if wants_json:
            prompt = f"""Based on this combined GA4 and SEO data, answer the user's question in JSON format.

User's question: {state['query']}

GA4 Data: {state.get('ga4_data')}
SEO Data: {state.get('seo_data')}

CRITICAL RULES:
- Return ONLY pure JSON (no markdown, no code blocks, no backticks)
- Start directly with {{ or [
- Combine insights from both GA4 and SEO data
- Use clean, simple formatting
- Do NOT use escape characters like \\n or \\t
- Do NOT add any text before or after the JSON
- Format ALL dates as dd-mm-yyyy (e.g., 15-12-2024) regardless of input format"""
        else:
            prompt = f"""Based on this combined GA4 and SEO data, answer the user's question.

User's question: {state['query']}

GA4 Data: {state.get('ga4_data')}
SEO Data: {state.get('seo_data')}

CRITICAL RULES:
- Write in ONE continuous line of plain text (NO line breaks, NO newlines)
- Do NOT use any formatting: no bullet points, no asterisks, no markdown
- Do NOT use \\n or \\t or any escape characters
- Write as a single flowing sentence or paragraph
- Use commas to separate items instead of line breaks
- Combine insights from both GA4 and SEO data
- Be direct and clear (3-4 sentences max)
- Do NOT return JSON unless explicitly asked
- Format ALL dates as dd-mm-yyyy (e.g., 15-12-2024) regardless of input format
- Example good format: "Top 5 pages by views: page1 (1000 views), page2 (800 views), page3 (600 views)"
- Example BAD format: "Top pages:\\n1. page1\\n2. page2" (never do this)"""
        
        try:
            answer = self.llm_client.generate(
                system_prompt="You are a direct, honest data analyst. Report EXACTLY what is in the data. NEVER assume, invent, or translate metric names. If metrics are substituted, be clear about it. Use the EXACT metric names from the data.",
                user_prompt=prompt,
                temperature=0.2
            )
            return self._clean_llm_response(answer.strip())
        except Exception as e:
            logger.error(f"Failed to generate fusion answer: {e}")
            return "Combined analysis complete. See structured data for details."
    
    async def process_query(
        self,
        query: str,
        property_id: str = None
    ) -> GraphStateModel:
        """
        Process a query through the orchestrator.
        
        Args:
            query: Natural language query
            property_id: Optional GA4 property ID
            
        Returns:
            Final graph state with answer
        """
        # Initialize state as dict (LangGraph expects dict with TypedDict)
        initial_state_dict: GraphState = {
            "query": query,
            "property_id": property_id,
            "query_type": QueryType.UNKNOWN,
            "ga4_plan": None,
            "ga4_data": None,
            "ga4_error": None,
            "seo_data": None,
            "seo_error": None,
            "answer": "",
            "structured_data": None,
            "metadata": {}
        }
        
        # Run through graph
        try:
            final_state_dict = self.graph.invoke(initial_state_dict)
            # Convert result dict to Pydantic model for type safety
            final_state = GraphStateModel(**final_state_dict)
            return final_state
        except Exception as e:
            logger.error(f"Graph execution failed: {e}", exc_info=True)
            # Return error state
            error_state = GraphStateModel(**initial_state_dict)
            error_state.answer = f"Error: {str(e)}"
            return error_state

