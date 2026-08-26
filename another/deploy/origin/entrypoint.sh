#!/bin/sh
set -eu
if [ "${ANOTHER_RUN_XHTTP:-}" = "1" ]; then
  xhttp-origin &
fi
if [ "${ANOTHER_RUN_REALITY:-}" = "1" ]; then
  reality-origin &
fi
exec python -m another_admin.api
