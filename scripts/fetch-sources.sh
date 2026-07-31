#!/bin/sh
set -eu
POSIXLY_CORRECT='no bashing shell'

##
# ${*} = message to print to stderr
# returns: 0
error() {
  : "error(msg='${*}')"
  echo "error: ${*}" >&2
}

##
# ${*} = fatal message
# returns: does not return (exits 1)
die() {
  : "die(msg='${*}')"
  error "${*}"
  exit 1
}

##
# ${1} = name (local directory name under sources/)
# ${2} = url (git clone URL)
# returns: 0 on success, dies on failure
fetch_repo() {
  : "fetch_repo(name='${1}', url='${2}')"
  _dest="${SOURCES_DIR}/${1}"

  if test -d "${_dest}/.git"; then
    echo "Updating ${1}..."
    git -C "${_dest}" fetch --all --prune
    git -C "${_dest}" reset --hard origin/HEAD 2>/dev/null ||
      git -C "${_dest}" reset --hard origin/main 2>/dev/null ||
      git -C "${_dest}" reset --hard origin/master ||
      die "failed to reset ${1}"
  else
    echo "Cloning ${1}..."
    git clone --depth 1 "${2}" "${_dest}" || die "failed to clone ${1}"
  fi

  unset _dest
}

# Resolve sources directory relative to this script
SCRIPT_DIR="$(cd "$(dirname "${0}")" && pwd)"
SOURCES_DIR="${SCRIPT_DIR}/../sources"
mkdir -p "${SOURCES_DIR}"

# Fetch all source repositories
fetch_repo protondrive-sdk 'https://github.com/ProtonDriveApps/sdk.git'
fetch_repo webclient       'https://github.com/ProtonMail/WebClients.git'
fetch_repo go-proton-api   'https://github.com/ProtonMail/go-proton-api.git'
fetch_repo proton-bridge   'https://github.com/ProtonMail/proton-bridge.git'

echo 'All sources fetched.'

unset SCRIPT_DIR SOURCES_DIR
