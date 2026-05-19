#!/usr/bin/env python3
"""
UK Job Search Agent - Finds £120k-150k tech jobs in UK and emails daily digest
Built with Strands Agents SDK
"""

import os, sys
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import List, Dict, Any
from dotenv import load_dotenv

from strands import Agent, tool
from tavily import TavilyClient

# Load environment variables
load_dotenv()

# ============================================================
# CONFIGURATION - EDIT THESE VALUES
# ============================================================

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "your_tavily_api_key_here")
YOUR_EMAIL = "shantanu.bsa@gmail.com"
YOUR_EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")  # For Gmail, use App Password
SMTP_SERVER = "smtp.gmail.com"  # Use "smtp.mail.yahoo.com" for Yahoo, etc.
SMTP_PORT = 587

# Job search criteria
TARGET_ROLES = [
    "AI Engineer", "Data Engineer", "Data Scientist", "AI Strategist",
    "Cloud Architect", "Lead Architect", "Solutions Architect",
    "Head of AI", "Principal Data Engineer", "ML Engineer"
]

SALARY_MIN = 120000
SALARY_MAX = 150000
LOCATION = "United Kingdom"

# File to track already sent jobs (for deduplication)
SENT_JOBS_FILE = "sent_jobs.json"

# ============================================================
# DEDUPLICATION - Never resend the same job
# ============================================================

