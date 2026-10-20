# Job Hunter AI — personal Telegram bot

Private-use long-polling Telegram bot for one user. Core commands: `/start`, `/scan`, `/top`, `/saved`, `/stats`, `/sources`, `/profile`, `/add`, `/cover ID`, `/analyze ID`, `/pause`, `/resume`. Buttons track applications, saves and skips. **The bot never automatically applies to jobs.**

## Sources and limitations

Automated: Himalayas and Remotive public APIs; optional HeadHunter only with an authorized token; optional official public RSS/Atom feeds. Habr Career, getmatch and Dream Job support manual import: forward/paste a vacancy with its full description and URL, then reply `/add`. A bare URL is insufficient. Matching 0–100 is a heuristic, not a hiring probability. Optional `OPENAI_API_KEY` enables AI cover letters and analysis; without it the fallback is rule-based. Geographic eligibility must be confirmed independently.

## Railway deployment

Connect **this repository** to a Railway service (Dockerfile root). Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_OWNER_ID` as protected Railway Variables; never commit them. Set `DB_PATH=/app/data/jobs.sqlite3` and attach a persistent Railway volume at `/app/data`. One service/replica, no public domain required: Telegram updates are handled by long polling. Optional: portfolio links and `OPENAI_API_KEY` in Railway Variables. Railway may charge for running containers and volumes.

Open the Telegram bot, press **Start** and send `/scan`. After setup check `Deploy Logs`. Scans run every 12 hours. Manual scans reuse the last result if less than 6 hours old, to respect job-source API rate limits.

## Local

Install Python 3.11+, run `pip install -r requirements.txt`, copy `.env.example` to `.env`, supply credentials and then use `python main.py`. For local environment files, load via your shell or `python-dotenv` if installed. Do not run local and cloud polling at the same time (Telegram getUpdates conflict).
