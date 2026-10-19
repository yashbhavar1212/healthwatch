# HealthWatch: Smart Community Health Monitoring System

Early warning for water-borne disease (diarrhea, fever) in rural villages.
Health workers report daily counts. The system scores the risk, charts the trend,
raises alerts and draws trend charts for district officers.

Team: Piyush Chaudhari, Pranav Gawade, Sujan Kamble, Sarthak Sagare

## Run it (2 minutes)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows   (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

| Role | Username | Password |
|------|----------|----------|
| District officer (admin) | `admin` | `Admin@123` |
| Health worker | `worker` | `Worker@123` |

The app starts **empty**: no villages and no reports. Open Report cases, add a village, then add
reports for it. (Optional: set `DEMO_DATA=1` in `.env` before the first run to load 10 sample villages.)
Charts and fonts load from the internet (Chart.js, Google Fonts),
so keep Wi-Fi on during the presentation.

## What it does

| Page | Purpose |
|------|---------|
| Home | Live "Try the risk check" calculator, live village counts, how a report flows |
| Sign in | Role-based login (admin / worker) |
| Report cases | Step 1: add a village (list shows every village with its report count; officers can delete). Step 2: report form with village dropdown, diarrhea, fever, rainfall, water quality, date, notes. Live risk preview. Result with advice after saving |
| Dashboard | Stat tiles, alert feed with Acknowledge, 30-day line chart, risk doughnut, score bar chart, village status table. Auto-refreshes every minute |
| Records | Search and filter (village, level, dates), pagination, CSV export, admin delete |

## How risk is scored

Points are added for each factor, then the total picks the level.

| Factor | Points |
|--------|--------|
| Diarrhea cases | <5: 0, 5-10: 2, 11-25: 3, >25: 4 |
| Fever cases | <15: 0, 15-40: 1, >40: 2 |
| Rainfall | Low 0, Medium 1, High 2 |
| Drinking water | Good 0, Doubtful 1, Contaminated 2 |
| Rising trend | +1 if diarrhea is at least 1.5x the previous report (min. 5 cases) |

Score 0-2 Low, 3-4 Moderate, 5-6 High, 7+ Critical. High and Critical create an alert
(and an e-mail if SMTP is configured). The thresholds are working values for this project,
not an official WHO formula. Say so in your viva.

## Folder structure

```
app.py               Flask app factory, config, security headers
manage.py            Admin helper: stats, create-user, reset
backend/
  risk.py            Scoring engine (the heart of the project)
  db.py              SQLite schema + add_record()
  routes.py          JSON API (/api/...)
  pages.py           HTML pages with server-side login check
  alerts.py          Alert storage + optional e-mail
  seed.py            Default users, villages, demo data
templates/           Jinja pages (base, index, login, entry, dashboard, records)
static/css/style.css Design system
static/js/           common, home, login, entry, dashboard, records
tests/test_app.py    14 automated tests
```

## API summary

| Method | Endpoint | Access |
|--------|----------|--------|
| POST | /api/login, /api/logout | public / signed in |
| POST | /api/assess | public (calculator, stores nothing) |
| GET | /api/public/overview | public |
| GET / POST | /api/villages | signed in |
| DELETE | /api/villages/<id> | admin (deletes its reports too) |
| GET / POST | /api/records | signed in |
| DELETE | /api/records/<id> | admin |
| GET | /api/export.csv | signed in |
| GET | /api/summary | signed in |
| GET / POST | /api/alerts, /api/alerts/<id>/ack | signed in |

## Tests

```bash
python -m unittest discover tests -v
```

## Deploy on Render (free, step by step)

1. **Put the project on GitHub.** Create a free account, click New repository (name: `healthwatch`),
   then in the project folder (the one that contains `app.py`) run:
   ```
   git init
   git add .
   git commit -m "HealthWatch"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/healthwatch.git
   git push -u origin main
   ```
   No Git? On the repository page choose "uploading an existing file" and drag in the files and folders
   from inside `HealthWatch`. `app.py` must be at the top level of the repository, not inside another folder.
