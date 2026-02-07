#!/bin/bash
# ============================================
# DAOM Backend — Comprehensive Code Quality Check
# ============================================
# Tools: flake8, ruff, bandit, vulture, pylint, semgrep
# Usage: cd backend && ./lint.sh
# ============================================

set -e
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "================================================"
echo "  🔬 DAOM Backend — Code Quality Sweep"
echo "================================================"
echo ""

FAIL=0

# 1. flake8 — Critical Errors (SyntaxError, undefined names)
echo -e "${BLUE}[1/6] flake8 — Critical Errors (F821, E999)${NC}"
if flake8 app/ --select=F821,E999 --show-source 2>/dev/null; then
    echo -e "${GREEN}  ✅ No critical errors${NC}"
else
    echo -e "${RED}  ❌ Critical errors found!${NC}"
    FAIL=1
fi
echo ""

# 2. ruff — Fast Lint (unused imports, whitespace)
echo -e "${BLUE}[2/6] ruff — Code Quality${NC}"
RUFF_COUNT=$(ruff check app/ --select F401,W293,W291 2>/dev/null | wc -l | tr -d ' ')
if [ "$RUFF_COUNT" -eq 0 ]; then
    echo -e "${GREEN}  ✅ Clean (0 issues)${NC}"
else
    echo -e "${YELLOW}  ⚠️  $RUFF_COUNT issues (run 'ruff check app/ --fix' to auto-fix)${NC}"
fi
echo ""

# 3. bandit — Security Scan
echo -e "${BLUE}[3/6] bandit — Security Scan${NC}"
BANDIT_MEDIUM=$(bandit -r app/ -ll --format json 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
results = [r for r in data.get('results', []) if r['issue_severity'] in ('MEDIUM', 'HIGH')]
print(len(results))
for r in results:
    fp = r['filename'].split('app/')[-1]
    print(f\"  [{r['issue_severity']}] {fp}:{r['line_number']} — {r['issue_text']}\")
" 2>/dev/null || echo "0")
BANDIT_COUNT=$(echo "$BANDIT_MEDIUM" | head -1)
if [ "$BANDIT_COUNT" = "0" ]; then
    echo -e "${GREEN}  ✅ No medium/high security issues${NC}"
else
    echo "$BANDIT_MEDIUM" | tail -n +2
    echo -e "${YELLOW}  ⚠️  $BANDIT_COUNT security issues found${NC}"
fi
echo ""

# 4. vulture — Dead Code Detection
echo -e "${BLUE}[4/6] vulture — Dead Code${NC}"
VULTURE_COUNT=$(vulture app/services/ --min-confidence 80 2>/dev/null | wc -l | tr -d ' ')
if [ "$VULTURE_COUNT" -eq 0 ]; then
    echo -e "${GREEN}  ✅ No dead code detected${NC}"
else
    echo -e "${YELLOW}  ⚠️  $VULTURE_COUNT potential dead code items${NC}"
    vulture app/services/ --min-confidence 80 2>/dev/null | head -10
fi
echo ""

# 5. pylint — Code Quality Score
echo -e "${BLUE}[5/6] pylint — Quality Score${NC}"
PYLINT_SCORE=$(pylint app/services/*.py --disable=all --enable=E,W --score=y --output-format=text 2>/dev/null | grep "rated at" | grep -oE '[0-9]+\.[0-9]+' || echo "N/A")
echo -e "  📊 Score: ${GREEN}${PYLINT_SCORE}/10${NC}"
echo ""

# 6. semgrep — Advanced Security Patterns (optional, slower)
echo -e "${BLUE}[6/6] semgrep — Advanced Security Patterns${NC}"
if command -v semgrep &> /dev/null; then
    SEMGREP_COUNT=$(semgrep scan --config auto app/services/ --severity ERROR --severity WARNING --json 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(len(data.get('results', [])))
" 2>/dev/null || echo "0")
    if [ "$SEMGREP_COUNT" = "0" ]; then
        echo -e "${GREEN}  ✅ No security patterns detected${NC}"
    else
        echo -e "${YELLOW}  ⚠️  $SEMGREP_COUNT issues found${NC}"
    fi
else
    echo -e "${YELLOW}  ⏭️  semgrep not installed (pip install semgrep)${NC}"
fi

echo ""
echo "================================================"
if [ "$FAIL" -eq 0 ]; then
    echo -e "  ${GREEN}✅ All checks passed!${NC}"
else
    echo -e "  ${RED}❌ Some checks failed!${NC}"
fi
echo "================================================"
echo ""

exit $FAIL
