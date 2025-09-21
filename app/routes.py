from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from rapidfuzz import fuzz
from bson.objectid import ObjectId
from . import mongo

main = Blueprint("main", __name__)

# ================== HOME ===================
@main.route("/")
def home():
    if "user" in session:
        role = session.get("role")
        if role == "staff":
            # Fetch exams for staff dashboard
            exams = list(mongo.db.exams.find())
            return render_template("staff_dashboard.html", user=session["user"], exams=exams)
        elif role == "student":
            # Fetch exams for student dashboard
            exams = list(mongo.db.exams.find())
            return render_template("student_dashboard.html", user=session["user"], exams=exams)
    return render_template("index.html")

# ================== AUTH ===================
@main.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "student")

        if not username or not password:
            flash("Username and password are required!", "danger")
            return redirect(url_for("main.signup"))

        if mongo.db.users.find_one({"username": username}):
            flash("Username already exists!", "danger")
            return redirect(url_for("main.signup"))

        hashed_pw = generate_password_hash(password)
        mongo.db.users.insert_one({
            "username": username,
            "password": hashed_pw,
            "role": role
        })

        flash("Signup successful! Please login.", "success")
        return redirect(url_for("main.login"))

    return render_template("signup.html")


@main.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        user = mongo.db.users.find_one({"username": username})

        if user and check_password_hash(user["password"], password):
            session["user"] = username
            session["role"] = user.get("role", "student")
            flash("Login successful!", "success")
            return redirect(url_for("main.home"))
        else:
            flash("Invalid username or password", "danger")
            return redirect(url_for("main.login"))

    return render_template("login.html")


@main.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.home"))

# ================== STAFF: CREATE EXAM ===================
@main.route("/create_exam", methods=["GET", "POST"])
def create_exam():
    if "role" not in session or session["role"] != "staff":
        flash("Only staff can create exams.", "danger")
        return redirect(url_for("main.home"))

    if request.method == "POST":
        question = request.form.get("question", "").strip()
        key_answer = request.form.get("key_answer", "").strip()

        if not question or not key_answer:
            flash("Both question and key answer are required.", "danger")
            return redirect(url_for("main.create_exam"))

        mongo.db.exams.insert_one({
            "question": question,
            "key_answer": key_answer
        })

        flash("Exam created successfully!", "success")
        return redirect(url_for("main.home"))

    return render_template("create_exam.html")

# ================== STUDENT: TAKE EXAM ===================
@main.route("/take_exam/<exam_id>", methods=["GET", "POST"])
def take_exam(exam_id):
    if "role" not in session or session["role"] != "student":
        flash("Only students can take exams.", "danger")
        return redirect(url_for("main.home"))

    try:
        exam = mongo.db.exams.find_one({"_id": ObjectId(exam_id)})
    except Exception:
        exam = None

    if not exam:
        flash("Exam not found.", "danger")
        return redirect(url_for("main.home"))

    if request.method == "POST":
        student_answer = request.form.get("answer", "").strip()

        score = fuzz.ratio(student_answer.lower(), exam["key_answer"].lower())

        mongo.db.results.insert_one({
            "exam_id": str(exam["_id"]),
            "student": session["user"],
            "student_answer": student_answer,
            "score": score
        })

        flash(f"Exam submitted! Your score: {score}%", "info")
        return redirect(url_for("main.home"))

    return render_template("take_exam.html", exam=exam)

# ================== STAFF: VIEW RESULTS ===================
@main.route("/results/<exam_id>")
def results(exam_id):
    if "role" not in session or session["role"] != "staff":
        flash("Only staff can view results.", "danger")
        return redirect(url_for("main.home"))

    try:
        exam = mongo.db.exams.find_one({"_id": ObjectId(exam_id)})
    except Exception:
        exam = None

    if not exam:
        flash("Exam not found.", "danger")
        return redirect(url_for("main.home"))

    results = list(mongo.db.results.find({"exam_id": str(exam_id)}))
    return render_template("results.html", results=results, exam=exam)

# ================== LEADERBOARD ===================
@main.route("/leaderboard")
def leaderboard():
    pipeline = [
        {"$group": {"_id": "$student", "best_score": {"$max": "$score"}}},
        {"$sort": {"best_score": -1}},
        {"$limit": 10}
    ]
    leaderboard_data = list(mongo.db.results.aggregate(pipeline))

    formatted = [
        {"student": r["_id"], "score": r["best_score"]}
        for r in leaderboard_data if r["_id"] is not None
    ]

    return render_template("leaderboard.html", leaderboard=formatted)
