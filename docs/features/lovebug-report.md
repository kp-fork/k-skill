# 러브버그.com 조회·제보 가이드

`lovebug-report`는 `러브버그.com`(`https://xn--2i0bt2q2wd1wb.com/`)의 공개 지도 JSON과 익명 제보 RPC 표면을 직접 사용하는 스킬이다. upstream이 인증/키 없이 열려 있는 공개 표면이므로 `k-skill-proxy`를 사용하지 않는다.

## 이 기능으로 할 수 있는 일

- 수도권 시·구별 러브버그 스코어, 최근 제보량, 강도 분포를 조회한다.
- 동/읍/면 area snapshot을 함께 조회해 지역을 좁힌다.
- 사용자가 제공한 현재 좌표·정확도·구 코드로 익명 러브버그 제보를 제출한다.

## 공개 접근 경로

- 지도: `https://xn--2i0bt2q2wd1wb.com/`
- 구별 점수: `GET /api/map/gu-score`
- 주간 제보 수: `GET /api/map/weekly-report-count`
- 클러스터: `GET /api/map/clusters?level=sigungu&historicalYear=2026`
- 동네 snapshot: `GET /api/map/areas?historicalYear=2026&includePolygon=false`
- 익명 제보: `POST https://sewrbxfawkmusnyzjoab.supabase.co/rest/v1/rpc/submit_anonymous_report`

익명 제보 body는 `p_gu_code`, `p_lng`, `p_lat`, `p_accuracy_m`, `p_level`, `p_device_hash`, `p_context`, `p_image_url`, `p_indoor`를 사용한다.

## CLI

```bash
node packages/lovebug-report/src/cli.js search --query 중랑 --include-areas
node packages/lovebug-report/src/cli.js list --limit 10
node packages/lovebug-report/src/cli.js report --gu-code 11070 --level 많아요 --context 길거리 --lng 127.09 --lat 37.59 --accuracy 25 --device-hash stable-id
```

패키지 설치 후에는 bin 이름을 사용할 수 있다.

```bash
lovebug-report search --query 동안
```

## Node API

```js
const { searchLovebugRegions, reportLovebug } = require("lovebug-report")

const status = await searchLovebugRegions({ query: "중랑", includeAreas: true })

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

## 응답 해석

러브버그 스코어는 최근 사용자 제보 기반이다. 답변할 때는 정부 공식 방제 통계가 아니라 `러브버그.com` 커뮤니티 제보 현황임을 밝힌다.

## 실패 모드

- `ANON_DAILY_DUPLICATE`: 같은 익명 기기에서 오늘 이미 제보했다.
- `OUTSIDE_GU_AREA`: 좌표가 선택한 구 밖이다.
- `ACCURACY_TOO_LOW`: 위치 정확도가 낮다.
- 사이트가 Next.js/Supabase route, anon key, RPC, rate limit 정책을 바꾸면 호출이 실패할 수 있다.
- 이미지 업로드는 자동화하지 않는다. 이미 호스팅된 URL만 `imageUrl`로 넘긴다.
