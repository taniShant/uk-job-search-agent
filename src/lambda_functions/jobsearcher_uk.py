import os
import json
import boto3
from datetime import datetime, timedelta
from tavily import TavilyClient
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# -------------------------
# ENV
# -------------------------
TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]
DDB_TABLE = os.environ["DDB_TABLE"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

YOUR_EMAIL = "shantanu.bsa@gmail.com"

ddb = boto3.resource("dynamodb")
table = ddb.Table(DDB_TABLE)

client = TavilyClient(api_key=TAVILY_API_KEY)

TARGET_ROLES = [
    "AI Engineer",
    "Data Engineer",
    "ML Engineer",
    "Cloud Architect"
]

LOCATION = "United Kingdom"


# -------------------------
# DDB DEDUP
# -------------------------
def is_duplicate(url):
    resp = table.get_item(Key={"job_url": url})
    return "Item" in resp


def mark_seen(url, title):
    table.put_item(
        Item={
            "job_url": url,
            "title": title,
            "ttl": int((datetime.utcnow() + timedelta(days=7)).timestamp())
        }
    )


# -------------------------
# SEARCH LOGIC (YOUR OLD STYLE)
# -------------------------
def search_jobs():
    jobs = []

    for role in TARGET_ROLES:
        query = f'site:linkedin.com/jobs "{role}" "{LOCATION}"'
        results = client.search(query, max_results=10)

        for r in results.get("results", []):
            url = r.get("url")
            title = r.get("title", role)

            if not url or is_duplicate(url):
                continue

            jobs.append({
                "title": title,
                "url": url
            })

            mark_seen(url, title)

    return jobs


# -------------------------
# EMAIL (YOUR EXISTING STYLE)
# -------------------------
def send_email(jobs):
    if not jobs:
        return

    html = "<h2>UK Jobs</h2>"
    for j in jobs:
        html += f"<p><a href='{j['url']}'>{j['title']}</a></p>"

    msg = MIMEMultipart()
    msg["From"] = YOUR_EMAIL
    msg["To"] = YOUR_EMAIL
    msg["Subject"] = f"UK Jobs - {len(jobs)} new"

    msg.attach(MIMEText(html, "html"))

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(YOUR_EMAIL, EMAIL_PASSWORD)
    server.send_message(msg)
    server.quit()


# -------------------------
# LAMBDA ENTRYPOINT
# -------------------------
def lambda_handler(event, context):
    jobs = search_jobs()
    send_email(jobs)

    return {
        "statusCode": 200,
        "body": json.dumps({"jobs_found": len(jobs)})
    }