# UK Job Search Agent 🤖

Daily automated job search for UK tech roles paying £120k-150k.

## Setup 

1. Get Tavily API key from https://tavily.com
2. Add secrets in GitHub: Settings → Secrets and variables → Actions
   - `TAVILY_API_KEY`  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"
   - `EMAIL_PASSWORD`
   - Aws secret keys 
3. Push to main branch 

## How it works

Runs daily at 10:05 AM UK time, searches LinkedIn & job boards, emails (in gmail) results.
This Cron job is scheduled in cron-job via acron job  https://console.cron-job.org/jobs/7631568
URL points to github , action.yml : https://api.github.com/repos/taniShant/uk-job-search-agent/actions/workflows/deploy.yml/dispatches

Go to Advanced tab of cron and set values 

Key : Accept         Value: application/vnd.github.v3+json
Key : Authorization  Value: Bearer <gitlab pat>
Key : Content-Type   Value: application/json

Method: POST . Request body {"ref":"main"}

## License

MIT 

