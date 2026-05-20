#!/bin/bash

# Paths
DATA_DIR="/Users/shantanu/Downloads/CodeProjects/AGENTIC_AI_PROJECTS/uk-job-search-agent/data"
S3_PATH="s3://svc-s3-dev-632943041262-modelartifact/uk-work-search-agent/data/latest_jobs_history.csv"

# Create data directory if it doesn't exist
mkdir -p "$DATA_DIR"

# Download only if file exists in S3 (no manual intervention)
aws s3 cp "$S3_PATH" "$DATA_DIR/jobs_history.csv" --only-show-errors

if [ $? -eq 0 ]; then
    echo "$(date): ✅ CSV synced successfully" >> "$DATA_DIR/sync.log"
else
    echo "$(date): ⚠️ No new CSV found" >> "$DATA_DIR/sync.log"
fi