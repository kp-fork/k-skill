# k-skill-proxy 배포 가이드 (gpu01 + cron + Docker)

`k-skill-proxy` 프로덕션은 이제 Google Cloud Run이 아니라 **gpu01**의 Docker 컨테이너로 운영한다. GitHub Actions의 `main` push/merge 자동 배포는 프로덕션 배포 경로가 아니다.

이 문서는 gpu01의 cron 기반 자동 배포, 시크릿/env 배치, 헬스체크, 로그, 롤백, 그리고 기존 GCP 리소스 정리 절차를 정리한다. 일반 contributor는 읽지 않아도 되며, 프록시 운영 maintainer가 gpu01 운영·복구·인계를 할 때 기준 문서로 사용한다.

## 운영 사실

| 항목 | 값 |
| --- | --- |
| 프로덕션 호스트 | `gpu01` |
| 공개 도메인 | `https://k-skill-proxy.nomadamas.org` |
| 런타임 | Docker container |
| 컨테이너 이름 | `k-skill-proxy` |
| 후보 컨테이너 이름 | `k-skill-proxy-candidate` |
| 이미지 태그 | `k-skill-proxy:<git-sha>` |
| 컨테이너 이미지 정의 | `packages/k-skill-proxy/Dockerfile` |
| Docker build context | repo root (`/opt/k-skill/current` 기준) |
| 배포 스크립트 | `scripts/deploy-k-skill-proxy-gpu01.sh` |
| 권장 repo checkout | `/opt/k-skill/current` |
| 비밀 env 파일 | `/etc/k-skill-proxy/secrets.env` (`0600` 또는 더 엄격) |
| 배포 대상 config | `/etc/k-skill-proxy/deploy.env` (`0640` 또는 더 엄격) |
| 로그 디렉터리 | `/var/log/k-skill-proxy` |
| 상태 디렉터리 | `/var/lib/k-skill-proxy` |
| 프로덕션 포트 | host `127.0.0.1:4020` → container `8080` |
| 후보 smoke 포트 | host `127.0.0.1:4021` → container `8080` |
| 배포 트리거 | gpu01 cron이 host-configured deploy SHA/ref만 배포 |

## 배포 의미론

- `main` merge 자체는 프로덕션을 바꾸지 않는다.
- gpu01 cron은 `/etc/k-skill-proxy/deploy.env`에 명시된 `KSKILL_PROXY_DEPLOY_SHA` 또는 `KSKILL_PROXY_DEPLOY_REF`만 배포한다.
- 배포 대상이 설정되지 않았으면 스크립트는 fail-closed로 종료한다.
- 스크립트는 절대 `origin/main`을 기본값으로 삼지 않는다.
- 권장 초기 컷오버 방식은 `KSKILL_PROXY_DEPLOY_SHA=<full commit sha>`를 고정하는 것이다.
- git 기반 승격이 더 편하면 `KSKILL_PROXY_DEPLOY_REF=production` 같은 전용 production branch/ref를 쓰되, 그 ref를 갱신하는 행위가 곧 프로덕션 승격이다.

## 배포 흐름

cron이 실행하는 한 번의 배포는 다음 순서로만 성공한다.

1. `flock`으로 중복 실행을 막는다.
2. `/etc/k-skill-proxy/deploy.env`와 `/etc/k-skill-proxy/secrets.env`를 검증한다.
3. repo root에서 `git fetch --prune origin`을 실행한다.
4. 명시된 deploy SHA/ref를 commit SHA로 해석한다.
5. 현재 배포된 SHA와 같으면 아무 것도 바꾸지 않고 종료한다.
6. 기존 serving state를 `/var/lib/k-skill-proxy/rollback-state.env`에 저장한다.
7. checkout을 resolved SHA로 detach/force 이동한 뒤 repo root build context로 이미지를 빌드한다.
8. 후보 컨테이너를 `127.0.0.1:4021`에서 띄운다.
9. 후보 컨테이너의 local `/health`가 `ok: true`이고 필수 upstream 설정 boolean이 true인지 확인한다.
10. 기존 프로덕션 컨테이너를 교체해 `127.0.0.1:4020`에 새 컨테이너를 띄운다.
11. `https://k-skill-proxy.nomadamas.org/health` public smoke를 수행한다.
12. 대표 read-only public route smoke를 수행한다.
13. 모든 public smoke가 통과한 뒤에만 `/var/lib/k-skill-proxy/deployed-sha`를 갱신한다.

public smoke 실패는 경고가 아니라 배포 실패다. 상태 파일을 갱신하지 않고, 가능한 경우 이전 컨테이너/image/port/routing state로 rollback을 시도한다.

## 1회성 gpu01 셋업