def load_sent_jobs() -> Dict[str, str]:
    """Load previously sent jobs from file"""
    if os.path.exists(SENT_JOBS_FILE):
        with open(SENT_JOBS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_sent_jobs(sent_jobs: Dict[str, str]):
    """Save sent jobs to file"""
    with open(SENT_JOBS_FILE, 'w') as f:
        json.dump(sent_jobs, f, indent=2)

def is_job_already_sent(job_url: str, sent_jobs: Dict[str, str]) -> bool:
    """Check if job was already emailed"""
    return job_url in sent_jobs

def mark_job_as_sent(job_url: str, job_title: str, sent_jobs: Dict[str, str]):
    """Mark job as sent"""
    sent_jobs[job_url] = {
        "title": job_title,
        "sent_date": datetime.now().isoformat()
    }
    save_sent_jobs(sent_jobs)

# ============================================================
# TOOL 1: Search LinkedIn for Jobs
# ============================================================

@tool
def search_linkedin_jobs(role: str) -> List[Dict]:
    """
    Search LinkedIn for UK tech jobs matching the role.
    Returns list of job postings with titles, companies, locations, and links.
    """
    client = TavilyClient(api_key=TAVILY_API_KEY)
    
    # Construct search query
    query = f'site:linkedin.com/jobs "{role}" "{LOCATION}" salary {SALARY_MIN} {SALARY_MAX} GBP'
    
    try:
        results = client.search(query, max_results=15)
        
        jobs = []
        for result in results.get('results', []):
            job = {
                'title': result.get('title', role),
                'company': extract_company_from_url(result.get('url', '')),
                'location': LOCATION,
                'salary_range': f"£{SALARY_MIN:,} - £{SALARY_MAX:,}",
                'apply_url': result.get('url', ''),
                'source': 'LinkedIn',
                'posted_date': datetime.now().strftime('%Y-%m-%d')
            }
            jobs.append(job)
        
        return jobs
    except Exception as e:
        print(f"Error searching LinkedIn: {e}")
        return []

def extract_company_from_url(url: str) -> str:
    """Extract company name from LinkedIn job URL"""
    # Simple extraction - can be improved
    parts = url.split('/')
    for i, part in enumerate(parts):
        if part == 'company' and i + 1 < len(parts):
            return parts[i + 1].replace('-', ' ').title()
    return "Unknown Company"

# ============================================================
# TOOL 2: Search CWJobs
# ============================================================

@tool
def search_cwjobs(role: str) -> List[Dict]:
    """
    Search CWJobs for UK IT jobs matching the role.
    """
    client = TavilyClient(api_key=TAVILY_API_KEY)
    
    query = f'site:cwjobs.co.uk "{role}" £{SALARY_MIN//1000}k £{SALARY_MAX//1000}k'
    
    try:
        results = client.search(query, max_results=10)
        
        jobs = []
        for result in results.get('results', []):
            job = {
                'title': result.get('title', role),
                'company': extract_domain_name(result.get('url', '')),
                'location': LOCATION,
                'salary_range': f"£{SALARY_MIN:,} - £{SALARY_MAX:,}",
                'apply_url': result.get('url', ''),
                'source': 'CWJobs',
                'posted_date': datetime.now().strftime('%Y-%m-%d')
            }
            jobs.append(job)
        
        return jobs
    except Exception as e:
        print(f"Error searching CWJobs: {e}")
        return []

def extract_domain_name(url: str) -> str:
    """Extract domain name from URL"""
    import re
    match = re.search(r'https?://(?:www\.)?([^/]+)', url)
    if match:
        return match.group(1).split('.')[0].title()
    return "Unknown Company"

# ============================================================
# TOOL 3: Search General Job Boards
# ============================================================

@tool
def search_general_jobs(role: str) -> List[Dict]:
    """
    Search general job boards (Indeed, Monster, etc.) for UK tech jobs.
    """
    client = TavilyClient(api_key=TAVILY_API_KEY)
    
    query = f'"{role}" jobs "{LOCATION}" salary {SALARY_MIN} to {SALARY_MAX}'
    
    try:
        results = client.search(query, max_results=15)
        
        jobs = []
        for result in results.get('results', []):
            # Filter out non-UK or irrelevant results
            title = result.get('title', '').lower()
            if any(role.lower() in title for role in TARGET_ROLES):
                job = {
                    'title': result.get('title', role),
                    'company': extract_domain_name(result.get('url', '')),
                    'location': LOCATION,
                    'salary_range': f"£{SALARY_MIN:,} - £{SALARY_MAX:,}",
                    'apply_url': result.get('url', ''),
                    'source': 'General Job Board',
                    'posted_date': datetime.now().strftime('%Y-%m-%d')
                }
                jobs.append(job)
        
        return jobs
    except Exception as e:
        print(f"Error searching general jobs: {e}")
        return []

# ============================================================
# TOOL 4: Send Email Digest
# ============================================================

@tool
def send_job_digest(jobs: List[Dict], recipient: str) -> str:
    """
    Send HTML email digest with all new job matches.
    """
    if not jobs:
        return "No new jobs found today"
    
    # Filter out already sent jobs
    sent_jobs = load_sent_jobs()
    new_jobs = [job for job in jobs if not is_job_already_sent(job['apply_url'], sent_jobs)]
    
    if not new_jobs:
        return f"No new jobs today (found {len(jobs)} jobs but all were already sent previously)"
    
    # Create HTML email
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
            h2 {{ color: #34495e; margin-top: 20px; }}
            .job {{ background: #f8f9fa; border-left: 4px solid #3498db; padding: 15px; margin: 15px 0; border-radius: 4px; }}
            .job-title {{ font-size: 18px; font-weight: bold; color: #2c3e50; }}
            .company {{ color: #7f8c8d; margin: 5px 0; }}
            .salary {{ color: #27ae60; font-weight: bold; margin: 5px 0; }}
            .location {{ color: #7f8c8d; margin: 5px 0; }}
            .apply-link {{ margin: 10px 0; }}
            .apply-link a {{ background: #3498db; color: white; padding: 8px 15px; text-decoration: none; border-radius: 4px; }}
            .apply-link a:hover {{ background: #2980b9; }}
            .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #ddd; font-size: 12px; color: #95a5a6; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎯 UK Tech Jobs Digest</h1>
            <p>Found <strong>{len(new_jobs)}</strong> new jobs matching your criteria:</p>
            <ul>
                <li>💰 Salary: £{SALARY_MIN:,} - £{SALARY_MAX:,}</li>
                <li>📍 Location: {LOCATION}</li>
                <li>💼 Roles: {', '.join(TARGET_ROLES[:5])}...</li>
            </ul>
    """
    
    for job in new_jobs:
        html_content += f"""
            <div class="job">
                <div class="job-title">{job.get('title', 'Position Available')}</div>
                <div class="company">🏢 {job.get('company', 'Unknown Company')}</div>
                <div class="salary">💰 {job.get('salary_range', 'Salary not specified')}</div>
                <div class="location">📍 {job.get('location', LOCATION)}</div>
                <div class="apply-link">
                    <a href="{job.get('apply_url', '#')}">📋 View & Apply</a>
                </div>
                <small>Source: {job.get('source', 'Job Board')} | Found: {job.get('posted_date', 'Today')}</small>
            </div>
        """
        
        # Mark as sent
        mark_job_as_sent(job['apply_url'], job.get('title', 'Unknown'), load_sent_jobs())
    
    html_content += f"""
            <div class="footer">
                <p>This is an automated daily job alert from your UK Job Search Agent.</p>
                <p>To stop receiving these emails, remove the scheduled task or update your settings.</p>
                <p>Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Send email
    try:
        msg = MIMEMultipart()
        msg['From'] = YOUR_EMAIL
        msg['To'] = recipient
        msg['Subject'] = f"🎯 Daily Job Alert: {len(new_jobs)} new UK Tech Jobs (£{SALARY_MIN//1000}k-£{SALARY_MAX//1000}k)"
        
        msg.attach(MIMEText(html_content, 'html'))
        
        # For Gmail, use App Password
        if SMTP_SERVER == "smtp.gmail.com":
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(YOUR_EMAIL, YOUR_EMAIL_PASSWORD)
            server.send_message(msg)
            server.quit()
        else:
            # For other SMTP servers
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(YOUR_EMAIL, YOUR_EMAIL_PASSWORD)
            server.send_message(msg)
            server.quit()
        
        return f"✅ Successfully sent {len(new_jobs)} job alerts to {recipient}"
    
    except Exception as e:
        return f"❌ Failed to send email: {str(e)}"

# ============================================================
# TOOL 5: Filter Jobs by Role and Location
# ============================================================

@tool
def filter_jobs_by_criteria(jobs: List[Dict]) -> List[Dict]:
    """
    Filter jobs to only include those matching target roles and UK location.
    """
    filtered = []
    
    for job in jobs:
        title = job.get('title', '').lower()
        location = job.get('location', '').lower()
        
        # Check role match
        role_match = any(role.lower() in title for role in TARGET_ROLES)
        
        # Check UK location
        uk_match = 'uk' in location or 'Uk' in location or 'UK' in location or 'london' in location or 'London' in location or 'britain' in location or 'united kingdom' in location or 'United Kingdom' in location
        
        if role_match and uk_match:
            filtered.append(job)
    
    return filtered

# ============================================================
# CREATE THE AGENT
# ============================================================

# Initialize the Strands Agent with all tools [citation:7]
job_agent = Agent(
    tools=[
        search_linkedin_jobs,
        search_cwjobs,
        search_general_jobs,
        filter_jobs_by_criteria,
        send_job_digest
    ],
    system_prompt=f"""
    You are a UK job hunting assistant. Your job is to help find tech jobs paying £{SALARY_MIN:,} - £{SALARY_MAX:,} GBP in the United Kingdom.

    TARGET ROLES: {', '.join(TARGET_ROLES)}

    When searching for jobs:
    1. Always search for each target role using search_linkedin_jobs, search_cwjobs, and search_general_jobs
    2. After collecting jobs, use filter_jobs_by_criteria to ensure they match the requirements
    3. Finally, use send_job_digest to email the results to {YOUR_EMAIL}
    4. Never resend jobs that were already sent (the send_job_digest tool handles deduplication automatically)

    If no jobs are found, send an email saying "No new jobs found today" to keep me informed.
    """
)

# ============================================================
# MAIN EXECUTION FUNCTION
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
    
    # Run the agent
    try:
        result = job_agent(search_prompt)
        print(f"\n✅ Agent completed: {result}")
        return result
    except Exception as e:
        print(f"\n❌ Agent error: {e}")
        return None

# ============================================================
# RUN IF SCRIPT IS EXECUTED DIRECTLY
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 UK Job Search Agent")
    print("=" * 60)
    
    # Check configuration
    # if TAVILY_API_KEY == "ytvly-dev-29O2Uf-eseaqsg1WMAIvdvJGnm21eDnGC775Ld3ybTAHT3lbn":
    #     print("⚠️  WARNING: Please set your TAVILY_API_KEY in a .env file")
    #     print("   Create a file called .env with:")
    #     print("   TAVILY_API_KEY=tvly-your-actual-key")
    #     print("   EMAIL_PASSWORD=your-app-password")
    #     sys.exit(1)
    
    # if not YOUR_EMAIL_PASSWORD:
    #     print("⚠️  WARNING: Email password not set. Email sending will fail.")
    #     print("   For Gmail, create an App Password at: https://myaccount.google.com/apppasswords")
    #     print("   Then add to .env: EMAIL_PASSWORD=your-16-digit-app-password")


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

    # TODO : Persist today's data localy and check duplicates before resending alert next date 