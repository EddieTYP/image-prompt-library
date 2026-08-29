#!/usr/bin/env bash

# Read installer-owned .env values as literal data. Never evaluate file content.
image_prompt_library_load_env_file() {
  local env_file="$1" line key value
  [ -f "$env_file" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in ""|'#'*) continue ;; esac
    case "$line" in *=*) ;; *) continue ;; esac
    key="${line%%=*}"
    value="${line#*=}"
    case "$key" in
      IMAGE_PROMPT_LIBRARY_PATH|IMAGE_PROMPT_LIBRARY_AUTH_PATH|IMAGE_PROMPT_LIBRARY_CONFIG_PATH|XAI_API_KEY|BACKEND_HOST|BACKEND_PORT|FRONTEND_PORT|BACKUP_DIR)
        printf -v "$key" '%s' "$value"
        export "$key"
        ;;
    esac
  done < "$env_file"
}