```bash
sudo install -d -m 0755 /opt/k-skill
sudo install -d -m 0750 /etc/k-skill-proxy
sudo install -d -m 0750 /var/lib/k-skill-proxy
sudo install -d -m 0750 /var/log/k-skill-proxy

# repo checkout. 운영자가 실제 deploy user 권한에 맞춰 owner를 조정한다.
sudo git clone https://github.com/NomaDamas/k-skill.git /opt/k-skill/current
```

필수 도구:

- `git`
- `docker`
- `curl`
- `python3`
- `flock` (`util-linux`)

reverse proxy는 `https://k-skill-proxy.nomadamas.org`를 gpu01의 `127.0.0.1:4020`으로 전달해야 한다. DNS/TLS/reverse proxy 설정은 repo 밖의 호스트 설정이므로 컷오버 때 public `/health`로 반드시 검증한다.

## 배포 대상 설정

`/etc/k-skill-proxy/deploy.env` 예시:

```bash
# 가장 안전한 초기 컷오버: 정확한 commit SHA 고정
KSKILL_PROXY_DEPLOY_SHA=0123456789abcdef0123456789abcdef01234567

# 또는 전용 production ref를 의도적으로 운용할 때만 사용
# KSKILL_PROXY_DEPLOY_REF=production

KSKILL_PROXY_REPO_DIR=/opt/k-skill/current
KSKILL_PROXY_CONTAINER_NAME=k-skill-proxy
KSKILL_PROXY_IMAGE_NAME=k-skill-proxy
KSKILL_PROXY_HOST_PORT=4020
KSKILL_PROXY_CANDIDATE_PORT=4021
KSKILL_PROXY_CONTAINER_PORT=8080
KSKILL_PROXY_PUBLIC_BASE_URL=https://k-skill-proxy.nomadamas.org
KSKILL_PROXY_STATE_DIR=/var/lib/k-skill-proxy
KSKILL_PROXY_LOG_DIR=/var/log/k-skill-proxy
```

둘 다 설정되어 있으면 `KSKILL_PROXY_DEPLOY_SHA`가 우선한다. 둘 다 없으면 배포하지 않는다.

## 프로덕션 승격 절차

### pinned SHA 방식

1. `dev` → `main` merge 후 검증할 commit SHA를 정한다.
2. gpu01에서 `/etc/k-skill-proxy/deploy.env`의 `KSKILL_PROXY_DEPLOY_SHA`를 해당 full SHA로 바꾼다.
3. cron이 다음 주기에 배포하거나, 운영자가 스크립트를 수동 실행한다.

### production branch 방식

1. `production` 같은 전용 branch/ref를 운영한다.
2. maintainer가 의도적으로 해당 ref를 fast-forward 또는 갱신한다.
3. gpu01 cron은 `KSKILL_PROXY_DEPLOY_REF=production`만 해석해서 배포한다.

이 방식을 써도 `main` merge 단독으로는 배포되지 않는다.

## 시크릿과 runtime env

`/etc/k-skill-proxy/secrets.env`는 repo에 넣지 않는다. root 또는 전용 deploy user만 읽을 수 있게 `0600` 또는 더 엄격하게 둔다.

필수/운영 env 예시:

```bash
AIR_KOREA_OPEN_API_KEY=...
KMA_OPEN_API_KEY=...
SEOUL_OPEN_API_KEY=...
HRFCO_OPEN_API_KEY=...
OPINET_API_KEY=...
DATA_GO_KR_API_KEY=...
DATA4LIBRARY_AUTH_KEY=...
FOODSAFETYKOREA_API_KEY=...
KAKAO_REST_API_KEY=...
KEDU_INFO_KEY=...
KRX_API_KEY=...
KOSIS_API_KEY=...
NAVER_SEARCH_CLIENT_ID=...
NAVER_SEARCH_CLIENT_SECRET=...
LAW_OC=...

# 선택
LAW_REFERER=
LAW_USER_AGENT=

# runtime knobs
KSKILL_PROXY_HOST=0.0.0.0
KSKILL_PROXY_NAME=k-skill-proxy
KSKILL_PROXY_CACHE_TTL_MS=300000
KSKILL_PROXY_RATE_LIMIT_WINDOW_MS=60000
KSKILL_PROXY_RATE_LIMIT_MAX=60
PORT=8080
```

## Docker access 보안 경계

Docker daemon, Docker socket, `docker` group, `sudo docker`, 컨테이너 inspect/start 권한은 모두 프로덕션 시크릿 접근 권한과 동일하게 취급한다. 컨테이너 env, bind mount, 로그, 대체 컨테이너 실행을 통해 upstream API key를 읽을 수 있기 때문이다.

