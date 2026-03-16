#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: deploy-web.sh <prod|dev|status>

prod   Update /root/daily-learner from origin/main and restart daily-learner-web.service
dev    Update /root/daily-learner-dev from origin/learn-dev and restart daily-learner-web-dev.service
status Show branch, commit, and service status for both environments
EOF
}

deploy_env() {
  local name="$1"
  local workdir branch service

  case "$name" in
    prod)
      workdir="/root/daily-learner"
      branch="main"
      service="daily-learner-web.service"
      ;;
    dev)
      workdir="/root/daily-learner-dev"
      branch="learn-dev"
      service="daily-learner-web-dev.service"
      ;;
    *)
      echo "Unknown environment: $name" >&2
      exit 1
      ;;
  esac

  git -C "$workdir" fetch origin "$branch"
  git -C "$workdir" checkout "$branch"
  git -C "$workdir" pull --ff-only origin "$branch"
  systemctl restart "$service"
  echo "$name deployed: $(git -C "$workdir" rev-parse --short HEAD)"
}

status_env() {
  local name="$1"
  local workdir branch service

  case "$name" in
    prod)
      workdir="/root/daily-learner"
      branch="main"
      service="daily-learner-web.service"
      ;;
    dev)
      workdir="/root/daily-learner-dev"
      branch="learn-dev"
      service="daily-learner-web-dev.service"
      ;;
    *)
      echo "Unknown environment: $name" >&2
      exit 1
      ;;
  esac

  echo "[$name]"
  echo "  workdir: $workdir"
  echo "  branch:  $(git -C "$workdir" branch --show-current)"
  echo "  commit:  $(git -C "$workdir" rev-parse --short HEAD)"
  echo "  remote:  $(git -C "$workdir" rev-parse --short "origin/$branch" 2>/dev/null || echo 'missing')"
  echo "  service: $(systemctl is-active "$service")"
}

main() {
  local target="${1:-}"

  case "$target" in
    prod|dev)
      deploy_env "$target"
      ;;
    status)
      status_env prod
      status_env dev
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
