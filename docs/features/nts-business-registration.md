# 국세청 사업자등록정보 진위확인 및 상태조회

`nts-business-registration` 스킬은 공공데이터포털의 **국세청_사업자등록정보 진위확인 및 상태조회 서비스**를 `k-skill-proxy` 경유로 호출한다.

## 제공 기능

- 사업자등록번호 상태조회: `POST /v1/nts-business/status`
- 사업자등록정보 진위확인: `POST /v1/nts-business/validate`

## 인증/시크릿

사용자 로컬 시크릿은 필요 없다. upstream `DATA_GO_KR_API_KEY`는 프록시 서버에만 둔다.

self-host 프록시를 쓰는 경우에만 `KSKILL_PROXY_BASE_URL`을 설정한다. 비우면 hosted proxy(`https://k-skill-proxy.nomadamas.org`)를 사용한다.

## 예시

```bash
python3 nts-business-registration/scripts/nts_business_registration.py status \
  --b-no 123-45-67890
```

```bash
python3 nts-business-registration/scripts/nts_business_registration.py validate \
  --business-json '{"b_no":"123-45-67890","start_dt":"2020-01-31","p_nm":"홍길동","b_nm":"테스트상사"}'
```

## 입력 제한

- 사업자등록번호는 숫자 10자리여야 한다. 하이픈은 자동 제거한다.
- 상태조회/진위확인은 한 번에 최대 100건까지 보낸다.
- 진위확인은 `b_no`, `start_dt`, `p_nm`이 필수다.
- 선택 필드: `p_nm2`, `b_nm`, `corp_no`, `b_sector`, `b_type`, `b_adr`

## 실패 모드

- `400 bad_request`: 입력 형식 오류 또는 필수 필드 누락
- `503 upstream_not_configured`: 프록시 서버에 `DATA_GO_KR_API_KEY` 없음
- upstream 인증/활용신청 오류: 공공데이터포털 키가 해당 서비스에 승인되지 않았거나 오류 상태

## 공식 출처

- 공공데이터포털: <https://www.data.go.kr/tcs/dss/selectApiDataDetailView.do?publicDataPk=15081808>
