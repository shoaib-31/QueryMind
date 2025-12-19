# Assumptions & Limitations

## Core Assumptions

### Data Sources
- GA4 property has active data collection with appropriate service account permissions
- Screaming Frog data follows standard worksheet naming (`internal_all`, `response_codes_all`, etc.)
- URLs in GA4 and Screaming Frog match format for fusion queries (exact or path-based)
- SEO data is relatively current

### LLM Services
- At least one LLM (primary or fallback) is available
- LLM can accurately classify query intent and parse English queries
- 30-second retry delay × 3 attempts is sufficient for rate limit recovery

### Metric Availability
- Deprecated GA4 metrics are automatically substituted:
  - `bounceRate` → `engagementRate`
  - `averageSessionDuration` → `userEngagementDuration`
  - `pageviews` → `screenPageViews`

## Known Limitations

### Functional
- Single query per request, no conversation history
- English-only optimized
- GA4 data has 24-48 hour latency
- Simple URL matching only (exact or path-based, no fuzzy matching)

### Performance
- Large SEO datasets (10k+ URLs) may cause slowdowns
- Each LLM call adds 1-5 seconds latency
- Rate limit retries add 30-90 seconds
- No query result caching

### Scale
- Single-threaded request processing
- Subject to GA4 API and LLM quotas
- Large SEO datasets loaded entirely into memory

### Integration
- Google Analytics and Google Sheets only
- Cannot query other analytics platforms or SEO tools

## Open Questions

**Performance & Latency**:
- Should we use a custom classification model instead of LLM for query routing?
- Should we implement async/parallel processing for GA4 and SEO data fetching?
- Should we stream LLM responses instead of waiting for complete generation?
- Should we migrate SEO data from Google Sheets to a database for faster queries?
- Should we use smaller/faster models for specific tasks (e.g., classification vs generation)?
- Should we pre-load and cache common SEO worksheets at startup?
- Should we implement request batching for multiple queries?

**Technical**:
- Should we implement query result caching? For how long?
- Should we support multiple GA4 properties?
- Should we integrate Google Search Console directly?

**Product**:
- Should we support conversation mode with follow-up questions?
- Should we generate visualizations (charts, graphs)?
- Should we implement user authentication and access control?

---

**Version**: 0.1.0  
**Last Updated**: December 2025
