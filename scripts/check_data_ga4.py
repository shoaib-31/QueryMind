

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest,
    RunRealtimeReportRequest,
    DateRange,
    Dimension,
    Metric,
    OrderBy,
)

PROPERTY_ID = "481659673"

def print_rows(resp, max_rows=10):
    print(f"Rows returned: {len(resp.rows)}")
    for row in resp.rows[:max_rows]:
        dims = [dv.value for dv in row.dimension_values]
        mets = [mv.value for mv in row.metric_values]
        print("  dims:", dims, " metrics:", mets)

def run_realtime(client, prop):
    print("\n=== REALTIME (last ~30 mins) ===")
    # NOTE: realtime supports a limited schema; unifiedScreenName works widely.
    req = RunRealtimeReportRequest(
        property=prop,
        dimensions=[Dimension(name="unifiedScreenName")],
        metrics=[Metric(name="screenPageViews"), Metric(name="activeUsers")],
    )
    resp = client.run_realtime_report(req)
    print_rows(resp, max_rows=20)

def run_daily_totals(client, prop, start, end):
    print(f"\n=== PROCESSED DAILY TOTALS ({start} to {end}) ===")
    req = RunReportRequest(
        property=prop,
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name="date")],
        metrics=[Metric(name="screenPageViews"), Metric(name="totalUsers"), Metric(name="sessions")],
        order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date"))],
    )
    resp = client.run_report(req)
    print_rows(resp, max_rows=20)

def run_top_pages(client, prop, start, end):
    print(f"\n=== TOP PAGES ({start} to {end}) ===")
    req = RunReportRequest(
        property=prop,
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="screenPageViews"), Metric(name="totalUsers")],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"), desc=True)],
        limit=10,
    )
    resp = client.run_report(req)
    print_rows(resp, max_rows=10)

def main():
    if PROPERTY_ID == "YOUR_PROPERTY_ID":
        print("❌ Set PROPERTY_ID at the top of the script.")
        return

    client = BetaAnalyticsDataClient()
    prop = f"properties/{PROPERTY_ID}"

    # 1) Realtime (fastest proof of ingestion)
    run_realtime(client, prop)

    # 2) Processed reporting data probes
    run_daily_totals(client, prop, "7daysAgo", "today")
    run_daily_totals(client, prop, "30daysAgo", "today")

    # 3) If processed data exists, this will show your top pages
    run_top_pages(client, prop, "30daysAgo", "today")

if __name__ == "__main__":
    main()

