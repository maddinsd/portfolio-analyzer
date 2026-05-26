# Privacy Rules — Personal Data Protection

## Files That Contain Personal or Sensitive Data
These files MUST NEVER be committed, logged, printed
to console in full, or exposed via any endpoint:

| File | Contents | Rule |
|------|----------|------|
| web/feedback.json | User feedback messages | Never read aloud, never commit |
| data/applications.json | Job applications, statuses | Never commit, never log |
| data/seen_jobs.json | Job monitoring history | Never commit, never log |
| data/firm_counts.json | Career strategy data | Never commit, never log |
| data/jobs_feed.js | Job listings cache | Never commit |
| .env | API keys and secrets | Never commit, never print |
| web/static/examples/ | Example outputs | Public — safe to serve |

## API Keys and Credentials
All secrets MUST live in environment variables only.
Never in source code. Never in comments.
Never in commit messages. Never in log output.

Keys in use:
- ANTHROPIC_API_KEY — Claude API
- FMP_API_KEY — Financial Modeling Prep
- NEWS_API_KEY — NewsAPI
- ADMIN_TOKEN — Platform admin password
- ICLOUD_EMAIL / ICLOUD_APP_PASSWORD — Email relay

If a key needs to be referenced in documentation,
use the variable name only — never the value.
Example: "Set ANTHROPIC_API_KEY in Vercel env vars"

## Personal Information Rules
- sdmadding@icloud.com may appear in:
  · Vercel environment variables (ICLOUD_EMAIL)
  · The live disclaimer rendered in the browser
  · README.md attribution
- sdmadding@icloud.com MUST NEVER appear in:
  · Python source files (use os.environ instead)
  · JavaScript source files
  · Any file committed to git (except README.md)

## Third-Party Data Collection
No analytics, tracking, or telemetry may be added
without explicit instruction. This includes:
- Google Analytics / GA4
- Mixpanel, Amplitude, PostHog
- Facebook Pixel
- Hotjar, FullStory, or session recording tools
- Any CDN-loaded script not already in the project

## Vercel Deployment Privacy
- All API keys are set in Vercel dashboard only
- Never in vercel.json
- Never in environment config files committed to git
- The .vercelignore file MUST exclude data/ directories

## Job Monitor Isolation
- ~/job-monitor is a separate private project
- NEVER reference, link to, or expose it from this codebase
- data/ files (seen_jobs, firm_counts, jobs_feed) are
  job monitor artifacts — never commit, never serve
