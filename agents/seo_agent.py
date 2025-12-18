"""
SEO Agent for processing Screaming Frog data from Google Sheets.
Handles SEO-related queries about indexability, technical issues, etc.
"""

from typing import Dict, Any, Optional, List
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from langchain_core.output_parsers import JsonOutputParser
import logging

logger = logging.getLogger(__name__)


class SEOAgent:
    """Agent for handling SEO queries from Screaming Frog data."""
    
    def __init__(self, sheet_id: str, sheet_name: str = "Sheet1"):
        """
        Initialize the SEO agent with Google Sheets connection.
        
        Args:
            sheet_id: Google Sheets ID
            sheet_name: Default sheet name (used only as fallback)
        """
        self.sheet_id = sheet_id
        self.sheet_name = sheet_name  # Fallback only
        self.spreadsheet = None
        self.available_worksheets: List[str] = []
        self.cached_sheets: Dict[str, pd.DataFrame] = {}  # Cache multiple sheets
        self._connect()
    
    def _connect(self):
        """Establish connection to Google Sheets and discover available worksheets."""
        try:
            # Use default credentials (from GOOGLE_APPLICATION_CREDENTIALS)
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets.readonly',
                'https://www.googleapis.com/auth/drive.readonly'
            ]
            
            creds = Credentials.from_service_account_file(
                'credentials.json',
                scopes=scopes
            )
            
            self.client = gspread.authorize(creds)
            
            # Open spreadsheet and discover worksheets
            self.spreadsheet = self.client.open_by_key(self.sheet_id)
            self.available_worksheets = [ws.title for ws in self.spreadsheet.worksheets()]
            
            logger.info(f"SEO Agent connected successfully to '{self.spreadsheet.title}'")
            logger.info(f"Discovered {len(self.available_worksheets)} worksheets: {self.available_worksheets[:5]}...")
            
        except Exception as e:
            logger.error(f"Failed to connect to Google Sheets: {e}")
            raise RuntimeError(f"Could not initialize SEO Agent: {str(e)}")
    
    def select_worksheets(self, query: str, llm_client) -> List[str]:
        """
        Use LLM to intelligently select which worksheet(s) to query based on user query.
        Provides column information for better decision making.
        
        Args:
            query: User's natural language query
            llm_client: LLM client for decision making
            
        Returns:
            List of worksheet names to query
        """
        # Get column information for each worksheet (use cached data when available)
        worksheet_info = self._get_worksheet_columns_info()
        
        # Build detailed worksheet descriptions
        worksheet_descriptions = []
        for ws_name, columns in worksheet_info.items():
            col_sample = ', '.join(columns[:8]) + ('...' if len(columns) > 8 else '')
            worksheet_descriptions.append(f"- '{ws_name}': {len(columns)} columns ({col_sample})")
        
        system_prompt = f"""You are an SEO data analyst. Given a user's query, determine which worksheet(s) from a Screaming Frog crawl export contain the relevant data.

Available worksheets with their columns:
{chr(10).join(worksheet_descriptions)}

Worksheet naming patterns and typical columns:
- 'internal_all' - Main crawl data (columns: address, content_type, status_code, title, word_count, etc.)
- 'external_all' - External links (columns: source, destination, alt_text, etc.)
- 'images_all' - Image data (columns: address, alt_text, size, missing_alt_text, etc.)
- 'response_codes_all' - HTTP status codes (columns: address, status_code, status, etc.)
- 'canonicals_all' - Canonical tags (columns: address, canonical_link, etc.)
- 'meta_description_all' - Meta descriptions (columns: address, meta_description, length, etc.)
- 'page_titles_all' - Page titles (columns: address, title, length, etc.)
- 'h1_all', 'h2_all' - Headings (columns: address, h1, h1_length, etc.)
- 'content_all' - Content analysis (columns: address, content_type, word_count, text_ratio, etc.)
- 'links_all' - All links (columns: source, destination, anchor_text, type, etc.)
- 'mobile_all' - Mobile usability
- 'pagespeed_all' - Page speed metrics
- 'security_all' - HTTPS and security
- 'structured_data_all' - Schema markup
- 'search_console_all' - GSC integration data
- 'accessibility_all' - Accessibility issues
- 'directives_all' - Robots directives
- 'sitemaps_all' - Sitemap data
- 'url_all' - URL structure
- 'hreflang_all' - International targeting
- 'pagination_all' - Pagination data
- 'javascript_all' - JS-related issues
- 'link_metrics_all' - Link metrics
- 'validation_all' - HTML validation

IMPORTANT: Look at the actual columns provided above to make your decision!

Output ONLY a JSON array of worksheet names (1-3 worksheets max):
["worksheet_name_1", "worksheet_name_2"]

Choose the MOST relevant worksheet(s). Usually 1 is enough, use 2-3 only if the query needs data from multiple sources."""

        user_prompt = f"User query: {query}\n\nWhich worksheet(s) should I query?"
        
        try:
            response = llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.0
            )
            
            # Parse response using LangChain's JsonOutputParser
            json_parser = JsonOutputParser()
            selected_worksheets = json_parser.parse(response)
            
            # Validate selections
            valid_worksheets = [ws for ws in selected_worksheets if ws in self.available_worksheets]
            
            if not valid_worksheets:
                logger.warning(f"LLM selected invalid worksheets: {selected_worksheets}. Using 'internal_all' as fallback.")
                valid_worksheets = ['internal_all'] if 'internal_all' in self.available_worksheets else [self.available_worksheets[0]]
            
            logger.info(f"Selected worksheet(s) for query: {valid_worksheets}")
            return valid_worksheets
            
        except Exception as e:
            logger.error(f"Failed to select worksheets, using fallback: {e}")
            # Fallback: use internal_all or first available
            fallback = 'internal_all' if 'internal_all' in self.available_worksheets else self.available_worksheets[0]
            logger.info(f"Using fallback worksheet: {fallback}")
            return [fallback]
    
    def _get_worksheet_columns_info(self) -> Dict[str, List[str]]:
        """
        Get column information for all worksheets.
        Uses cached data when available, otherwise fetches first few rows.
        
        Returns:
            Dictionary mapping worksheet names to their column lists
        """
        worksheet_columns = {}
        
        for ws_name in self.available_worksheets:
            try:
                # If already cached, use that
                if ws_name in self.cached_sheets:
                    worksheet_columns[ws_name] = list(self.cached_sheets[ws_name].columns)
                else:
                    # Fetch just the header row to get column names
                    worksheet = self.spreadsheet.worksheet(ws_name)
                    headers = worksheet.row_values(1)
                    # Normalize column names
                    normalized = [
                        col.lower().replace(' ', '_').replace('/', '_').replace('-', '_')
                        for col in headers
                    ]
                    worksheet_columns[ws_name] = normalized
            except Exception as e:
                logger.warning(f"Could not fetch columns for {ws_name}: {e}")
                worksheet_columns[ws_name] = []
        
        return worksheet_columns
    
    def fetch_data(self, worksheet_name: str, force_refresh: bool = False) -> pd.DataFrame:
        """
        Fetch data from a specific worksheet (cached after first load).
        
        Args:
            worksheet_name: Name of the worksheet to fetch
            force_refresh: Force re-fetch from Google Sheets
            
        Returns:
            DataFrame with data from the specified worksheet
        """
        # Check cache
        if worksheet_name in self.cached_sheets and not force_refresh:
            logger.info(f"Using cached data for worksheet '{worksheet_name}'")
            return self.cached_sheets[worksheet_name]
        
        try:
            logger.info(f"Fetching data from worksheet: '{worksheet_name}'")
            
            # Validate worksheet exists
            if worksheet_name not in self.available_worksheets:
                error_msg = (
                    f"Worksheet '{worksheet_name}' not found. "
                    f"Available: {', '.join(self.available_worksheets[:10])}..."
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            # Fetch the worksheet
            worksheet = self.spreadsheet.worksheet(worksheet_name)
            logger.info(f"Opened worksheet: '{worksheet_name}' ({worksheet.row_count} rows)")
            
            # Get all values
            data = worksheet.get_all_records()
            
            # Convert to DataFrame
            df = pd.DataFrame(data)
            
            if df.empty:
                logger.warning(f"Worksheet '{worksheet_name}' is empty or has no data rows")
                return pd.DataFrame()  # Return empty df instead of error
            
            # Normalize column names (lowercase, replace spaces with underscores)
            df.columns = [
                col.lower().replace(' ', '_').replace('/', '_').replace('-', '_')
                for col in df.columns
            ]
            
            # Cache the data
            self.cached_sheets[worksheet_name] = df
            
            logger.info(f"Fetched {len(df)} rows with {len(df.columns)} columns from '{worksheet_name}'")
            
            return df
            
        except gspread.exceptions.SpreadsheetNotFound:
            error_msg = f"Spreadsheet with ID '{self.sheet_id}' not found. Check SCREAMING_FROG_SHEET_ID in .env"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except RuntimeError:
            # Re-raise our custom runtime errors
            raise
        except Exception as e:
            logger.error(f"Failed to fetch data from '{worksheet_name}': {e}", exc_info=True)
            raise RuntimeError(f"Could not fetch data from '{worksheet_name}': {type(e).__name__}: {str(e)}")
    
    def query_data(
        self,
        query: str,
        llm_client
    ) -> Dict[str, Any]:
        """
        Process a natural language query about SEO data.
        Intelligently selects and queries the appropriate worksheet(s).
        
        Args:
            query: Natural language query
            llm_client: LLM client for understanding query intent
            
        Returns:
            Structured response with data and summary
        """
        try:
            # Step 1: Select relevant worksheet(s) based on query
            selected_worksheets = self.select_worksheets(query, llm_client)
            
            # Step 2: Fetch data from selected worksheet(s)
            all_data = {}
            combined_df = None
            
            for ws_name in selected_worksheets:
                df = self.fetch_data(ws_name, force_refresh=False)
                
                if not df.empty:
                    all_data[ws_name] = df
                    
                    # For single worksheet, use it directly
                    if combined_df is None:
                        combined_df = df.copy()
                        combined_df['_source_worksheet'] = ws_name
                    else:
                        # For multiple worksheets, combine them
                        df_copy = df.copy()
                        df_copy['_source_worksheet'] = ws_name
                        combined_df = pd.concat([combined_df, df_copy], ignore_index=True)
            
            if combined_df is None or combined_df.empty:
                return {
                    "answer": "No relevant SEO data found for your query.",
                    "data": None,
                    "worksheets_queried": selected_worksheets
                }
            
            # Step 3: Analyze the data
            logger.info(f"Analyzing {len(combined_df)} rows of data")
            logger.debug(f"Available columns: {list(combined_df.columns)[:10]}...")
            
            analysis_plan = self._parse_query_intent(query, combined_df, llm_client)
            logger.info(f"Analysis plan: {analysis_plan}")
            
            result = self._execute_analysis(combined_df, analysis_plan)
            logger.info(f"Analysis result type: {result.get('operation')}, rows: {result.get('row_count', 'N/A')}")
            logger.debug(f"Analysis result sample: {str(result)[:200]}...")
            
            # Step 4: Generate natural language summary
            summary = self._generate_summary(result, query, llm_client, selected_worksheets)
            logger.info(f"Generated summary: {summary[:100]}...")
            
            return {
                "answer": summary,
                "data": result,
                "worksheets_queried": selected_worksheets,
                "columns_available": list(combined_df.columns),
                "total_rows": len(combined_df)
            }
            
        except Exception as e:
            logger.error(f"Failed to process SEO query: {e}", exc_info=True)
            raise RuntimeError(f"SEO query failed: {str(e)}")
    
    def _parse_query_intent(
        self,
        query: str,
        df: pd.DataFrame,
        llm_client
    ) -> Dict[str, Any]:
        """Parse query intent and create analysis plan."""
        system_prompt = f"""You are an SEO data analyst. Given a query about SEO data, create an analysis plan.

Available columns in the data: {', '.join(df.columns)}

Sample data (first row): {df.head(1).to_dict('records')[0] if not df.empty else 'No data'}

Output ONLY valid JSON. You can return either:

1. Single operation:
{{
  "operation": "filter|group|aggregate|describe",
  "column": "column_name",
  "condition": {{"operator": "equals|contains|not_equals|greater_than|less_than", "value": "..."}},
  "group_by": "column_name",
  "aggregate": {{"function": "count|sum|mean", "column": "column_name"}}
}}

2. Multiple operations (for complex analyses):
[
  {{"operation": "aggregate", "column": "col1", "aggregate": {{"function": "count"}}}},
  {{"operation": "aggregate", "column": "col2", "aggregate": {{"function": "count"}}}}
]

IMPORTANT: Be specific about operations:
- To find non-200 status codes: operation=filter, column=status_code, condition={{"operator": "not_equals", "value": 200}}
- To count by status: operation=group, group_by=status_code
- To list specific pages: operation=filter with appropriate column (address, url, etc.)
- For summarizing multiple metrics: return a list of aggregate operations

Common patterns:
- "how many pages are not indexable?" → operation=filter, column=indexability, condition={{"operator": "equals", "value": "Non-Indexable"}}
- "show pages with https issues" → operation=filter, column=https (or similar)
- "what is the indexability status breakdown?" → operation=group, group_by=indexability
- "broken pages" or "non-200 status" → operation=filter, column=status_code, condition={{"operator": "not_equals", "value": 200}}
- "list all 404 pages" → operation=filter, column=status_code, condition={{"operator": "equals", "value": 404}}
"""
        
        user_prompt = f"Create analysis plan for: {query}"
        
        try:
            response = llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.0
            )
            
            plan = self._parse_llm_response(response)
            return plan
            
        except Exception as e:
            logger.warning(f"Could not parse query intent, using fallback: {e}")
            # Fallback: simple describe
            return {"operation": "describe"}
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response using LangChain's JsonOutputParser."""
        json_parser = JsonOutputParser()
        return json_parser.parse(response)
    
    def _execute_analysis(
        self,
        df: pd.DataFrame,
        plan: Any
    ) -> Dict[str, Any]:
        """
        Execute the analysis plan on the dataframe.
        Handles both single operations and lists of operations.
        """
        # Handle list of operations (multiple analyses)
        if isinstance(plan, list):
            logger.info(f"Executing {len(plan)} operations on {len(df)} rows")
            results = []
            for i, single_plan in enumerate(plan):
                logger.info(f"Operation {i+1}/{len(plan)}: {single_plan.get('operation', 'unknown')}")
                result = self._execute_single_analysis(df, single_plan)
                results.append(result)
            
            # Combine results
            return {
                "operation": "multiple",
                "operations_count": len(results),
                "results": results,
                "row_count": len(df)
            }
        else:
            # Single operation
            return self._execute_single_analysis(df, plan)
    
    def _execute_single_analysis(
        self,
        df: pd.DataFrame,
        plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single analysis operation."""
        operation = plan.get("operation", "describe")
        logger.info(f"Executing {operation} operation on {len(df)} rows")
        
        if operation == "filter":
            return self._filter_data(df, plan)
        elif operation == "group":
            return self._group_data(df, plan)
        elif operation == "aggregate":
            return self._aggregate_data(df, plan)
        else:
            return self._describe_data(df)
    
    def _filter_data(self, df: pd.DataFrame, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Filter data based on conditions."""
        condition = plan.get("condition", {})
        column = plan.get("column")
        
        logger.info(f"Filtering by column '{column}' with condition: {condition}")
        
        if not column or column not in df.columns:
            logger.warning(f"Column '{column}' not found in dataframe. Available: {list(df.columns)[:10]}")
            return {
                "operation": "filter",
                "error": f"Column '{column}' not found",
                "available_columns": list(df.columns),
                "row_count": 0,
                "rows": []
            }
        
        try:
            operator = condition.get("operator", "contains")
            value = condition.get("value", "")
            
            # Apply filter based on operator
            if operator == "equals":
                filtered_df = df[df[column] == value]
            elif operator == "not_equals":
                filtered_df = df[df[column] != value]
            elif operator == "contains":
                filtered_df = df[df[column].astype(str).str.contains(str(value), case=False, na=False)]
            elif operator == "greater_than":
                filtered_df = df[df[column] > value]
            elif operator == "less_than":
                filtered_df = df[df[column] < value]
            else:
                # Default to showing data where column has a value
                filtered_df = df[df[column].notna()]
            
            logger.info(f"Filter result: {len(filtered_df)} rows matched (from {len(df)} total)")
            
            # Convert to records, limit to 100 rows
            rows = filtered_df.head(100).to_dict('records')
            
            return {
                "operation": "filter",
                "column": column,
                "condition": condition,
                "row_count": len(filtered_df),
                "total_rows": len(df),
                "rows": rows,
                "sample": rows[:5] if rows else []
            }
            
        except Exception as e:
            logger.error(f"Filter operation failed: {e}")
            return {
                "operation": "filter",
                "error": str(e),
                "row_count": 0,
                "rows": []
            }
    
    def _group_data(self, df: pd.DataFrame, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Group and count data."""
        group_by = plan.get("group_by")
        
        logger.info(f"Grouping by column: {group_by}")
        
        if group_by and group_by in df.columns:
            grouped = df[group_by].value_counts().to_dict()
            total = len(df)
            
            logger.info(f"Grouped into {len(grouped)} categories, total rows: {total}")
            
            # Add percentages
            grouped_with_pct = {
                k: {"count": v, "percentage": round((v / total) * 100, 2)}
                for k, v in grouped.items()
            }
            
            return {
                "operation": "group",
                "group_by": group_by,
                "counts": grouped,
                "details": grouped_with_pct,
                "total_rows": total,
                "unique_values": len(grouped)
            }
        
        logger.warning(f"Invalid group_by column: {group_by}")
        return {
            "operation": "group",
            "error": f"Invalid group_by column: {group_by}",
            "available_columns": list(df.columns)
        }
    
    def _aggregate_data(self, df: pd.DataFrame, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Aggregate data with functions like count, sum, mean."""
        agg_config = plan.get("aggregate", {})
        function = agg_config.get("function", "count")
        column = plan.get("column") or agg_config.get("column")
        condition = plan.get("condition")
        
        logger.info(f"Aggregating column '{column}' with function: {function}")
        
        try:
            # Apply filter condition if provided
            working_df = df
            if condition:
                operator = condition.get("operator")
                value = condition.get("value")
                
                if operator == "not_equals" and column and column in df.columns:
                    # Filter out empty/null values or specific value
                    if value == "" or value is None:
                        working_df = df[df[column].notna() & (df[column] != "")]
                    else:
                        working_df = df[df[column] != value]
                    logger.info(f"Filtered to {len(working_df)} rows where {column} != {value}")
            
            # Perform aggregation
            if function == "count":
                if column and column in working_df.columns:
                    # Count non-empty values in the column
                    result = working_df[column].notna().sum()
                else:
                    result = len(working_df)
            elif function == "sum" and column and column in working_df.columns:
                result = working_df[column].sum()
            elif function == "mean" and column and column in working_df.columns:
                result = working_df[column].mean()
            else:
                result = len(working_df)
            
            logger.info(f"Aggregation result: {result}")
            
            return {
                "operation": "aggregate",
                "function": function,
                "column": column,
                "result": result,
                "row_count": len(df),
                "filtered_row_count": len(working_df)
            }
        except Exception as e:
            logger.error(f"Aggregation failed: {e}")
            return {
                "operation": "aggregate",
                "error": str(e),
                "column": column,
                "row_count": len(df)
            }
    
    def _describe_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Provide basic description of the data."""
        logger.info(f"Describing dataframe with {len(df)} rows and {len(df.columns)} columns")
        
        sample = df.head(10).to_dict('records')
        
        return {
            "operation": "describe",
            "total_rows": len(df),
            "columns": list(df.columns),
            "column_count": len(df.columns),
            "sample": sample,
            "sample_size": len(sample)
        }
    
    def _generate_summary(
        self,
        result: Dict[str, Any],
        original_query: str,
        llm_client,
        worksheets_queried: List[str]
    ) -> str:
        """Generate natural language summary of results."""
        user_query_lower = original_query.lower()
        wants_json = any(keyword in user_query_lower for keyword in ['json', 'json format', 'as json', 'in json'])
        
        if wants_json:
            prompt = f"""Given this SEO data analysis result, answer the user's question in JSON format.

User's question: {original_query}

Data sources: {', '.join(worksheets_queried)}

Analysis result: {result}

CRITICAL RULES:
- Return ONLY pure JSON (no markdown, no code blocks, no backticks)
- Start directly with {{ or [
- Use clean, simple formatting
- Do NOT use escape characters like \\n or \\t
- Do NOT add any text before or after the JSON
- Do NOT wrap in markdown code blocks (no ```json)"""
        else:
            prompt = f"""Given this SEO data analysis result, answer the user's question.

User's question: {original_query}

Data sources: {', '.join(worksheets_queried)}

Analysis result: {result}

CRITICAL RULES:
- Write in ONE continuous line of plain text (NO line breaks, NO newlines)
- Do NOT use any formatting: no bullet points, no asterisks, no markdown
- Do NOT use \\n or \\t or any escape characters
- Write as a single flowing sentence or paragraph
- Use commas to separate items instead of line breaks
- Be direct and clear (2-3 sentences max)
- Explain findings in a way anyone can understand
- Do NOT return JSON unless explicitly asked
- Example good format: "Found 3 broken pages: page1 (404), page2 (500), page3 (403)"
- Example BAD format: "Found pages:\\n* page1\\n* page2" (never do this)"""
        
        try:
            summary = llm_client.generate(
                system_prompt="You are a direct, honest SEO analyst. Report EXACTLY what is in the data. NEVER assume or invent data. If data is limited or missing, say so clearly. Use EXACT values from the data.",
                user_prompt=prompt,
                temperature=0.2
            )
            return summary.strip()
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return f"Analysis complete from {', '.join(worksheets_queried)}. Found {result.get('total_rows', 0)} results."
    
    def lookup_urls(self, urls: List[str], llm_client=None) -> pd.DataFrame:
        """
        Look up specific URLs in the SEO data.
        Used for fusion queries.
        
        Args:
            urls: List of URLs to look up
            llm_client: Optional LLM client for intelligent worksheet selection
            
        Returns:
            DataFrame with matching rows
        """
        # For URL lookup, internal_all is usually the best source
        worksheet_to_use = 'internal_all' if 'internal_all' in self.available_worksheets else self.available_worksheets[0]
        
        logger.info(f"Looking up {len(urls)} URLs in worksheet: {worksheet_to_use}")
        
        df = self.fetch_data(worksheet_to_use)
        
        if df.empty:
            logger.warning("SEO data is empty")
            return pd.DataFrame()
        
        logger.info(f"SEO data loaded: {len(df)} rows, {len(df.columns)} columns")
        
        # Try common URL column names (case-insensitive)
        url_columns = ['address', 'Address', 'url', 'URL', 'page', 'Page', 'path', 'Path', 'source', 'Source']
        url_col = None
        
        for col in url_columns:
            if col in df.columns:
                url_col = col
                logger.info(f"Found URL column: '{url_col}'")
                break
        
        if url_col is None:
            logger.warning(f"Could not find URL column in {worksheet_to_use}")
            logger.warning(f"Available columns: {df.columns.tolist()}")
            return pd.DataFrame()
        
        # Log sample values from SEO data
        sample_seo_urls = df[url_col].head(10).tolist()
        logger.debug(f"Sample SEO URLs: {sample_seo_urls}")
        
        # Try exact match first
        matches = df[df[url_col].isin(urls)]
        logger.info(f"Exact match: Found {len(matches)} matches")
        
        if len(matches) == 0 and len(urls) > 0:
            logger.info("Trying path-based matching")
            
            from urllib.parse import urlparse
            
            # Extract paths from GA4 URLs (they might already be paths)
            ga4_paths = []
            for url in urls:
                if url is None or url == "":
                    continue  # Skip None/empty URLs
                url_str = str(url).strip()
                if url_str.startswith('http'):
                    ga4_paths.append(urlparse(url_str).path)
                else:
                    ga4_paths.append(url_str)
            
            logger.debug(f"GA4 paths: {ga4_paths[:10]}")
            
            # Extract paths from SEO URLs
            seo_paths = []
            for seo_url in df[url_col]:
                if pd.notna(seo_url) and seo_url:
                    url_str = str(seo_url).strip()
                    if url_str.startswith('http'):
                        seo_paths.append(urlparse(url_str).path)
                    else:
                        seo_paths.append(url_str)
                else:
                    seo_paths.append(None)
            
            df['_temp_path'] = seo_paths
            
            logger.debug(f"SEO paths (sample): {[p for p in seo_paths[:10] if p]}")
            
            matches = df[df['_temp_path'].isin(ga4_paths)]
            df = df.drop('_temp_path', axis=1)
            
            logger.info(f"Path-based match: Found {len(matches)} matches")
        
        if len(matches) == 0:
            logger.warning("No URL matches found")
            logger.debug(f"GA4 URLs: {urls[:5]}")
            logger.debug(f"SEO URLs (sample): {sample_seo_urls[:5]}")
        else:
            logger.info(f"Found {len(matches)} matching URLs in SEO data")
        
        return matches

