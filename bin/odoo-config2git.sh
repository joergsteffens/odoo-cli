#!/bin/bash

set -e
set -u
set -o pipefail

#set -x

ODOOS="dev-joergs-local staging production"
TARGET_DIR="/home/joergs/git/bareos/extra/odoo-config"
GIT="git -C ${TARGET_DIR}"
LANG=C
SCRIPT_DIR="$(dirname $(readlink -f "${BASH_SOURCE[0]}"))"

error()
{
  echo "ERROR: $@" >&2
}

dump2git()
{
  INSTANCE="$1"
  CONFIGFILE="${SCRIPT_DIR}/odoo-api-$INSTANCE.conf"
  if ! [ -r "$CONFIGFILE" ]; then
    error "failed to read config file '$CONFIGFILE' for instance '$INSTANCE'"
    exit 1
  fi
  $GIT branch $INSTANCE 2>/dev/null || true
  $GIT checkout $INSTANCE
  $GIT reset --hard origin/$INSTANCE
  rm ${TARGET_DIR}/*
  ${SCRIPT_DIR}/odoo-api.py -c ${CONFIGFILE} config-dump --output-directory ${TARGET_DIR} --json
  $GIT add --all
  if $GIT commit -m "auto-update" --no-gpg-sign; then
    $GIT push -u origin $INSTANCE
  fi
}

$GIT fetch origin
for i in $ODOOS; do
  dump2git "$i"
done
