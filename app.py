from functools import wraps
from pathlib import Path
import os
import sqlite3

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "local-secret-key")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "local_services.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'customer', 'provider')),
            full_name TEXT NOT NULL,
            phone TEXT,
            city TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            city TEXT NOT NULL,
            price TEXT,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected', 'disabled')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(provider_id) REFERENCES users(id)
        )
        """
    )
    conn.commit()

    admin_exists = conn.execute(
        "SELECT 1 FROM users WHERE username = ?",
        ("admin",),
    ).fetchone()

    if not admin_exists:
        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, full_name, phone, city)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "admin",
                generate_password_hash("admin123"),
                "admin",
                "System Admin",
                "0000000000",
                "Remote City",
            ),
        )
        conn.commit()

    conn.close()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(user) if user else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def role_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            if user["role"] not in allowed_roles:
                flash("You do not have permission to view that page.", "danger")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


@app.route("/")
def index():
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    city = request.args.get("city", "").strip()

    conn = get_db()
    categories = [
        row["category"]
        for row in conn.execute(
            "SELECT DISTINCT category FROM services WHERE status = 'approved' ORDER BY category"
        ).fetchall()
    ]

    sql = """
        SELECT s.*, u.full_name AS provider_name, u.phone AS provider_phone, u.city AS provider_city
        FROM services s
        JOIN users u ON u.id = s.provider_id
        WHERE s.status = 'approved'
    """
    params = []

    if query:
        search_term = f"%{query.lower()}%"
        sql += """
            AND (
                LOWER(s.title) LIKE ? OR
                LOWER(s.category) LIKE ? OR
                LOWER(s.description) LIKE ? OR
                LOWER(u.full_name) LIKE ?
            )
        """
        params.extend([search_term, search_term, search_term, search_term])

    if category:
        sql += " AND LOWER(s.category) = ?"
        params.append(category.lower())

    if city:
        city_term = f"%{city.lower()}%"
        sql += " AND (LOWER(s.city) LIKE ? OR LOWER(u.city) LIKE ?)"
        params.extend([city_term, city_term])

    sql += " ORDER BY s.created_at DESC"

    services = conn.execute(sql, params).fetchall()
    conn.close()

    context = {
        "services": [dict(row) for row in services],
        "user": current_user(),
        "categories": categories,
        "query": query,
        "category": category,
        "city": city,
    }
    return render_template("index.html", **context)


@app.route("/service/<int:service_id>")
def service_detail(service_id):
    conn = get_db()
    service = conn.execute(
        """
        SELECT s.*, u.full_name AS provider_name, u.phone AS provider_phone, u.city AS provider_city
        FROM services s
        JOIN users u ON u.id = s.provider_id
        WHERE s.id = ? AND s.status = 'approved'
        """,
        (service_id,),
    ).fetchone()
    conn.close()

    if not service:
        flash("Service not found.", "danger")
        return redirect(url_for("index"))

    return render_template(
        "service_detail.html",
        service=dict(service),
        user=current_user(),
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    user = current_user()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        city = request.form.get("city", "").strip()
        role = request.form.get("role", "customer")

        if not all([username, password, full_name, city]):
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("register"))

        if role not in {"customer", "provider"}:
            flash("Invalid user role selected.", "danger")
            return redirect(url_for("register"))

        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        if existing:
            conn.close()
            flash("That username is already taken.", "danger")
            return redirect(url_for("register"))

        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, full_name, phone, city)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                generate_password_hash(password),
                role,
                full_name,
                phone,
                city,
            ),
        )
        conn.commit()
        new_user = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        conn.close()

        session["user_id"] = new_user["id"]
        flash("Account created successfully.", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html", user=user)


@app.route("/login", methods=["GET", "POST"])
def login():
    user = current_user()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        account = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        conn.close()

        if account and check_password_hash(account["password_hash"], password):
            session["user_id"] = account["id"]
            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "danger")
        return redirect(url_for("login"))

    return render_template("login.html", user=user)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    conn = get_db()

    if user["role"] == "admin":
        users = conn.execute(
            "SELECT id, username, role, full_name, phone, city FROM users ORDER BY created_at DESC"
        ).fetchall()
        services = conn.execute(
            """
            SELECT s.*, u.full_name AS provider_name, u.phone AS provider_phone, u.city AS provider_city
            FROM services s
            JOIN users u ON u.id = s.provider_id
            ORDER BY s.created_at DESC
            """
        ).fetchall()
        return render_template(
            "dashboard.html",
            user=user,
            users=[dict(row) for row in users],
            services=[dict(row) for row in services],
            view_mode="admin",
        )

    if user["role"] == "provider":
        services = conn.execute(
            """
            SELECT s.*
            FROM services s
            WHERE s.provider_id = ?
            ORDER BY s.created_at DESC
            """,
            (user["id"],),
        ).fetchall()
        return render_template(
            "dashboard.html",
            user=user,
            services=[dict(row) for row in services],
            view_mode="provider",
        )

    services = conn.execute(
        """
        SELECT s.*, u.full_name AS provider_name, u.phone AS provider_phone, u.city AS provider_city
        FROM services s
        JOIN users u ON u.id = s.provider_id
        WHERE s.status = 'approved'
        ORDER BY s.created_at DESC
        """
    ).fetchall()
    conn.close()
    return render_template(
        "dashboard.html",
        user=user,
        services=[dict(row) for row in services],
        view_mode="customer",
    )


@app.route("/service/add", methods=["POST"])
@login_required
@role_required("provider")
def add_service():
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    city = request.form.get("city", "").strip()
    price = request.form.get("price", "").strip()

    if not all([title, category, description, city]):
        flash("Please complete all required service fields.", "danger")
        return redirect(url_for("dashboard"))

    user = current_user()
    conn = get_db()
    conn.execute(
        """
        INSERT INTO services (provider_id, title, category, description, city, price, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """,
        (user["id"], title, category, description, city, price),
    )
    conn.commit()
    conn.close()

    flash("Service submitted successfully and is now pending admin approval.", "success")
    return redirect(url_for("dashboard"))


@app.route("/service/<int:service_id>/status/<status>", methods=["POST"])
@login_required
@role_required("admin")
def update_service_status(service_id, status):
    allowed_statuses = {"pending", "approved", "rejected", "disabled"}
    if status not in allowed_statuses:
        flash("Invalid service status.", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db()
    conn.execute(
        "UPDATE services SET status = ? WHERE id = ?",
        (status, service_id),
    )
    conn.commit()
    conn.close()

    flash(f"Service status updated to {status}.", "success")
    return redirect(url_for("dashboard"))


@app.route("/service/<int:service_id>/delete", methods=["POST"])
@login_required
def delete_service(service_id):
    user = current_user()
    conn = get_db()
    service = conn.execute(
        "SELECT provider_id FROM services WHERE id = ?",
        (service_id,),
    ).fetchone()

    if not service:
        conn.close()
        flash("Service not found.", "danger")
        return redirect(url_for("dashboard"))

    can_delete = user["role"] == "admin" or (
        user["role"] == "provider" and service["provider_id"] == user["id"]
    )

    if can_delete:
        conn.execute("DELETE FROM services WHERE id = ?", (service_id,))
        conn.commit()
        conn.close()
        flash("Service deleted successfully.", "success")
    else:
        conn.close()
        flash("You are not allowed to delete this service.", "danger")

    return redirect(url_for("dashboard"))


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
