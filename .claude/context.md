# Project Context — Lindner Research Platform

## Who This Is For
Finance student at the University of Cincinnati, Carl H.
Lindner College of Business. Targeting sell-side equity
research roles (Baird, Piper Sandler, William Blair,
Stifel, KeyBanc). CFA Level I exam August 2026.

## What This Project Is
An AI-powered equity research platform that generates
institutional-grade research packages from a single ticker
symbol. Built as a portfolio project and personal tool.

## Live URLs
- Production: https://web-chi-ten-48.vercel.app
- Local: http://localhost:5001
- GitHub: https://github.com/maddinsd/portfolio-analyzer

## Tech Stack
- Backend: Python, Flask, app.py
- Frontend: HTML, CSS (design-system.css), vanilla JS (app.js)
- Data: yfinance, FMP API, SEC EDGAR, NewsAPI, Anthropic API
- Deployment: Vercel (make deploy)
- Notifications: ntfy.sh (sam-madding-finance-alerts topic)

## Project Structure
web/           — Flask web app (deployed to Vercel)
automation/    — Python pipeline (local only, never deployed)
main.py        — Local CLI entry point
Makefile       — make deploy syncs and deploys web/

## Design System
All colors, spacing, typography from design-system.css.
Never hardcode colors or spacing values.
8px grid only. CSS variables only.
Dark mode via [data-theme="dark"] on html element.

## Key Architectural Rules
- Web (Vercel) and local pipeline are separate systems
- automation/ files are never deployed to Vercel
- Vercel only runs web/app.py
- make deploy = sync pipeline files + npx vercel --prod
- Admin auth via admin_token cookie + ADMIN_TOKEN env var
- Visitor mode: read-only, inputs disabled, examples visible
- Admin mode: full access after password modal

## What Must Never Change Without Discussion
- The UC disclaimer in the sidebar footer
- The admin authentication mechanism
- The rate limiting configuration
- The .gitignore rules for data files
- The design system CSS variable names

## Sensitive Areas
- The personal iCloud email is only valid in Vercel env vars,
  the browser-rendered disclaimer, and README.md attribution —
  never in committed source code; use ICLOUD_EMAIL env var
- ~/job-monitor is a separate private project — never reference
  it from here under any circumstances
