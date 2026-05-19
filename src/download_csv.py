#!/usr/bin/env python3
"""
Download jobs_history.csv from GitHub Actions artifacts
"""

import os
import zipfile
import requests
from pathlib import Path

# GitHub configuration
REPO_OWNER = "taniShant"  # Change this
REPO_NAME = "uk-job-search-agent"          # Change this
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")  # Optional but recommended

def download_latest_artifact():
    """Download the latest jobs-history artifact"""
    
    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    
    # Get latest workflow run
    runs_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs"
    response = requests.get(runs_url, headers=headers)
    
    if response.status_code != 200:
        print(f"❌ Failed to get runs: {response.status_code}")
        return False
    
    runs = response.json().get("workflow_runs", [])
    if not runs:
        print("❌ No workflow runs found")
        return False
    
    # Find latest run with artifact
    for run in runs:
        run_id = run["id"]
        artifacts_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs/{run_id}/artifacts"
        artifacts_response = requests.get(artifacts_url, headers=headers)
        
        if artifacts_response.status_code == 200:
            artifacts = artifacts_response.json().get("artifacts", [])
            for artifact in artifacts:
                if artifact["name"] == "jobs-history":
                    # Download the artifact
                    download_url = artifact["archive_download_url"]
                    print(f"✅ Found artifact from run {run_id}")
                    
                    # Download zip
                    zip_response = requests.get(download_url, headers=headers)
                    if zip_response.status_code == 200:
                        zip_path = "jobs-history.zip"
                        with open(zip_path, "wb") as f:
                            f.write(zip_response.content)
                        
                        # Extract CSV
                        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                            zip_ref.extractall(".")
                            print(f"✅ Extracted jobs_history.csv to {os.getcwd()}")
                        
                        # Clean up
                        os.remove(zip_path)
                        return True
                    else:
                        print(f"❌ Failed to download: {zip_response.status_code}")
                        return False
    
    print("❌ No jobs-history artifact found")
    return False

if __name__ == "__main__":
    download_latest_artifact()