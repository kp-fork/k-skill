#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE="${KSKILL_PROXY_DEPLOY_CONFIG:-/etc/k-skill-proxy/deploy.env}"
SECRETS_FILE="${KSKILL_PROXY_SECRETS_FILE:-/etc/k-skill-proxy/secrets.env}"

log() {
  printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

fail() {
  log "ERROR: $*"
  exit 1
}

quote_env_value() {
  printf '%q' "$1"
}


load_config() {
  [[ -r "$CONFIG_FILE" ]] || fail "deploy config is not readable: $CONFIG_FILE"
  # shellcheck disable=SC1090
  set -a; source "$CONFIG_FILE"; set +a

  : "${KSKILL_PROXY_REPO_DIR:=/opt/k-skill/current}"
  : "${KSKILL_PROXY_CONTAINER_NAME:=k-skill-proxy}"
  : "${KSKILL_PROXY_CANDIDATE_NAME:=k-skill-proxy-candidate}"
  : "${KSKILL_PROXY_IMAGE_NAME:=k-skill-proxy}"
  : "${KSKILL_PROXY_HOST_PORT:=4020}"
  : "${KSKILL_PROXY_CANDIDATE_PORT:=4021}"
  : "${KSKILL_PROXY_CONTAINER_PORT:=8080}"
  : "${KSKILL_PROXY_PUBLIC_BASE_URL:=https://k-skill-proxy.nomadamas.org}"
  : "${KSKILL_PROXY_STATE_DIR:=/var/lib/k-skill-proxy}"
  : "${KSKILL_PROXY_LOG_DIR:=/var/log/k-skill-proxy}"
  : "${KSKILL_PROXY_ROLLBACK_STATE:=${KSKILL_PROXY_STATE_DIR}/rollback-state.env}"
  : "${KSKILL_PROXY_DEPLOYED_SHA_FILE:=${KSKILL_PROXY_STATE_DIR}/deployed-sha}"

  if [[ -z "${KSKILL_PROXY_DEPLOY_SHA:-}" && -z "${KSKILL_PROXY_DEPLOY_REF:-}" ]]; then
    fail "no deploy target configured; set KSKILL_PROXY_DEPLOY_SHA or KSKILL_PROXY_DEPLOY_REF in $CONFIG_FILE"
  fi

  if [[ "${KSKILL_PROXY_DEPLOY_REF:-}" == "main" || "${KSKILL_PROXY_DEPLOY_REF:-}" == "origin/main" ]]; then
    fail "refusing to deploy main implicitly; configure a pinned SHA or dedicated production ref"
  fi

  if [[ -n "${KSKILL_PROXY_DEPLOY_SHA:-}" && ! "$KSKILL_PROXY_DEPLOY_SHA" =~ ^[0-9a-fA-F]{40}$ ]]; then
    fail "KSKILL_PROXY_DEPLOY_SHA must be a full 40-character commit SHA"
  fi

  case "${KSKILL_PROXY_DEPLOY_REF:-}" in
    main|origin/main|refs/heads/main|refs/remotes/origin/main)
      fail "refusing to deploy main implicitly; configure a pinned SHA or dedicated production ref"
      ;;
    *[[:space:]]*)
      fail "deploy ref must not contain whitespace"
      ;;
  esac

  [[ -r "$SECRETS_FILE" ]] || fail "secrets env file is not readable: $SECRETS_FILE"
  if command -v stat >/dev/null 2>&1; then
    local mode
    mode="$(stat -f '%Lp' "$SECRETS_FILE" 2>/dev/null || stat -c '%a' "$SECRETS_FILE" 2>/dev/null || true)"
    case "$mode" in
      600|400|640|440) ;;
      *) fail "secrets env file must not be world-readable; current mode: ${mode:-unknown}" ;;
    esac
  fi

  mkdir -p "$KSKILL_PROXY_STATE_DIR" "$KSKILL_PROXY_LOG_DIR"
}

resolve_sha() {
  cd "$KSKILL_PROXY_REPO_DIR"
  git fetch --prune origin

  if [[ -n "${KSKILL_PROXY_DEPLOY_SHA:-}" ]]; then
    git rev-parse --verify "${KSKILL_PROXY_DEPLOY_SHA}^{commit}"
    return
  fi

  git rev-parse --verify "origin/${KSKILL_PROXY_DEPLOY_REF}^{commit}"
}

checkout_resolved_sha() {
  local sha="$1"
  cd "$KSKILL_PROXY_REPO_DIR"
  git checkout --detach --force "$sha"
}


record_rollback_state() {
  local previous_sha previous_container_id previous_image previous_ports previous_health timestamp
  timestamp="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  previous_sha="$(cat "$KSKILL_PROXY_DEPLOYED_SHA_FILE" 2>/dev/null || true)"
  previous_container_id="$(docker ps -aq --filter "name=^/${KSKILL_PROXY_CONTAINER_NAME}$" | head -n 1 || true)"
  previous_image=""
  previous_ports=""
  if [[ -n "$previous_container_id" ]]; then
    previous_image="$(docker inspect --format '{{.Image}}' "$previous_container_id" 2>/dev/null || true)"
    previous_ports="$(docker port "$previous_container_id" 2>/dev/null | tr '\n' ';' || true)"
  fi
  if curl -fsS --max-time 10 "http://127.0.0.1:${KSKILL_PROXY_HOST_PORT}/health" >/dev/null 2>&1; then
    previous_health="ok"
  else
    previous_health="failed_or_unreachable"
  fi

  {
    printf 'TIMESTAMP=%s\n' "$(quote_env_value "$timestamp")"
    printf 'PREVIOUS_DEPLOYED_SHA=%s\n' "$(quote_env_value "$previous_sha")"
    printf 'PREVIOUS_CONTAINER_NAME=%s\n' "$(quote_env_value "$KSKILL_PROXY_CONTAINER_NAME")"
    printf 'PREVIOUS_CONTAINER_ID=%s\n' "$(quote_env_value "$previous_container_id")"
    printf 'PREVIOUS_IMAGE=%s\n' "$(quote_env_value "$previous_image")"
    printf 'PREVIOUS_PORT_MAPPING=%s\n' "$(quote_env_value "$previous_ports")"
    printf 'PREVIOUS_REVERSE_PROXY_TARGET=%s\n' "$(quote_env_value "127.0.0.1:$KSKILL_PROXY_HOST_PORT")"
    printf 'PREVIOUS_ROUTING_STATE=%s\n' "$(quote_env_value "public-domain:$KSKILL_PROXY_PUBLIC_BASE_URL->127.0.0.1:$KSKILL_PROXY_HOST_PORT")"
    printf 'PREVIOUS_HEALTH_STATUS=%s\n' "$(quote_env_value "$previous_health")"
  } > "$KSKILL_PROXY_ROLLBACK_STATE"
}