2. **Sign up at render.com** with "Sign in with GitHub".
3. Click **New +**, then **Web Service**, and pick the `healthwatch` repository.
4. Fill the form:
   - Language: **Python 3**
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app --workers 1 --threads 4 --bind 0.0.0.0:$PORT`
   - Instance type: **Free**
5. Open **Advanced / Environment Variables** and add:
   - `FLASK_SECRET_KEY` = any long random text
   - `ADMIN_PASSWORD` = your own admin password
   - `WORKER_PASSWORD` = your own worker password
   - `PRODUCTION` = `1`
6. Click **Create Web Service**. The first build takes a few minutes. When the log says the service is live,
   open the `https://healthwatch-xxxx.onrender.com` address shown at the top and sign in.
7. **To update the site later:** change the code, run `git add .`, `git commit -m "update"`, `git push`.
   Render redeploys by itself.

Things to know about the free plan:
- The service sleeps after 15 minutes without visitors. The first visit afterwards takes about a minute.
  **Open the site 5 minutes before your presentation.**
- The disk is temporary. Without a Neon database (see the next section) villages and reports are erased when
  the service restarts or redeploys.
- For permanent data use the free Neon database described below (recommended), or a paid Render disk.

Another free option is PythonAnywhere (free account, Flask supported, files stay saved), but it needs a manual
WSGI setup.


## Keep your data permanently (free): Neon database

On Render's free plan the disk is temporary, so a SQLite file is erased whenever the site sleeps, restarts or
redeploys. The fix is a free online PostgreSQL database. The app switches to it automatically when `DATABASE_URL` is set.
Locally (no `DATABASE_URL`) it still uses the SQLite file.

1. Go to **neon.com** and sign up (no card needed). Create a project (any name, nearest region).
2. On the project dashboard click **Connect**, make sure the database and role are the defaults, and copy the
   **connection string** (it starts with `postgresql://`).
3. In Render open your web service, then **Environment**, and add:
   - `DATABASE_URL` = the connection string you copied
   - `PYTHON_VERSION` = `3.12.3`
4. Push the new code to GitHub (`git add .`, `git commit -m "postgres"`, `git push`). Render redeploys.
5. Open the site, sign in, add your villages and reports once. They now stay saved, even after the site sleeps or redeploys.

Notes: Neon's free database pauses after 5 idle minutes and wakes on the next visit (the first page can take a
second or two longer). The free plan is permanent and gives 0.5 GB, far more than this project needs.
Do not use Render's own free PostgreSQL for this: it is time-limited.

## Optional e-mail alerts

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_EMAIL_TO` in `.env`
(for Gmail, use an app password). Every High or Critical report then sends a mail.

## Improvements over the first version

| Before | Now |
|--------|-----|
| 40 diarrhea cases with medium rain was labelled Safe | Multi-factor score. Same case is Critical (covered by a test) |
| Fever was stored but never used | Fever, rainfall, water quality and trend all count |
| One shared login from an environment variable | Users table, hashed passwords, admin and worker roles |
| Village typed as free text | Add a village first, then report for it. Villages and reports can be deleted |
| Table only | Charts, alerts, filters, CSV export |
| `innerHTML` with raw data (XSS risk) | All output escaped |
| Dashboard HTML was public | Pages protected on the server, CSRF tokens on changes |
| Popups promised SMS, maps, exports that did not exist | Export and e-mail alerts are real. Limits are listed honestly |

## Likely viva questions

**Why rule-based and not machine learning?** There is no labelled outbreak data yet. Rules are transparent
and health workers can verify them. With real data we would train a model and compare it to these rules.

**Why SQLite?** Zero setup and enough for one district. The SQL is standard, so moving to PostgreSQL is a connection change.

**How do you stop bad data?** Server-side validation of every field, range limits, dates cannot be in the future.

**What stops someone changing data without logging in?** Server-side session check on every page and API call, plus CSRF tokens.

**How is the rising trend found?** The new report is compared with the village's previous report by date.

**What would you build next?** Automatic rainfall from a weather API, SMS alerts, PostgreSQL, a trained prediction model,
a mobile-friendly offline form for areas with poor network.
