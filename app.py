import os
import re
import sys
import time
from datetime import datetime, timezone

import psycopg2
from flask import Flask, request, jsonify

app = Flask(__name__)

# Secrets from environment variables
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me-in-production")


def get_db_connection():
    """Get database connection using environment variables with retry."""
    last_error = None

    for attempt in range(5):
        try:
            conn = psycopg2.connect(
                host=os.environ.get("DB_HOST", "db"),
                database=os.environ.get("DB_NAME", "securecart"),
                user=os.environ.get("DB_USER", "postgres"),
                password=os.environ.get("DB_PASSWORD"),
                connect_timeout=5,
            )
            return conn
        except Exception as e:
            last_error = e
            print(f"DB connection attempt {attempt + 1} failed: {e}")
            time.sleep(2)

    raise Exception(f"DB connection failed after retries: {last_error}")


def init_db():
    """Initialize database with required tables."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    cur.close()
    conn.close()
    print("Database initialized successfully.")


def validate_email(email):
    """Basic email format validation."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def validate_username(username):
    """Username must be 3-80 alphanumeric characters or underscore."""
    pattern = r"^[a-zA-Z0-9_]{3,80}$"
    return re.match(pattern, username) is not None


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify(
        {
            "status": "healthy",
            "version": os.environ.get("APP_VERSION", "unknown"),
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )


@app.route("/api/users", methods=["GET"])
def get_users():
    """List all users."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, username, email, created_at FROM users ORDER BY id ASC")
        users = cur.fetchall()
        cur.close()
        conn.close()

        return jsonify(
            [
                {
                    "id": u[0],
                    "username": u[1],
                    "email": u[2],
                    "created_at": str(u[3]),
                }
                for u in users
            ]
        )
    except Exception as e:
        print(f"GET /api/users failed: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/users", methods=["POST"])
def create_user():
    """Create a new user with input validation."""
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body is required"}), 400

    username = data.get("username", "")
    email = data.get("email", "")
    password = data.get("password", "")

    if not username or not email or not password:
        return jsonify({"error": "username, email, and password are required"}), 400

    if not validate_username(username):
        return jsonify({"error": "Username must be 3-80 alphanumeric characters"}), 400

    if not validate_email(email):
        return jsonify({"error": "Invalid email format"}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s) RETURNING id",
            (username, email, password),
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"id": user_id, "username": username}), 201

    except psycopg2.IntegrityError:
        return jsonify({"error": "Username or email already exists"}), 409
    except Exception as e:
        print(f"POST /api/users failed: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/login", methods=["POST"])
def login():
    """Authenticate a user with parameterized queries."""
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body is required"}), 400

    username = data.get("username", "")
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, email FROM users WHERE username = %s AND password = %s",
            (username, password),
        )
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
            return jsonify(
                {
                    "message": "Login successful",
                    "user": {
                        "id": user[0],
                        "username": user[1],
                        "email": user[2],
                    },
                }
            )

        return jsonify({"error": "Invalid credentials"}), 401

    except Exception as e:
        print(f"POST /api/login failed: {e}")
        return jsonify({"error": "Internal server error"}), 500


# IMPORTANT:
# This runs when Gunicorn imports the app, so the users table gets created.
# Skip under pytest only (CI has no Postgres); env-based skips leak into Docker via the shell.
if "pytest" not in sys.modules:
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
