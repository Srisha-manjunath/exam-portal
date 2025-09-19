import os
import datetime
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient

# -----------------------------
# Flask App Config
# -----------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "exam-portal-secret")

# -----------------------------
# MongoDB Setup
# -----------------------------
MONGO_URI = os.environ.get(
    "MONGO_URI",
    "mongodb+srv://srisha1045:Jungk0ok-7@cluster0.muqelad.mongodb.net/exam_portal?retryWrites=true&w=majority&appName=Cluster0"
)

client = MongoClient(MONGO_URI)
db = client["exam_portal"]

# -----------------------------
# Logging Setup
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")

# -------- Student Login --------
@app.route("/login/student", methods=["GET", "POST"])
def login_student():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = db.users.find_one({"email": email, "role": "student"})
        if user and check_password_hash(user["password"], password):
            session["user_id"] = str(user["_id"])
            flash("Login successful!", "success")
            return redirect(url_for("student_dashboard"))
        else:
            flash("Invalid credentials", "danger")
    return render_template("login_student.html")

# -------- Staff Login --------
@app.route("/login/staff", methods=["GET", "POST"])
def login_staff():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = db.users.find_one({"email": email, "role": "staff"})
        if user and check_password_hash(user["password"], password):
            session["user_id"] = str(user["_id"])
            flash("Login successful!", "success")
            return redirect(url_for("staff_dashboard"))
        else:
            flash("Invalid credentials", "danger")
    return render_template("login_staff.html")

# -------- Register --------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role")  # student or staff

        if db.users.find_one({"email": email}):
            flash("Email already registered", "danger")
            return redirect(url_for("register"))

        hashed_pw = generate_password_hash(password)
        db.users.insert_one({
            "name": name,
            "email": email,
            "password": hashed_pw,
            "role": role,
            "created_at": datetime.datetime.utcnow()
        })
        flash("Registration successful, please log in.", "success")
        return redirect(url_for("login_student" if role == "student" else "login_staff"))

    return render_template("register.html")

# -------- Student Dashboard --------
@app.route("/dashboard/student")
def student_dashboard():
    if "user_id" not in session:
        return redirect(url_for("login_student"))
    return render_template("student_dashboard.html")

# -------- Staff Dashboard --------
@app.route("/dashboard/staff")
def staff_dashboard():
    if "user_id" not in session:
        return redirect(url_for("login_staff"))
    return render_template("staff_dashboard.html")

# -------- Logout --------
@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

# -----------------------------
# Run Server
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting Flask on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
