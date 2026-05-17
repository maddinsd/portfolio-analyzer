#!/bin/bash
# Run before deploying to Vercel to sync pipeline files from the project root.
# Usage: bash web/sync_pipeline.sh  (from project root)
#        or just: make deploy
set -e
cd "$(dirname "$0")"

PIPELINE_FILES="fetcher.py analyzer.py reporter.py excel.py dcf.py research.py \
  competitive.py analyst_coverage.py transcript_parser.py sec_parser.py \
  insider_tracker.py pitch.py report_pdf.py utils.py"

for f in $PIPELINE_FILES; do
  if [ -f "../$f" ]; then
    cp "../$f" "./$f"
    echo "Synced $f"
  fi
done

# Copy directory contents (trailing slash) so re-runs don't nest directories
cp -r ../education/. ./education/
cp -r ../assets/.    ./assets/
cp ../lbo/lbo_engine.py  ./lbo/lbo_engine.py
cp ../lbo/lbo_excel.py   ./lbo/lbo_excel.py
cp ../lbo/lbo_fetcher.py ./lbo/lbo_fetcher.py
cp ../lbo/lbo_model.py   ./lbo/lbo_model.py
cp ../ma/ma_engine.py    ./ma/ma_engine.py
cp ../ma/ma_excel.py     ./ma/ma_excel.py
cp ../ma/ma_fetcher.py   ./ma/ma_fetcher.py
cp ../ma/ma_model.py     ./ma/ma_model.py

echo "Sync complete — $(date)"
