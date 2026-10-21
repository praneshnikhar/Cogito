#!/usr/bin/env bash
# Regenerate the .docx (and .txt) versions of the documents from their
# markdown masters. Edit the .md files, then run:  bash docs/build-docx.sh
set -euo pipefail
cd "$(dirname "$0")"

pandoc -f markdown-tex_math_dollars PROJECT_REPORT.md -o PROJECT_REPORT.docx \
  --toc --toc-depth=2 --resource-path=.
pandoc -f markdown-tex_math_dollars PROJECT_REPORT.md -t plain --wrap=none \
  --columns=110 -o PROJECT_REPORT.txt

pandoc -f markdown-tex_math_dollars DATABASE.md -o DATABASE.docx \
  --toc --toc-depth=1 --resource-path=.
pandoc -f markdown-tex_math_dollars DATABASE.md -t plain --wrap=none \
  --columns=110 -o DATABASE.txt

echo "regenerated: PROJECT_REPORT.docx/.txt, DATABASE.docx/.txt"
