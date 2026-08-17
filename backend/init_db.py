import psycopg2
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "itinerary_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432))
}

def init_db():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Users
        cur.execute("""
        CREATE TABLE IF NOT EXISTS app_user (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS itineraries (
            id SERIAL PRIMARY KEY,
            user_id TEXT,
            data JSONB,
            created_at TIMESTAMP DEFAULT NOW()
      )
      """)

        # Itineraries
        cur.execute("""
        CREATE TABLE IF NOT EXISTS itinerary (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES app_user(id) ON DELETE CASCADE,
            title TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            data JSONB
        );
        """)

        # POIs — never dropped. Re-running this script must not destroy
        # destination data; use sql/insert_poi.sql to (re)seed instead.
        cur.execute("""
        CREATE TABLE IF NOT EXISTS poi (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,               -- e.g. nature/food/history/shopping
            description TEXT,
            location TEXT,               -- city/region
            country TEXT,                -- country name
            budget_level TEXT,           -- low/medium/high
            travel_style TEXT,           -- e.g. relaxing/cultural/adventure
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        # Hybrid-source columns. Added separately (rather than in the CREATE
        # above) so existing databases pick them up on re-run.
        #   source      'local' for hand-curated gems, 'osm' for fetched POIs
        #   external_id stable provider key, e.g. 'osm:node/1234', for upserts
        #   popularity  Wikipedia pageviews over the last 90 days; NULL if the
        #               place has no Wikipedia article
        #   fetched_at  when the row was last refreshed from the provider
        for ddl in (
            "ALTER TABLE poi ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'local'",
            "ALTER TABLE poi ADD COLUMN IF NOT EXISTS external_id TEXT",
            "ALTER TABLE poi ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION",
            "ALTER TABLE poi ADD COLUMN IF NOT EXISTS lon DOUBLE PRECISION",
            "ALTER TABLE poi ADD COLUMN IF NOT EXISTS popularity INTEGER",
            "ALTER TABLE poi ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMP",
            "CREATE UNIQUE INDEX IF NOT EXISTS poi_external_id_key "
            "ON poi (external_id) WHERE external_id IS NOT NULL",
        ):
            cur.execute(ddl)

        # Seed the Southeast Asia destination set only when poi is empty, so
        # re-running this script leaves existing destinations untouched.
        cur.execute("SELECT count(*) FROM poi;")
        existing = cur.fetchone()[0]
        if existing:
            print(f"POI table already has {existing} rows — left untouched.")
        else:
            seed_path = os.path.join(os.path.dirname(__file__), "sql", "insert_poi.sql")
            with open(seed_path, encoding="utf-8") as f:
                cur.execute(f.read())
            cur.execute("SELECT count(*) FROM poi;")
            print(f"Seeded {cur.fetchone()[0]} POIs from sql/insert_poi.sql.")
            print("Run seed_food_data.py and seed_missing_data.py next for full coverage.")

        conn.commit()
        cur.close()
        conn.close()
        print("Database initialized successfully!")

    except Exception as e:
        print(f"Error initializing database: {e}")

if __name__ == "__main__":
    init_db()
