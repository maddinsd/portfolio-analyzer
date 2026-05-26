# Rules — What Claude May and May Not Do

## 🟢 MAY DO WITHOUT ASKING
- Read any file in the project
- Write or edit code files, templates, stylesheets
- Install npm or pip packages (non-destructive)
- Run tests, linters, dry-run commands
- Create new files and directories
- Commit staged changes with a descriptive message
- Run make deploy ONLY after explicit "deploy" instruction
- Search the codebase, grep, list files
- Generate, edit, or delete example/static files
- Update CLAUDE.md and rule files when instructed

## 🟡 MUST ASK BEFORE DOING
- git push (always confirm before pushing to remote)
- make deploy or any Vercel deployment
- Deleting any file that exists in git history
- Adding any new external API integration
- Changing any environment variable name or structure
- Modifying .gitignore (could accidentally expose files)
- Adding any script tag to HTML files (third-party risk)
- Changing authentication or admin logic
- Any operation that touches feedback.json contents
- Sending any real notification or email
- Running any command that costs money (API calls)

## 🔴 NEVER DO — NO EXCEPTIONS
- Hardcode any API key, password, token, or secret
  in any file that could be committed
- Commit or log contents of: feedback.json,
  applications.json, seen_jobs.json, firm_counts.json,
  jobs_feed.js, .env, or any file in data/
- Hardcode the personal email address in committed
  source files — use os.environ / ICLOUD_EMAIL only
- Add analytics scripts, tracking pixels, or
  third-party data collection to the web interface
- Reference or link to ~/job-monitor from this project
- Expose the admin password (ADMIN_TOKEN) in any
  client-side code, logs, or error messages
- Create public endpoints that return raw file
  contents from data/ directories
- Add any dependency that phones home or collects
  usage data without explicit approval
- Run git push --force on any branch
- Empty or truncate seen_jobs.json, feedback.json,
  or any data file without explicit instruction
- Modify the UC disclaimer in the footer
