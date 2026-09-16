#!/usr/bin/env bash
# Regenerates the committed catalogue and its upstream pin from a checkout.
#
# This script exists to be the only place the generator's arguments are written
# down. The catalogue is restricted to the templates this project has actually
# ported; run without that restriction it grows from 491 rows to 2140, adding a
# disabled row for every one of the ~900 extensions on templates nothing here
# reads. Both outputs are legitimate, which is exactly the problem: a CI guard
# that regenerated with different arguments than the commit it checks would
# report a difference that says nothing about the change under review.
set -euo pipefail

repo="${1:?usage: regenerate_catalogue.sh <path to a tachiyomi-extensions checkout>}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Kept in step with SUPPORTED_TEMPLATES in gen_catalogue.py. They are separate
# because the generator may be pointed at anything, while the committed
# catalogue covers one specific set.
TEMPLATES="madara,mangathemesia,madaralegacy,zeistmanga,comiciviewer,keyoapp,iken"

exec "${PYTHON:-python3}" "$here/gen_catalogue.py" \
  --repo "$repo" \
  --templates "$TEMPLATES" \
  --report