health_check() {
  local url="$1"
  local tmp status
  tmp="$(mktemp)"
  if ! curl -fsS --max-time 20 "$url" > "$tmp"; then
    rm -f "$tmp"
    return 1
  fi
  python3 - "$tmp" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path))
if data.get("ok") is not True:
    raise SystemExit(f"health ok was not true: {data}")
missing = [k for k, v in data.get("upstreams", {}).items() if k.endswith("Configured") and v is not True]
if missing:
    raise SystemExit(f"upstreams not configured: {missing}")
PY
  status=$?
  rm -f "$tmp"
  return "$status"
}

public_route_smoke() {
  curl -fsS --max-time 30 --get "${KSKILL_PROXY_PUBLIC_BASE_URL%/}/v1/fine-dust/report" \
    --data-urlencode 'stationName=종로구' >/dev/null
}

start_container() {
  local name="$1"
  local port="$2"
  local image="$3"
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run -d \
    --name "$name" \
    --restart unless-stopped \
    --env-file "$SECRETS_FILE" \
    -e PORT="$KSKILL_PROXY_CONTAINER_PORT" \
    -e KSKILL_PROXY_HOST=0.0.0.0 \
    -p "127.0.0.1:${port}:${KSKILL_PROXY_CONTAINER_PORT}" \
    "$image" >/dev/null
}

rollback() {
  [[ -r "$KSKILL_PROXY_ROLLBACK_STATE" ]] || fail "rollback state missing: $KSKILL_PROXY_ROLLBACK_STATE"
  # shellcheck disable=SC1090
  source "$KSKILL_PROXY_ROLLBACK_STATE"
  if [[ -z "${PREVIOUS_DEPLOYED_SHA:-}" ]]; then
    log "rollback state has no previous SHA; no prior production deployment to restore"
    return 1
  fi
  local image="${KSKILL_PROXY_IMAGE_NAME}:${PREVIOUS_DEPLOYED_SHA}"
  log "rolling back to $image and route ${PREVIOUS_REVERSE_PROXY_TARGET:-127.0.0.1:${KSKILL_PROXY_HOST_PORT}}"
  start_container "$KSKILL_PROXY_CONTAINER_NAME" "$KSKILL_PROXY_HOST_PORT" "$image"
  health_check "http://127.0.0.1:${KSKILL_PROXY_HOST_PORT}/health"
  health_check "${KSKILL_PROXY_PUBLIC_BASE_URL%/}/health"
  printf '%s\n' "$PREVIOUS_DEPLOYED_SHA" > "$KSKILL_PROXY_DEPLOYED_SHA_FILE"
}

main() {
  load_config

  if [[ "${1:-}" == "--rollback" ]]; then
    rollback
    exit 0
  fi

  command -v docker >/dev/null 2>&1 || fail "docker is required"
  docker info >/dev/null 2>&1 || fail "docker daemon is required; Docker access is production secret access"

  local sha image current_sha
  sha="$(resolve_sha)"
  image="${KSKILL_PROXY_IMAGE_NAME}:${sha}"
  current_sha="$(cat "$KSKILL_PROXY_DEPLOYED_SHA_FILE" 2>/dev/null || true)"

  if [[ "$sha" == "$current_sha" ]]; then
    log "already deployed: $sha"
    exit 0
  fi

  log "deploying explicit target SHA: $sha"
  record_rollback_state
  checkout_resolved_sha "$sha"

  cd "$KSKILL_PROXY_REPO_DIR"
  docker build -f packages/k-skill-proxy/Dockerfile -t "$image" .

  start_container "$KSKILL_PROXY_CANDIDATE_NAME" "$KSKILL_PROXY_CANDIDATE_PORT" "$image"
  health_check "http://127.0.0.1:${KSKILL_PROXY_CANDIDATE_PORT}/health"

  start_container "$KSKILL_PROXY_CONTAINER_NAME" "$KSKILL_PROXY_HOST_PORT" "$image"
  health_check "http://127.0.0.1:${KSKILL_PROXY_HOST_PORT}/health"

  if ! health_check "${KSKILL_PROXY_PUBLIC_BASE_URL%/}/health"; then
    log "public health failed; attempting rollback"
    rollback || true
    exit 1
  fi

  if ! public_route_smoke; then
    log "public route smoke failed; attempting rollback"
    rollback || true
    exit 1
  fi

  printf '%s\n' "$sha" > "$KSKILL_PROXY_DEPLOYED_SHA_FILE"
  docker rm -f "$KSKILL_PROXY_CANDIDATE_NAME" >/dev/null 2>&1 || true
  log "deploy complete: $sha"
}

main "$@"
