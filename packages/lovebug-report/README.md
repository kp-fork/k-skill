# lovebug-report

Public `lovebug.com` map lookup and anonymous report client for the `lovebug-report` k-skill.

## Source

- Public site: `https://xn--2i0bt2q2wd1wb.com/` (`러브버그.com`)
- Public map JSON:
  - `GET /api/map/gu-score`
  - `GET /api/map/weekly-report-count`
  - `GET /api/map/clusters?level=sigungu&historicalYear=2026`
  - `GET /api/map/areas?historicalYear=2026&includePolygon=false`
- Anonymous report surface observed in the Next.js bundle:
  - Supabase RPC: `POST https://sewrbxfawkmusnyzjoab.supabase.co/rest/v1/rpc/submit_anonymous_report`
  - Body keys: `p_gu_code`, `p_lng`, `p_lat`, `p_accuracy_m`, `p_level`, `p_device_hash`, `p_context`, `p_image_url`, `p_indoor`

No `k-skill-proxy` route is used because the map surfaces and anon report RPC are public and do not require an upstream API key. Reporting still uses the site's own validation and can reject duplicates, poor accuracy, or coordinates outside the selected gu.

## Usage

```js
const { searchLovebugRegions, reportLovebug } = require("lovebug-report")

const status = await searchLovebugRegions({ query: "중랑", includeAreas: true })
console.log(status.items[0])

await reportLovebug({
  guCode: "11070",
  level: "많아요",
  context: "길거리",
  lng: 127.09,
  lat: 37.59,
  accuracyM: 25,
  deviceHash: "stable-anonymous-device-id"
})
```

CLI:

```bash
lovebug-report search --query 중랑 --include-areas
lovebug-report list --limit 10
lovebug-report report --gu-code 11070 --level 많아요 --context 길거리 --lng 127.09 --lat 37.59 --accuracy 25 --device-hash stable-id
```

## Boundaries and failure modes

- Search data is user-report-based and should be described as current community reports, not official pest-control truth.
- Anonymous reports require real coordinates. The upstream rejects `OUTSIDE_GU_AREA`, `ACCURACY_TOO_LOW`, and `ANON_DAILY_DUPLICATE` cases.
- This package does not bypass location validation, login, CAPTCHA, rate limits, or duplicate limits.
- Image upload is not automated; pass `imageUrl` only when an image is already hosted in a place the site accepts.
