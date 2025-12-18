import json, time, requests

MEASUREMENT_ID = os.getenv("GA4_MEASUREMENT_ID")
API_SECRET = os.getenv("GA4_API_SECRET")
ENDPOINT = f"https://www.google-analytics.com/mp/collect?measurement_id={MEASUREMENT_ID}&api_secret={API_SECRET}"

with open("ga4_mp_ingest.json", "r", encoding="utf-8") as f:
    data = json.load(f)

payloads = data["payloads"]
ok = fail = 0

for i, p in enumerate(payloads, 1):
    r = requests.post(ENDPOINT, json=p, timeout=15)
    if r.status_code in (200, 204):
        ok += 1
    else:
        fail += 1
        print("fail", i, r.status_code, r.text[:200])

    if i % 200 == 0:
        print(f"progress {i}/{len(payloads)} ok={ok} fail={fail}")
    time.sleep(0.05)  # reduce to 0.02 if you want faster

print("done", ok, fail)
