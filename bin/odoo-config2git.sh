#!/bin/bash

set -e
set -u
set -o pipefail

#set -x

ODOOS="dev-joergs-local staging production"
TARGET_DIR="/home/joergs/git/bareos/extra/odoo-config"
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
  CONFIGFILE="${SCRIPT_DIR}/odoo_api-$INSTANCE.conf"
  if ! [ -r "$CONFIGFILE" ]; then
    error "failed to read config file '$CONFIGFILE' for instance '$INSTANCE'"
    return 1
  fi
  $GIT branch $INSTANCE 2>/dev/null || true
  $GIT checkout $INSTANCE
  $GIT reset --hard origin/$INSTANCE
  rm ${TARGET_DIR}/*
  if ! ${SCRIPT_DIR}/odoo_api.py -c ${CONFIGFILE} config-dump --output-directory ${TARGET_DIR} --json; then
    error "failed to run 'odoo_api.py -c ${CONFIGFILE} config-dump'"
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
