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

# Resolve directories relative to this script
SCRIPT_DIR="$(cd "$(dirname "${0}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}/.."
SOURCES_DIR="${PROJECT_DIR}/sources"
PYTHON="${PROJECT_DIR}/.venv/bin/python"

mkdir -p "${SOURCES_DIR}"

# Read enabled sources from config
test -x "${PYTHON}" || die "venv not set up — run make first"

"${PYTHON}" -m src.config urls | while read -r _name _url; do
  fetch_repo "${_name}" "${_url}"
done
unset _name _url

echo 'All sources fetched.'

unset SCRIPT_DIR PROJECT_DIR SOURCES_DIR PYTHON
