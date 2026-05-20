#!/usr/bin/env python3
"""
UK Job Search Agent - Finds £120k-150k tech jobs in UK and emails daily digest
Now with CSV-based persistence + deduplication
"""

import os, sys, re
import json
import time
import smtplib
import csv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict
from dotenv import load_dotenv

from strands import Agent, tool
from tavily import TavilyClient

# Load environment variables
load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
YOUR_EMAIL = "shantanu.bsa@gmail.com"
YOUR_EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

TARGET_ROLES = [
    "AI Engineer", "Data Engineer", "Data Scientist", "AI Strategist",
    "Cloud Architect", "Lead Architect", "Solutions Architect",
    "Head of AI", "Principal Data Engineer", "ML Engineer"
]

SALARY_MIN = 120000
SALARY_MAX = 150000
LOCATION = "United Kingdom"

# CSV file for persistence
JOBS_FILE = os.path.join(os.getcwd(), "jobs_history.csv")

# ============================================================
# CSV DEDUPLICATION SYSTEM
# ============================================================

def load_existing_jobs() -> Dict[str, Dict]:
    """Load existing jobs from CSV (keyed by apply_url)"""
    existing = {}

    if not os.path.exists(JOBS_FILE):
        return existing

    with open(JOBS_FILE, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # for row in reader:
        #     existing[row["apply_url"]] = row

        for row in reader:
            # Create key from title and company
            key = f"{row.get('title', '').lower()}|{row.get('company', '').lower()}"
            existing[key] = row

    return existing

def get_job_key(job: Dict) -> str:
    """
    Create a unique key for a job using title + company (more reliable than URL)
    """
    title = job.get("title", "").lower().strip()
    company = job.get("company", "").lower().strip()
    return f"{title}|{company}"

def filter_new_jobs(jobs: List[Dict], existing: Dict[str, Dict]) -> List[Dict]:
    """Return only new jobs not already in CSV"""
    new_jobs = []

    for job in jobs:
        key = get_job_key(job)
        if key not in existing:
            new_jobs.append(job)
        else:
            print(f"⏭️ Duplicate found: {job.get('title')} at {job.get('company')}")

        # url = job.get("apply_url")
        # if url and url not in existing:
        #     new_jobs.append(job)

    return new_jobs


def append_jobs_to_csv(jobs: List[Dict]):
    """Append new jobs to CSV history file"""
    if not jobs:
        return

    file_exists = os.path.exists(JOBS_FILE)

    with open(JOBS_FILE, mode="a", newline="", encoding="utf-8") as f:
        fieldnames = [
            "title",
            "company",
            "location",
            "salary_range",
            "apply_url",
            "source",
            "posted_date",
            "first_seen_date",
            "job_key"
        ]

        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        for job in jobs:
            writer.writerow({
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "location": job.get("location", ""),
                "salary_range": job.get("salary_range", ""),
                "apply_url": job.get("apply_url", ""),
                "source": job.get("source", ""),
                "posted_date": job.get("posted_date", ""),
                "first_seen_date": datetime.now().isoformat(),
                "job_key": get_job_key(job)
            })

# ============================================================
# TOOL 1: LinkedIn Jobs
# ============================================================
def extract_linkedin_posted_date(text: str) -> str:
    """Extract the date string from LinkedIn job posting"""
    # Pattern matches: "4 days ago", "2 weeks ago", "1 month ago", "a week ago"
    patterns = [
        r'(\d+)\s+(day|days|week|weeks|month|months)\s+ago',
        r'a\s+(week|month)\s+ago'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            return match.group(0)
    return ""

def parse_linkedin_date(date_text: str) -> tuple:
    """
    Parse LinkedIn date strings like:
    - "4 days ago" -> (True, 4, "4 days ago")
    - "2 weeks ago" -> (False, 14, "2 weeks ago")
    - "1 month ago" -> (False, 30, "1 month ago")
    - "a week ago" -> (True, 7, "1 week ago")
    - "" -> (True, 0, "Date not specified")
    
    Returns (is_recent: bool, days_old: int, cleaned_date: str)
    """
    if not date_text:
        return (True, 0, "Date not specified")
    
    date_text_lower = date_text.lower()
    
    # Handle "a week ago" or "a month ago"
    if date_text_lower == "a week ago":
        return (True, 7, "1 week ago")
    if date_text_lower == "a month ago":
        return (False, 30, "1 month ago")
    
    # Handle "X days/weeks/months ago"
    match = re.search(r'(\d+)\s+(day|days|week|weeks|month|months)\s+ago', date_text_lower)
    
    if match:
        number = int(match.group(1))
        unit = match.group(2)
        
        # Convert to days
        if 'day' in unit:
            days_old = number
        elif 'week' in unit:
            days_old = number * 7
        elif 'month' in unit:
            days_old = number * 30
        else:
            days_old = 0
        
        # Check if within 7 days
        is_recent = days_old <= 7
        
        # Clean up the date text (e.g., "days" -> "day" for consistency)
        if 'days' in unit and number == 1:
            unit = 'day'
        elif 'weeks' in unit and number == 1:
            unit = 'week'
        elif 'months' in unit and number == 1:
            unit = 'month'
        
        cleaned_date = f"{number} {unit} ago"
        return (is_recent, days_old, cleaned_date)
    
    return (True, 0, date_text)

@tool
def search_linkedin_jobs(role: str) -> List[Dict]:
    client = TavilyClient(api_key=TAVILY_API_KEY)
    query = f'site:linkedin.com/jobs "{role}" "{LOCATION}" {SALARY_MIN} {SALARY_MAX}'

    try:
        results = client.search(query, max_results=10)

        jobs = []
        for r in results.get("results", []):
            title = r.get("title", role)
            content = r.get("content", "")
            url = r.get("url", "")
            
            # Extract the actual posted date from LinkedIn
            full_text = f"{title} {content}"
            posted_date_raw = extract_linkedin_posted_date(full_text)
            
            # Parse the date and check if recent
            is_recent, days_old, cleaned_date = parse_linkedin_date(posted_date_raw)
            
            if not is_recent:
                print(f"⏭️ Skipping old LinkedIn job: {title} - {cleaned_date} ({days_old} days old)")
                continue  # Skip this job entirely
            
            jobs.append({
                "title": title,
                "company": extract_company_from_url(url),
                "location": LOCATION,
                "salary_range": f"£{SALARY_MIN:,} - £{SALARY_MAX:,}",
                "apply_url": url,
                "source": "LinkedIn",
                "posted_date": cleaned_date  # Store like "4 days ago" or "1 month ago"
            })

        time.sleep(1)
        return jobs

    except Exception as e:
        print("LinkedIn error:", e)
        return []
    
def extract_company_from_url(url: str) -> str:
    parts = url.split("/")
    if "company" in parts:
        i = parts.index("company")
        if i + 1 < len(parts):
            return parts[i + 1].replace("-", " ").title()
    return "Unknown"

# ============================================================
# TOOL 2: CWJobs
# ============================================================

@tool
def search_cwjobs(role: str) -> List[Dict]:
    client = TavilyClient(api_key=TAVILY_API_KEY)
    query = f'site:cwjobs.co.uk "{role}" {SALARY_MIN//1000}k {SALARY_MAX//1000}k'

    try:
        results = client.search(query, max_results=10)

        jobs = []
        for r in results.get("results", []):
            jobs.append({
                "title": r.get("title", role),
                "company": extract_domain(r.get("url", "")),
                "location": LOCATION,
                "salary_range": f"£{SALARY_MIN:,} - £{SALARY_MAX:,}",
                "apply_url": r.get("url", ""),
                "source": "CWJobs",
                "posted_date": datetime.now().strftime("%Y-%m-%d")
            })
        time.sleep(1)
        return jobs

    except Exception as e:
        print("CWJobs error:", e)
        return []


def extract_domain(url: str) -> str:
    import re
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1).split(".")[0].title() if m else "Unknown"

# ============================================================
# TOOL 3: General Jobs
# ============================================================

@tool
def search_general_jobs(role: str) -> List[Dict]:
    client = TavilyClient(api_key=TAVILY_API_KEY)
    query = f'"{role}" jobs {LOCATION} {SALARY_MIN} to {SALARY_MAX}'

    try:
        results = client.search(query, max_results=15)

        jobs = []
        for r in results.get("results", []):
            title = r.get("title", "").lower()
            if any(role.lower() in title for role in TARGET_ROLES):
                jobs.append({
                    "title": r.get("title", role),
                    "company": extract_domain(r.get("url", "")),
                    "location": LOCATION,
                    "salary_range": f"£{SALARY_MIN:,} - £{SALARY_MAX:,}",
                    "apply_url": r.get("url", ""),
                    "source": "General",
                    "posted_date": datetime.now().strftime("%Y-%m-%d")
                })
        time.sleep(1)
        return jobs

    except Exception as e:
        print("General search error:", e)
        return []

# ============================================================
# TOOL 4: SEND EMAIL + CSV DEDUPE
# ============================================================

@tool
def send_job_digest(jobs: List[Dict], recipient: str) -> str:
    """
    Beautiful HTML email + CSV-based deduplication (single source of truth)
    """

    if not jobs:
        return send_no_jobs_email(recipient) 

    
    # ============================================================
    # 1. LOAD EXISTING JOBS FROM CSV
    # ============================================================
    existing = load_existing_jobs()

    # ============================================================
    # 2. FILTER ONLY NEW JOBS
    # ============================================================
    new_jobs = filter_new_jobs(jobs, existing)

    if not new_jobs:
        return f"No new jobs today (all {len(jobs)} already in history)"

    # ============================================================
    # 3. SAVE NEW JOBS TO CSV (IMPORTANT: BEFORE EMAIL)
    # ============================================================
    append_jobs_to_csv(new_jobs)

    # ============================================================
    # 4. BEAUTIFUL EMAIL TEMPLATE (YOUR ORIGINAL STYLE)
    # ============================================================
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                background-color: #f4f6f9;
            }}
            .container {{
                max-width: 850px;
                margin: 0 auto;
                padding: 20px;
            }}
            h1 {{
                color: #2c3e50;
                border-bottom: 2px solid #3498db;
                padding-bottom: 10px;
            }}
            h2 {{
                color: #34495e;
            }}
            .summary {{
                background: #ffffff;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 20px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.08);
            }}
            .job {{
                background: #ffffff;
                border-left: 5px solid #3498db;
                padding: 15px;
                margin: 15px 0;
                border-radius: 6px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.05);
            }}
            .job-title {{
                font-size: 18px;
                font-weight: bold;
                color: #2c3e50;
            }}
            .company {{
                color: #7f8c8d;
                margin-top: 5px;
            }}
            .salary {{
                color: #27ae60;
                font-weight: bold;
            }}
            .location {{
                color: #7f8c8d;
            }}
            .apply-link a {{
                display: inline-block;
                margin-top: 10px;
                background: #3498db;
                color: white;
                padding: 8px 14px;
                text-decoration: none;
                border-radius: 5px;
            }}
            .apply-link a:hover {{
                background: #2980b9;
            }}
            .footer {{
                margin-top: 30px;
                font-size: 12px;
                color: #95a5a6;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="container">

            <h1>🎯 UK Tech Jobs Digest</h1>

            <div class="summary">
                <h2>Today's Summary</h2>
                <p><b>{len(new_jobs)}</b> new high-paying roles found</p>
                <p>💰 Salary: £{SALARY_MIN:,} - £{SALARY_MAX:,}</p>
                <p>📍 Location: {LOCATION}</p>
                <p>💼 Roles: {', '.join(TARGET_ROLES[:5])} ...</p>
            </div>
    """

    # ============================================================
    # 5. JOB CARDS (BEAUTIFUL LOOP)
    # ============================================================
    for job in new_jobs:
        html_content += f"""
            <div class="job">
                <div class="job-title">{job.get('title', 'Role Available')}</div>
                <div class="company">🏢 {job.get('company', 'Unknown Company')}</div>
                <div class="location">📍 {job.get('location', LOCATION)}</div>
                <div class="salary">💰 {job.get('salary_range', 'Not disclosed')}</div>

                <div class="apply-link">
                    <a href="{job.get('apply_url', '#')}">🔗 View & Apply</a>
                </div>

                <small style="color:#95a5a6;">
                    Source: {job.get('source', 'Job Board')} |
                    Found: {job.get('posted_date', 'Today')}
                </small>
            </div>
        """

    # ============================================================
    # 6. FOOTER
    # ============================================================
    html_content += f"""
            <div class="footer">
                <p>Automated UK Job Search Agent</p>
                <p>Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                <p>No duplicate jobs will be sent again (CSV dedup enabled)</p>
            </div>

        </div>
    </body>
    </html>
    """

    # ============================================================
    # 7. SEND EMAIL
    # ============================================================
    try:
        msg = MIMEMultipart()
        msg["From"] = YOUR_EMAIL
        msg["To"] = recipient
        msg["Subject"] = f"🎯 {len(new_jobs)} New UK Tech Jobs (£{SALARY_MIN//1000}k-£{SALARY_MAX//1000}k)"

        msg.attach(MIMEText(html_content, "html"))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(YOUR_EMAIL, YOUR_EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()

        return f"✅ Sent {len(new_jobs)} new jobs successfully"

    except Exception as e:
        return f"❌ Email failed: {str(e)}"
    
def send_no_jobs_email(recipient: str) -> str:
    """Send email when no new jobs are found"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; }
            .container { max-width: 600px; margin: 0 auto; padding: 20px; }
            h2 { color: #2c3e50; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>🤷 UK Tech Jobs Digest</h2>
            <p>No new high-paying tech jobs found today.</p>
            <p>💰 Salary: £120,000 - £150,000<br>
            📍 Location: United Kingdom</p>
            <p>Will keep searching tomorrow!</p>
            <hr>
            <small>Automated UK Job Search Agent</small>
        </div>
    </body>
    </html>
    """
    
    try:
        msg = MIMEMultipart()
        msg["From"] = YOUR_EMAIL
        msg["To"] = recipient
        msg["Subject"] = "🤷 UK Tech Jobs - No new jobs today"

        msg.attach(MIMEText(html_content, "html"))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(YOUR_EMAIL, YOUR_EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()

        return "✅ No jobs found - notification email sent"

    except Exception as e:
        return f"❌ Failed to send no-jobs email: {str(e)}"    
# ============================================================
# FILTER TOOL
# ============================================================

@tool
def filter_jobs_by_criteria(jobs: List[Dict]) -> List[Dict]:
    filtered = []

    for j in jobs:
        title = j.get("title", "").lower()
        location = j.get("location", "").lower()

        role_match = any(r.lower() in title for r in TARGET_ROLES)
        uk_match = any(x in location for x in ["uk", "london", "britain", "united kingdom", "manchester", "london" ])

        posted_date = j.get("posted_date", "")
        is_recent, days_old, _ = parse_linkedin_date(posted_date)

        if role_match and uk_match and is_recent:
            filtered.append(j)
        elif not is_recent and posted_date:
            print(f"⏭️ Filtered out (too old): {j.get('title')} - {posted_date} ({days_old} days)")

        # if role_match and uk_match:
        #     filtered.append(j)

    return filtered

# ============================================================
# AGENT
# ============================================================

job_agent = Agent(
    tools=[
        search_linkedin_jobs,
        search_cwjobs,
        search_general_jobs,
        filter_jobs_by_criteria,
        send_job_digest
    ],
    system_prompt=f"""
    You are a UK job hunting assistant. Your job is to help find tech jobs paying £{SALARY_MIN:,} - £{SALARY_MAX:,} GBP in the United Kingdom and posted in last 1 week.

    TARGET ROLES: {', '.join(TARGET_ROLES)}

    When searching for jobs:
    1. Always search for each target role using search_linkedin_jobs, search_cwjobs, and search_general_jobs
    2. After collecting jobs, use filter_jobs_by_criteria to ensure they match the requirements
    3. Finally, use send_job_digest to email the results to {YOUR_EMAIL}

IMPORTANT:
- Never resend jobs already in CSV history
- CSV file is jobs_history.csv

If no jobs are found, send an email saying "No new jobs found today" to keep me informed.

"""
)

# ============================================================
# MAIN
# ============================================================

def run_job_search():
    """Main function to run the job search agent"""
    print(f"🔍 Starting UK job search at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📋 Target roles: {', '.join(TARGET_ROLES)}")
    print(f"💰 Salary range: £{SALARY_MIN:,} - £{SALARY_MAX:,}")
    print(f"📍 Location: {LOCATION}")
    print("-" * 50)

     # Build the search prompt
    search_prompt = f"""
    Search for all {len(TARGET_ROLES)} job roles in {LOCATION} paying £{SALARY_MIN:,} to £{SALARY_MAX:,}.
    After collecting all jobs, filter them, then send the digest to {YOUR_EMAIL}.
    """

    try:
        result = job_agent(search_prompt)
        print(f"\n✅ Agent completed: {result}")
        return result
    except Exception as e:
        print(f"\n❌ Agent error: {e}")
 


if __name__ == "__main__":

    print("=" * 60)
    print("🤖 UK Job Search Agent")
    print("=" * 60)

    missing = []
    if not TAVILY_API_KEY:
        missing.append("TAVILY_API_KEY")
    if not YOUR_EMAIL_PASSWORD:
        missing.append("EMAIL_PASSWORD")
    
    if missing:
        print(f"⚠️  WARNING: Missing: {', '.join(missing)}")
        print("   For GitHub Actions: Add as repository secrets")
        print("   For local testing: Create a .env file")
        sys.exit(1)
    
    # Run the search
    run_job_search()