- 편의상 일반 사용자를 `docker` group에 추가하지 않는다.
- cron user는 프로덕션 운영자로 간주하고 의도적으로 선택한다.
- 배포 스크립트는 `set -x`를 쓰지 않고 env 값을 로그에 출력하지 않는다.
- Docker socket을 외부에 노출하지 않는다.

## cron 설정

crontab 예시:

```cron
*/10 * * * * flock -n /var/lock/k-skill-proxy-deploy.lock /opt/k-skill/current/scripts/deploy-k-skill-proxy-gpu01.sh >> /var/log/k-skill-proxy/deploy.log 2>&1
```

cron은 production deploy trigger지만, 배포 대상은 항상 `/etc/k-skill-proxy/deploy.env`의 explicit SHA/ref다. cron 주기가 돌아도 대상 SHA가 바뀌지 않았으면 스크립트는 skip한다.

## 수동 배포/점검

```bash
/opt/k-skill/current/scripts/deploy-k-skill-proxy-gpu01.sh
curl -fsS https://k-skill-proxy.nomadamas.org/health
```

로그:

```bash
tail -f /var/log/k-skill-proxy/deploy.log
docker logs --tail=200 k-skill-proxy
```

## smoke test 기준

### local health

```bash
curl -fsS http://127.0.0.1:4021/health
```

candidate 단계에서는 후보 포트 `4021`, production 단계에서는 `4020`을 확인한다. `/health` JSON은 `ok: true`여야 하며, `upstreams`의 `*Configured` boolean이 true인지 확인한다.

### public health

```bash
curl -fsS https://k-skill-proxy.nomadamas.org/health
```

public health 실패는 배포 실패다. deployed-state를 갱신하지 않는다.

### 대표 route smoke

기본 대표 route는 health만으로 잡히지 않는 public routing/API path 회귀를 확인하기 위한 read-only 요청이다. 운영 환경에서 upstream quota/availability를 고려해 route를 조정할 수 있다.

```bash
curl -fsS --get 'https://k-skill-proxy.nomadamas.org/v1/fine-dust/report' \
  --data-urlencode 'stationName=종로구'
```

upstream 자체 장애가 확인된 경우에만 운영자가 로그에 사유를 남기고 route smoke를 별도 처리한다. public `/health`는 항상 필수다.

## rollback

배포 스크립트는 production switch 전에 `/var/lib/k-skill-proxy/rollback-state.env`에 다음 값을 저장한다.

- timestamp
- previous deployed SHA
- previous image tag 또는 image ID
- previous container name
- previous container ID
- previous host port → container port mapping
- previous reverse-proxy upstream target
- previous routing state
- previous health status

수동 rollback 기본 절차:

```bash
sudo -E /opt/k-skill/current/scripts/deploy-k-skill-proxy-gpu01.sh --rollback
curl -fsS https://k-skill-proxy.nomadamas.org/health
```

문제가 이미지가 아니라 reverse proxy/DNS/TLS인 경우에는 저장된 routing state에 따라 이전 upstream target 또는 proxy 설정을 복원하고 proxy를 reload한다. rollback은 이전 이미지를 띄우는 것만으로 충분하다고 가정하지 않는다.

## 문제 해결

| 증상 | 확인할 것 |
| --- | --- |
| `no deploy target configured` | `/etc/k-skill-proxy/deploy.env`에 `KSKILL_PROXY_DEPLOY_SHA` 또는 `KSKILL_PROXY_DEPLOY_REF`가 있는지 확인 |
| health의 `*Configured`가 false | `/etc/k-skill-proxy/secrets.env`에 해당 upstream key가 있는지 확인 |
| Docker build 실패 | repo root에서 `-f packages/k-skill-proxy/Dockerfile .`로 빌드되는지 확인 |
| public health 실패 | DNS, TLS, reverse proxy upstream, firewall, container port mapping 확인 |
| cron은 도는데 배포가 안 됨 | deployed SHA와 resolved SHA가 같은지, lock이 오래 잡혀 있는지, 로그 권한 확인 |
| rollback 후에도 public 장애 | reverse proxy/routing state가 이전 target으로 복원됐는지 확인 |

## 기존 GCP/Cloud Run 정리

GitHub Actions의 Cloud Run 자동 배포는 즉시 비활성화한다. 다만 Cloud Run, Artifact Registry, WIF, Secret Manager 리소스는 gpu01 안정화 기간 동안 legacy rollback/비교용으로 잠시 남길 수 있다.

정리 순서:

1. gpu01 public `/health`와 대표 route smoke가 안정적으로 통과하는지 확인한다.
2. GitHub에 push-to-main 배포 workflow가 남아 있지 않은지 확인한다.
3. rollback window가 끝나면 Cloud Run traffic, Artifact Registry image, WIF provider/service account, Secret Manager secret을 수동 정리한다.
4. 정리 기록은 운영 로그나 PR 본문에 남긴다.
