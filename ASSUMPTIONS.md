# Assumptions & Open Questions

This document outlines the assumptions made during development, known limitations, and open questions for future consideration.

## Core Assumptions

### 1. Data Source Assumptions

#### Google Analytics 4 (GA4)

**Assumptions**:
- GA4 property is correctly configured and actively collecting data
- Service account has appropriate `Viewer` permissions on the property
- Data collection has been active long enough to have meaningful historical data
- Property ID is accurately provided by the client
- GA4 Data API v1beta is stable and available

**Potential Issues**:
- New properties may have limited historical data
- API quotas may be reached during high-volume usage
- Real-time data is not available (24-48 hour delay typical)

#### Screaming Frog SEO Data

**Assumptions**:
- Screaming Frog crawl data is exported to Google Sheets in standard format
- Sheet structure follows Screaming Frog's default worksheet naming (e.g., `internal_all`, `response_codes_all`)
- Service account has read access to the Google Sheet
- SEO data is relatively current (crawled recently)
- URLs in SEO data match format of URLs in GA4 (for fusion queries)

**Potential Issues**:
- Custom Screaming Frog exports may have different worksheet names
- Large crawls (100k+ URLs) may cause performance issues
- URL format mismatches between GA4 and Screaming Frog can break fusion queries

### 2. LLM Service Assumptions

**Assumptions**:
- At least one LLM service (primary or fallback) is available
- LLM services can understand natural language queries in English
- LLM can accurately classify query intent (GA4, SEO, or Fusion)
- LLM can parse structured data formats (JSON)
- API keys are valid and have sufficient quota
- Retry logic (30 seconds × 3 attempts) is sufficient for rate limit recovery

**Potential Issues**:
- Both LLM services may be unavailable simultaneously
- Rate limits may be exhausted faster than retry delay allows
- Non-English queries may produce unreliable results
- Complex or ambiguous queries may be misclassified

### 3. Query Language & Format

**Assumptions**:
- Users will ask questions in English
- Query phrasing will be reasonably clear and unambiguous
- Users understand basic analytics terminology (pageviews, sessions, etc.)
- Users understand basic SEO terminology (status codes, meta tags, etc.)
- Date references ("last 7 days", "this month") can be reliably parsed by LLM

**Potential Issues**:
- Ambiguous queries may be routed incorrectly
- Non-standard terminology may confuse the LLM
- Very technical jargon may not be understood
- Multiple questions in one query may produce incomplete answers

### 4. URL Matching (Fusion Queries)

**Assumptions**:
- GA4 records `pagePath` dimension accurately
- Screaming Frog records full URLs or paths in `address` column
- URLs can be matched either exactly or by path
- URL normalization (trailing slashes, protocols) is consistent between sources

