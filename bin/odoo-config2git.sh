#!/bin/bash

set -e
set -u
set -o pipefail

#set -x

CONFIG_DIR="${HOME}/.config/odoo-cli/"
ODOOS="staging production"
TARGET_DIR="${HOME}/git/odoo-config"
GIT="git -C ${TARGET_DIR}"
LANG=C.utf8
SCRIPT_DIR="$(dirname $(readlink -f "${BASH_SOURCE[0]}"))"

error()
{
  echo "ERROR: $@" >&2
}

dump2git()
{
  INSTANCE="$1"
  CONFIGFILE="${CONFIG_DIR}/$INSTANCE.conf"
  if ! [ -r "$CONFIGFILE" ]; then
    error "failed to read config file '$CONFIGFILE' for instance '$INSTANCE'"
    return 1
  fi
  $GIT branch $INSTANCE 2>/dev/null || true
  $GIT checkout $INSTANCE
  $GIT reset --hard origin/$INSTANCE
  rm ${TARGET_DIR}/*
  if ! ${SCRIPT_DIR}/odoo-cli -c ${CONFIGFILE} config-dump --output-directory ${TARGET_DIR} --json; then
    error "failed to run 'odoo-cli -c ${CONFIGFILE} config-dump'"
    return 1
  fi
  $GIT add --all
  if $GIT commit -m "auto-update" --no-gpg-sign; then
    $GIT push -u origin $INSTANCE
  fi
}

#
# main
#
test -d "${CONFIG_DIR}"
test -d "${TARGET_DIR}"
$GIT fetch origin
SUCCESS=()
FAILED=()
for i in $ODOOS; do
  if dump2git "$i"; then
    SUCCESS+=("$i")
  else
    FAILED+=("$i")
  fi
done

if [ ${#FAILED[@]} -ge 1 ]; then
  error "failed for ${FAILED[@]}"
fi

exit 0
