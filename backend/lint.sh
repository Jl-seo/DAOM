#!/bin/bash
# Run static analysis on backend code
# Checks for:
# F821: Undefined name (variable used but not defined)
# E999: Syntax Error
echo "Running flake8 static analysis..."
flake8 app/services --select=F821,E999 --show-source
if [ $? -eq 0 ]; then
    echo "✅ No critical errors found!"
else
    echo "❌ Critical errors detected!"
    exit 1
fi