**Potential Issues**:
- Query parameters may cause mismatches
- Hash fragments (#) may not match
- Protocol differences (http vs https) may prevent matches
- Internationalized URLs may cause encoding issues

### 5. Metric Availability

**Assumptions**:
- Modern GA4 metrics are preferred over deprecated UA metrics
- Users can accept metric substitutions (e.g., bounceRate → engagementRate)
- Substituted metrics provide comparable insights to original metrics
- System can identify deprecated metrics from query text

**Known Substitutions**:
- `bounceRate` → `engagementRate` (inverse relationship)
- `averageSessionDuration` → `userEngagementDuration`
- `pageviews` → `screenPageViews`

**Potential Issues**:
- Users expecting exact UA metrics may be confused by GA4 equivalents
- Inverse relationships (engagement vs bounce) require clear explanation
- Some UA metrics have no direct GA4 equivalent

## Known Limitations

### 1. Functional Limitations

#### Query Processing

- **Single Query Per Request**: Cannot handle multiple questions in one request
- **English Only**: Optimized for English language queries
- **No Conversation History**: Each query is independent, no context from previous queries
- **Limited Comparison Queries**: Cannot easily compare multiple date ranges or segments simultaneously

#### Data Retrieval

- **GA4 Data Limit**: Default limit of 10 rows per query (can be increased but may impact performance)
- **No Real-Time Data**: GA4 data has 24-48 hour latency
- **Single GA4 Property**: Can only query one property per request
- **SEO Data Static**: No real-time crawling, relies on pre-existing Screaming Frog data

#### URL Matching

- **Simple Matching Only**: Exact match or path-based match only
- **No Fuzzy Matching**: Cannot handle slight URL variations
- **No Domain Mapping**: Cannot map subdomains or cross-domain URLs
- **Case Sensitive**: URL matching may be case-sensitive

### 2. Performance Limitations

- **Large Dataset Performance**: SEO queries slow down with 10k+ URLs
- **Multiple Worksheets**: Querying multiple large worksheets increases latency
- **LLM Latency**: Each LLM call adds 1-5 seconds to processing time
- **Retry Delays**: Rate limit retries add 30-90 seconds to failed requests
- **No Query Caching**: Identical queries are re-processed each time

### 3. Scale Limitations

- **Concurrent Requests**: Single-threaded processing, no request queuing
- **Rate Limits**: Subject to GA4 API quotas (e.g., 10 requests per second)
- **LLM Quotas**: Subject to LiteLLM and Gemini API quotas
- **Memory Usage**: Large SEO datasets loaded entirely into memory

### 4. Integration Limitations

- **Google Services Only**: Only supports Google Analytics and Google Sheets
- **No Other Analytics Platforms**: Cannot query Adobe Analytics, Matomo, etc.
- **No Other SEO Tools**: Cannot query Ahrefs, SEMrush, Moz, etc.
- **No Database Integration**: Cannot query custom databases or data warehouses

### 5. Answer Quality Limitations

- **LLM Hallucination**: LLM may occasionally generate incorrect interpretations
- **Incomplete Data**: May not notice missing or incomplete data in responses
- **No Data Validation**: Does not validate if returned data makes business sense
- **JSON Formatting**: Sometimes returns JSON wrapped in markdown despite instructions

## Open Questions

### Technical Questions

1. **Caching Strategy**
   - Q: Should we implement query result caching?
   - Q: How long should cached results be valid?
   - Q: Should we cache per user or globally?

2. **Performance Optimization**
   - Q: Should we implement pagination for large SEO datasets?
   - Q: Should we pre-load and cache common SEO worksheets at startup?
   - Q: Should we implement parallel LLM calls for fusion queries?

3. **Error Handling**
   - Q: Should we retry GA4 API calls on transient failures?
   - Q: Should we implement circuit breaker pattern for external APIs?
   - Q: How should we handle partial failures in fusion queries?

4. **LLM Selection**
   - Q: Should we allow users to specify which LLM model to use?
   - Q: Should we use different LLMs for different tasks (routing vs generation)?
   - Q: Should we implement LLM response streaming?

5. **Data Processing**
   - Q: Should we implement data aggregation before sending to LLM?
   - Q: Should we limit data size in LLM prompts?
   - Q: Should we implement incremental data loading for large datasets?

### Product Questions

1. **Query Capabilities**
   - Q: Should we support follow-up questions in conversation mode?
   - Q: Should we support query history and favorites?
   - Q: Should we support scheduled/recurring queries?

2. **Data Sources**
   - Q: Should we support multiple GA4 properties?
   - Q: Should we support multiple SEO data sources?
   - Q: Should we integrate with Google Search Console directly?
   - Q: Should we support custom data source connectors?

3. **Output Format**
   - Q: Should we support visualization generation (charts, graphs)?
   - Q: Should we support exporting results to CSV, PDF, etc.?
   - Q: Should we support customizable answer formats?

4. **User Experience**
   - Q: Should we provide query suggestions or templates?
   - Q: Should we show confidence scores for answers?
   - Q: Should we show which data sources were used?
   - Q: Should we provide explanations of how answers were derived?

5. **Access Control**
   - Q: Should we implement user authentication?
   - Q: Should we implement role-based access control?
   - Q: Should we limit which properties/sheets users can query?
   - Q: Should we implement audit logging?

### Business Questions

1. **Pricing & Quotas**
   - Q: How should we handle LLM API costs?
   - Q: Should we implement usage quotas per user/organization?
   - Q: How do we handle cost overruns from high LLM usage?

2. **Compliance**
   - Q: Are there data retention requirements?
   - Q: Should we implement PII detection and filtering?
   - Q: What regions should the service be available in?
   - Q: Are there specific compliance requirements (GDPR, CCPA, etc.)?

3. **SLA & Reliability**
   - Q: What uptime SLA should we target?
   - Q: What is acceptable query latency?
   - Q: Should we implement redundancy for critical components?

## Future Considerations

### Short-Term Improvements

1. **Better URL Matching**: Implement fuzzy matching and normalization
2. **Query Caching**: Cache frequent query patterns
3. **Performance Monitoring**: Add detailed metrics and tracing
4. **Error Messages**: Improve user-facing error messages
5. **Validation**: Add more comprehensive input validation

### Medium-Term Enhancements

1. **Conversation Mode**: Support multi-turn conversations
2. **Visualization**: Generate charts and graphs
3. **Export Options**: Support multiple export formats
4. **Search Console Integration**: Direct GSC API integration
5. **Custom Data Sources**: Plugin architecture for custom integrations

### Long-Term Vision

1. **Multi-Source Analytics**: Support multiple analytics platforms
2. **Predictive Analytics**: ML-based predictions and forecasting
3. **Automated Insights**: Proactive anomaly detection and insights
4. **Natural Language Reports**: Generate complete reports from queries
5. **Voice Interface**: Support voice queries and audio responses

## Assumptions to Validate

### High Priority

1. **URL Matching Accuracy**: Validate that GA4 and Screaming Frog URLs match reliably
2. **LLM Classification Accuracy**: Measure intent classification error rate
3. **Query Latency**: Validate that response times are acceptable (< 10 seconds)
4. **Metric Substitution Acceptance**: Verify users understand and accept metric substitutions

### Medium Priority

1. **Large Dataset Performance**: Test with 50k+ URL SEO datasets
2. **Concurrent User Load**: Test with multiple simultaneous users
3. **LLM Cost Per Query**: Measure actual LLM API costs
4. **Error Rate**: Measure query failure rates by error type

### Low Priority

1. **Non-English Queries**: Test accuracy with other languages
2. **Edge Case Queries**: Test with unusual or complex queries
3. **Long-Term Stability**: Monitor performance over extended periods
4. **API Version Changes**: Track GA4 API changes and deprecations

## Risk Assessment

### High Risk

1. **LLM Service Dependency**: System unusable if both LLMs fail
2. **URL Matching**: Fusion queries may fail if URL formats don't match
3. **GA4 API Changes**: Breaking changes in GA4 API could break integration
4. **Rate Limits**: Could hit API limits during high usage

### Medium Risk

1. **LLM Hallucination**: May generate incorrect insights
2. **Query Misclassification**: May route queries to wrong agent
3. **Data Staleness**: SEO data may be outdated
4. **Cost Overruns**: High LLM usage could exceed budget

### Low Risk

1. **Sheet Structure Changes**: Screaming Frog format is relatively stable
2. **Service Account Permissions**: Usually set up correctly once
3. **Network Issues**: Transient and usually self-resolving

## Mitigation Strategies

1. **LLM Dependency**: Implement fallback + consider caching common query patterns
2. **URL Matching**: Provide clear error messages, suggest URL format corrections
3. **API Changes**: Monitor GA4 changelog, implement API versioning
4. **Rate Limits**: Implement request queuing, backoff strategies
5. **Hallucination**: Add confidence scores, allow user feedback
6. **Misclassification**: Log classification decisions, allow manual override
7. **Cost Control**: Implement usage quotas, optimize prompts

---

**Version**: 0.1.0  
**Last Updated**: December 2025

**Review Schedule**: These assumptions should be reviewed quarterly and updated based on:
- User feedback
- System metrics
- New feature requirements
- Technology changes

