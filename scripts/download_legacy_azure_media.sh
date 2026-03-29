#!/usr/bin/env bash

set -euo pipefail

MODE="${1:-all}"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-kvarteret1}"
STORAGE_ACCOUNT="${AZURE_STORAGE_ACCOUNT:-personaldatabasen}"
WEBAPP_NAME="${AZURE_WEBAPP_NAME:-personaldatabasen-api}"
OUTPUT_ROOT="${OUTPUT_ROOT:-data}"
IMAGES_DIR="${OUTPUT_ROOT}/legacy-images"
PERSONAL_FIL_DIR="${OUTPUT_ROOT}/legacy-personal-fil"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

usage() {
  cat <<'EOF'
Usage:
  scripts/download_legacy_azure_media.sh [all|images|personal-fil]

Environment overrides:
  AZURE_RESOURCE_GROUP
  AZURE_STORAGE_ACCOUNT
  AZURE_WEBAPP_NAME
  OUTPUT_ROOT
EOF
}

generate_expiry() {
  python3 - <<'PY'
from datetime import datetime, timedelta, timezone
print((datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%MZ"))
PY
}

download_images() {
  require_cmd az
  require_cmd azcopy

  mkdir -p "${IMAGES_DIR}"

  local account_key
  local expiry
  local sas

  account_key="$(az storage account keys list \
    --resource-group "${RESOURCE_GROUP}" \
    --account-name "${STORAGE_ACCOUNT}" \
    --query '[0].value' \
    --output tsv)"

  expiry="$(generate_expiry)"

  sas="$(az storage container generate-sas \
    --account-name "${STORAGE_ACCOUNT}" \
    --account-key "${account_key}" \
    --name images \
    --permissions rl \
    --expiry "${expiry}" \
    --output tsv)"

  echo "Downloading Azure Blob images container into ${IMAGES_DIR}"
  azcopy copy \
    "https://${STORAGE_ACCOUNT}.blob.core.windows.net/images?${sas}" \
    "${IMAGES_DIR}" \
    --recursive \
    --overwrite=ifSourceNewer
}

download_personal_fil() {
  require_cmd az
  require_cmd python3

  mkdir -p "${PERSONAL_FIL_DIR}"

  local profile_json
  profile_json="$(mktemp)"
  trap 'rm -f "${profile_json}"' RETURN

  az webapp deployment list-publishing-profiles \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${WEBAPP_NAME}" \
    --output json > "${profile_json}"

  PROFILE_JSON="${profile_json}" PERSONAL_FIL_DIR="${PERSONAL_FIL_DIR}" WEBAPP_NAME="${WEBAPP_NAME}" python3 - <<'PY'
import base64
import json
import os
import pathlib
import urllib.request
import zipfile

profile_path = pathlib.Path(os.environ["PROFILE_JSON"])
personal_fil_dir = pathlib.Path(os.environ["PERSONAL_FIL_DIR"])
webapp_name = os.environ["WEBAPP_NAME"]

profiles = json.loads(profile_path.read_text())
profile = next(
    item for item in profiles if item["publishMethod"] in {"MSDeploy", "ZipDeploy"}
)
auth = base64.b64encode(
    f'{profile["userName"]}:{profile["userPWD"]}'.encode("utf-8")
).decode("ascii")

zip_path = personal_fil_dir / "files.zip"
url = f"https://{webapp_name}.scm.azurewebsites.net/api/zip/site/wwwroot/files/"
request = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"})

with urllib.request.urlopen(request, timeout=600) as response, zip_path.open("wb") as handle:
    while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
            break
        handle.write(chunk)

extract_dir = personal_fil_dir / "extracted"
extract_dir.mkdir(parents=True, exist_ok=True)

with zipfile.ZipFile(zip_path) as archive:
    archive.extractall(extract_dir)
    file_entries = [info for info in archive.infolist() if not info.is_dir()]

print(f"Saved {zip_path}")
print(f"Extracted to {extract_dir}")
print(f"Recovered personal_fil file count: {len(file_entries)}")
if not file_entries:
    print("The current App Service files directory is empty.")
PY
}

case "${MODE}" in
  all)
    download_images
    download_personal_fil
    ;;
  images)
    download_images
    ;;
  personal-fil)
    download_personal_fil
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
