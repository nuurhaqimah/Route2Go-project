# Route2Go

An AI-powered travel planner that generates personalised weekend itineraries through a chatbot interface, complete with images, accommodation suggestions, and flight search.

<img width="1901" height="1179" alt="Screenshot 2026-05-11 091245" src="https://github.com/user-attachments/assets/03810e48-bf9d-4a48-96fb-259151fac963" />


## Project Structure

```
route2go/
├── backend/
│   ├── app.py            # Flask app — all routes and API logic
│   ├── database.py       # PostgreSQL helper functions
│   ├── init_db.py        # Creates tables and seeds initial POI data
│   ├── prompts.py        # Gemini AI system prompt
│   ├── requirements.txt  # Python dependencies
│   ├── .env              # Your local secrets (not committed)
│   ├── .env.example      # Template — copy this to .env
│   └── sql/              # Reference SQL scripts
├── frontend/
│   ├── templates/        # HTML pages served by Flask
│   └── static/           # CSS, JS, and image assets
├── .gitignore
└── README.md
```

Flask serves the API and the HTML pages together — there is no separate frontend
dev server. One `python app.py` runs the whole site.

## Prerequisites

- Python 3.10+
- PostgreSQL 14+ running locally

## Quick Start

### 1. Clone and enter the project

```bash
git clone <repo-url>
cd route2go
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
# From inside the backend/ folder:
cp .env.example .env
```

Open `backend/.env` and fill in your values:

| Variable                                 | Where to get it                                                                              |
| ---------------------------------------- | -------------------------------------------------------------------------------------------- |
| `GEMINI_API_KEY`                         | [Google AI Studio](https://aistudio.google.com/) → Get API key                               |
| `DB_PASSWORD`                            | Your local PostgreSQL password                                                               |
| `FLASK_SECRET_KEY`                       | Any long random string (e.g. run `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `ADMIN_PASS`                             | Choose a secure admin password                                                               |
| `PORT`                                   | Port the site runs on. Defaults to `5000`; the template uses `5050`                            |

### 5. Create the PostgreSQL database

Connect to PostgreSQL (via `psql` or pgAdmin) and run:

```sql
CREATE DATABASE itinerary_db;
```

### 6. Initialise the database

Creates the tables, then seeds destinations from `sql/insert_poi.sql` if the POI
table is empty. Existing destinations are never overwritten, so this is safe to
re-run.

```bash
# From inside the backend/ folder:
python init_db.py
python seed_food_data.py      # expanded food destinations
python seed_missing_data.py   # fills category/budget gaps
```

That gives you 170 destinations across Brunei, Malaysia, Singapore, Indonesia,
Thailand, the Philippines, and Japan.

### 7. Fetch real destinations (optional)

Pulls live tourist destinations from OpenStreetMap and ranks them by Wikipedia
pageviews. No API key or signup required.

```bash
# From inside the backend/ folder:
python refresh_external_pois.py --city "Kuala Lumpur" --country Malaysia
python refresh_external_pois.py                  # every curated city
python refresh_external_pois.py --stale-days 30  # only refresh older entries
```

Curated destinations are never overwritten — if a fetched place shares a name
with one of yours, yours is kept. See [Destination sources](#destination-sources).

### 7. Run the app

```bash
# From inside the backend/ folder:
python app.py
```

Open your browser at **http://localhost:5050**

---

## Troubleshooting

### `An attempt was made to access a socket in a way forbidden by its access permissions`

Another program has claimed the port. Find out which:

```powershell
netsh http show servicestate view=requestq | Select-String ":5000/" -Context 20,0
```

Either stop that program, or pick a free port by changing `PORT` in
`backend/.env`.

---

## Login Details

| Role         | Username              | Password                            | URL                               |
| ------------ | --------------------- | ----------------------------------- | --------------------------------- |
| Admin        | `admin`               | _(value of `ADMIN_PASS` in `.env`)_ | http://localhost:5050/login       |
| Regular user | _(register yourself)_ | _(your choice)_                     | http://localhost:5050/user/signup |

---

## Key Pages

| URL            | Description               |
| -------------- | ------------------------- |
| `/`            | Home / chatbot            |
| `/trip`        | Generate a new itinerary  |
| `/mytrips`     | View saved itineraries    |
| `/user/signup` | Register a new account    |
| `/user/login`  | User login                |
| `/admin`       | Admin panel (manage POIs) |
| `/health`      | Health check endpoint     |

---

## Destination sources

Destinations come from two places, both stored in the `poi` table and told apart
by its `source` column:

| Source | Meaning | How it gets there |
| ------- | ------------------------------------------------ | ---------------------------------- |
| `local` | Hand-curated spots, including local secrets that aren't listed online | Admin panel, or the seed scripts |
| `osm`   | Real destinations fetched from OpenStreetMap, ranked by Wikipedia pageviews | `refresh_external_pois.py`         |

Results put curated spots first, then the most popular fetched ones. Places that
OpenStreetMap marks as disused or permanently closed are filtered out on fetch.

Two limitations worth knowing:

- **No reviews or star ratings.** No free provider exposes them — Google charges
  per call for the `reviews` field and Foursquare has no free tier for ratings.
  Wikipedia pageviews stand in as a popularity signal instead.
- **Budget and travel style are unknown for fetched places.** OpenStreetMap has
  no equivalent, so those columns stay `NULL` rather than being guessed, and a
  filter on either still admits them.

## Tech Stack

- **Backend** — Python, Flask, psycopg2
- **AI** — Google Gemini 1.5 Flash
- **Database** — PostgreSQL
- **Destination data** — OpenStreetMap (Overpass API) + Wikipedia pageviews
- **Frontend** — HTML, CSS, Vanilla JS
- **PDF export** — Browser native print (`window.print()` via a dedicated print view)
