"""
GA4 Analytics Agent for processing Google Analytics 4 queries.
Handles natural language to GA4 Data API conversion.
"""

from typing import Dict, Any, Optional, List
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest,
    DateRange,
    Dimension,
    Metric,
    FilterExpression,
    Filter,
)
from datetime import datetime, timedelta
from langchain_core.output_parsers import JsonOutputParser
import logging

logger = logging.getLogger(__name__)


class GA4Agent:
    """Agent for handling GA4 analytics queries."""
    
    # Allowlist of valid GA4 metrics and dimensions
    VALID_METRICS = {
        "activeUsers", "newUsers", "totalUsers", "sessions",
        "sessionsPerUser", "screenPageViews", "screenPageViewsPerSession",
        "averageSessionDuration", "bounceRate", "engagementRate",
        "eventCount", "conversions", "totalRevenue", "userEngagementDuration"
    }
    
    # Metrics that are deprecated or may not have data
    DEPRECATED_METRICS = {
        "bounceRate": "This metric is deprecated in GA4. Use 'engagementRate' instead (inverse of bounce rate).",
        "averageSessionDuration": "This metric may not have data in GA4. Use 'userEngagementDuration' instead."
    }
    
    VALID_DIMENSIONS = {
        "date", "city", "country", "deviceCategory", "operatingSystem",
        "browser", "pagePath", "pageTitle", "landingPage", "eventName",
        "campaignName", "source", "medium", "channelGroup"
    }
    
    def __init__(self):
        """Initialize the GA4 agent with API client."""
        try:
            self.client = BetaAnalyticsDataClient()
            logger.info("GA4 Analytics client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize GA4 client: {e}")
            raise
    
    def parse_query_to_plan(self, query: str, llm_client) -> Dict[str, Any]:
        """
        Convert natural language query to a GA4 report plan using LLM.
        
        Args:
            query: Natural language query
            llm_client: LLM client for parsing
            
        Returns:
            Dict with metrics, dimensions, date_range, and optional filters
        """
        system_prompt = f"""You are a GA4 query planner. Convert natural language queries to structured GA4 report plans.

CRITICAL - ONLY Use These VERIFIED Metrics:
{', '.join(sorted(self.VALID_METRICS))}

Valid Dimensions: {', '.join(sorted(self.VALID_DIMENSIONS))}

CRITICAL - AUTOMATIC METRIC SUBSTITUTION:
ONLY add "metric_substitutions" when replacing DEPRECATED/OLD metric names with new ones:
- "bounce rate" or "bounceRate" → use "engagementRate" + ADD substitution note
- "session duration" or "average session duration" or "averageSessionDuration" → use "userEngagementDuration" + ADD substitution note
- "pageviews" → use "screenPageViews" + ADD substitution note

DO NOT add substitutions for metrics that are already correct:
- "engagement rate" or "engagementRate" → use "engagementRate" (NO substitution note)
- "user engagement duration" or "userEngagementDuration" → use "userEngagementDuration" (NO substitution note)
- "screen page views" or "screenPageViews" → use "screenPageViews" (NO substitution note)

Example WITH substitution (deprecated metric):
{{
  "metrics": ["engagementRate"],
  "dimensions": ["pagePath"],
  "date_range": {{"start": "2017-01-01", "end": "today"}},
  "metric_substitutions": {{
    "bounce rate": "engagementRate (replaces deprecated bounceRate)"
  }}
}}

Example WITHOUT substitution (already correct metric):
{{
  "metrics": ["engagementRate"],
  "dimensions": ["pagePath"],
  "date_range": {{"start": "2017-01-01", "end": "today"}}
}}

If a requested metric truly doesn't exist and has NO alternative:
Return: {{"error": "The requested metric is not available in GA4. Available metrics include: screenPageViews, sessions, totalUsers, engagementRate, userEngagementDuration."}}

Output ONLY valid JSON with this structure:
{{
  "metrics": ["metric1", "metric2"],
  "dimensions": ["dimension1"],
  "date_range": {{"start": "2017-01-01", "end": "today"}},
  "filters": [{{"dimension": "pagePath", "operator": "equals", "value": "/pricing"}}]
}}

IMPORTANT: 
- When query specifies a time period → use that time period
- When query does NOT specify a time period → ALWAYS use {{"start": "2017-01-01", "end": "today"}}
- NEVER assume a metric exists if it's not in the valid list

CRITICAL: Date range format rules (NO SPACES):
- Format: NdaysAgo (example: 7daysAgo, 14daysAgo, 30daysAgo) - NO SPACES!
- Valid values: NdaysAgo, yesterday, today, or YYYY-MM-DD
Examples:
- "last 7 days" → {{"start": "7daysAgo", "end": "today"}}
- "last 14 days" → {{"start": "14daysAgo", "end": "today"}}
- "last 30 days" → {{"start": "30daysAgo", "end": "today"}}
- "last week" → {{"start": "7daysAgo", "end": "today"}}
- "last month" → {{"start": "30daysAgo", "end": "today"}}
- "today" → {{"start": "today", "end": "today"}}
- "yesterday" → {{"start": "yesterday", "end": "today"}}
- "top 5 pages" (NO time period) → {{"start": "2017-01-01", "end": "today"}}
- "most popular pages" (NO time period) → {{"start": "2017-01-01", "end": "today"}}
- "pages by views" (NO time period) → {{"start": "2017-01-01", "end": "today"}}

WRONG: "7 days ago", "14 days ago" (with spaces) ❌
RIGHT: "7daysAgo", "14daysAgo" (no spaces) ✅

IMPORTANT: When the query does NOT specify a time period (e.g., "top 5 pages", "pages with most views"),
use the wide date range {{"start": "2017-01-01", "end": "today"}} to capture all available data.

CRITICAL - Filters and Dimensions:
- If query mentions a SPECIFIC page (e.g., "/pricing", "/about", "homepage") → ADD a filter:
  {{"dimension": "pagePath", "operator": "equals", "value": "/pricing"}}
- If query wants "daily" data → ADD "date" dimension
- If query wants data for a specific page over time → ADD BOTH "date" dimension AND pagePath filter

Examples:
- "page views for /pricing" → dimensions: ["pagePath"], filters: [{{"dimension": "pagePath", "operator": "equals", "value": "/pricing"}}]
- "daily page views for /pricing over last 14 days" → dimensions: ["date", "pagePath"], filters: [{{"dimension": "pagePath", "operator": "equals", "value": "/pricing"}}], date_range: {{"start": "14daysAgo", "end": "today"}}
- "page views by page" → dimensions: ["pagePath"], no filters
- "top pages" → dimensions: ["pagePath"], no filters

Common mappings:
- "traffic" / "visitors" → totalUsers, sessions
- "pageviews" / "page views" → screenPageViews
- "pages" → use pagePath dimension
- "top pages" → add pagePath dimension, order by metric
- "daily breakdown" / "over last X days" → add date dimension
- "for [specific page]" → add filter for that pagePath
- "by device" → add deviceCategory dimension
- "by source" → add source or medium dimension
- "bounce rate" → engagementRate (NOT bounceRate)
- "session duration" → userEngagementDuration (NOT averageSessionDuration)
"""
        
        user_prompt = f"Convert this query to a GA4 report plan: {query}"
        
        try:
            # Call LLM to parse query
            response = llm_client.generate(
                system_prompt="You are a GA4 query expert. Replace DEPRECATED metrics (bounceRate, averageSessionDuration) with modern ones (engagementRate, userEngagementDuration). If the user already asks for modern metrics (engagementRate, userEngagementDuration), use them as-is without adding substitution notes.",
                user_prompt=f"{system_prompt}\n\n{user_prompt}",
                temperature=0.0
            )
            
            plan = self._parse_llm_response(response)
            
            # Check if LLM returned an error about unavailable metrics
            if "error" in plan:
                error_msg = plan["error"]
                logger.error(f"GA4 plan generation failed: {error_msg}")
                raise ValueError(error_msg)
            
            # Check if LLM did metric substitutions and log them
            if "metric_substitutions" in plan:
                substitutions = plan["metric_substitutions"]
                logger.info(f"Metric substitutions: {substitutions}")
                # Store substitutions in the plan for later reference
            
            # Validate that no deprecated metrics slipped through
            requested_metrics = plan.get("metrics", [])
            for metric in requested_metrics:
                if metric in self.DEPRECATED_METRICS:
                    logger.warning(f"Deprecated metric '{metric}' found in plan")
                    # This shouldn't happen if LLM follows instructions, but catch it anyway
                    raise ValueError(f"The requested metric is not available in GA4. Please try using alternative metrics like engagementRate or userEngagementDuration.")
            
            self._validate_plan(plan)
            
            logger.info(f"Generated GA4 plan: {plan}")
            return plan
            
        except ValueError as e:
            # ValueError already has a user-friendly message, pass it through
            logger.error(f"Failed to parse query: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to parse query: {e}")
            raise ValueError(f"Could not understand the query. Please try rephrasing or check if the requested metrics are available in GA4.")
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response using LangChain's JsonOutputParser."""
        json_parser = JsonOutputParser()
        try:
            return json_parser.parse(response)
        except Exception as e:
            raise ValueError(f"LLM returned invalid JSON: {e}")
    
    def _validate_plan(self, plan: Dict[str, Any]) -> None:
        """Validate that plan uses only allowed fields."""
        # Validate metrics
        metrics = plan.get("metrics", [])
        invalid_metrics = [m for m in metrics if m not in self.VALID_METRICS]
        if invalid_metrics:
            raise ValueError(f"Invalid metrics: {invalid_metrics}")
        
        # Validate dimensions
        dimensions = plan.get("dimensions", [])
        invalid_dims = [d for d in dimensions if d not in self.VALID_DIMENSIONS]
        if invalid_dims:
            raise ValueError(f"Invalid dimensions: {invalid_dims}")
        
        # Ensure we have at least one metric
        if not metrics:
            raise ValueError("Plan must include at least one metric")
    
    def execute_plan(
        self,
        property_id: str,
        plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a GA4 report plan against the API.
        
        Args:
            property_id: GA4 property ID
            plan: Report plan from parse_query_to_plan
            
        Returns:
            Structured data from GA4 API
        """
        try:
            # Build request
            request = self._build_request(property_id, plan)
            
            # Execute API call
            logger.info(f"Executing GA4 query: property={property_id}, metrics={plan.get('metrics')}, dimensions={plan.get('dimensions')}, date_range={plan.get('date_range')}")
            response = self.client.run_report(request)
            
            logger.info(f"GA4 API response: {len(response.rows) if response.rows else 0} rows returned")
            
            # Parse response
            data = self._parse_response(response, plan)
            
            # Handle empty data
            if not data.get("rows"):
                logger.warning("GA4 query returned no data")
                logger.warning(f"Query details: metrics={plan.get('metrics')}, dimensions={plan.get('dimensions')}, date_range={plan.get('date_range')}")
                data["message"] = "No data found for the specified query"
            
            logger.info(f"GA4 data parsed: {len(data.get('rows', []))} rows")
            if data["rows"]:
                logger.info(f"First row sample: {data['rows'][0]}")
            
            return data
            
        except Exception as e:
            logger.error(f"GA4 API error: {e}")
            raise RuntimeError(f"Failed to execute GA4 query: {str(e)}")
    
    def _build_request(
        self,
        property_id: str,
        plan: Dict[str, Any]
    ) -> RunReportRequest:
        """Build GA4 API request from plan."""
        # Date range - default to all historical data from 2017
        date_range_data = plan.get("date_range", {})
        date_range = DateRange(
            start_date=date_range_data.get("start", "2017-01-01"),
            end_date=date_range_data.get("end", "today")
        )
        
        # Metrics
        metrics = [Metric(name=m) for m in plan.get("metrics", [])]
        
        # Dimensions
        dimensions = [Dimension(name=d) for d in plan.get("dimensions", [])]
        
        # Build request
        request = RunReportRequest(
            property=f"properties/{property_id}",
            date_ranges=[date_range],
            metrics=metrics,
            dimensions=dimensions,
            limit=10  # Default limit
        )
        
        return request
    
    def _parse_response(
        self,
        response,
        plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse GA4 API response into structured format."""
        rows = []
        
        for row in response.rows:
            row_data = {}
            
            # Add dimensions
            for i, dim_value in enumerate(row.dimension_values):
                dim_name = plan["dimensions"][i] if i < len(plan["dimensions"]) else f"dimension_{i}"
                row_data[dim_name] = dim_value.value
            
            # Add metrics
            for i, metric_value in enumerate(row.metric_values):
                metric_name = plan["metrics"][i] if i < len(plan["metrics"]) else f"metric_{i}"
                row_data[metric_name] = metric_value.value
            
            rows.append(row_data)
        
        return {
            "rows": rows,
            "row_count": len(rows),
            "query_plan": plan
        }

