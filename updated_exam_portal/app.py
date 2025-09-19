from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os, datetime, uuid
try:
    from pymongo import MongoClient
    from bson import ObjectId as BObjectId
    mongo_available = True
except Exception:
    mongo_available = False

# sklearn fallback for auto-grading
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    sklearn_available = True
except Exception:
    sklearn_available = False

# password hashing - prefer werkzeug but fallback to PBKDF2
try:
    from werkzeug.security import generate_password_hash, check_password_hash
except Exception:
    import hashlib, binascii
    def generate_password_hash(password):
        salt = b"static-salt"
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
        return binascii.hexlify(dk).decode()
    def check_password_hash(hashed, password):
        return generate_password_hash(password) == hashed

# SocketIO
try:
    from flask_socketio import SocketIO, emit, join_room
    socketio_available = True
except Exception:
    socketio_available = False

# Simple in-memory collections as fallback (unchanged)
class MemoryCollection:
    def __init__(self):
        self._data = {}
    def find_one(self, q):
        if not q: return None
        if "_id" in q:
            return self._data.get(str(q["_id"]))
        if "username" in q:
            for v in self._data.values():
                if v.get("username") == q["username"]:
                    return v
        for v in self._data.values():
            match = True
            for k,val in q.items():
                if v.get(k) != val:
                    match = False; break
            if match: return v
        return None
    def insert_one(self, doc):
        _id = str(uuid.uuid4())
        d = dict(doc); d["_id"] = _id
        self._data[_id] = d
        class R: pass
        r = R(); r.inserted_id = _id
        return r
    def find(self, q=None):
        out = []
        for v in self._data.values():
            if not q:
                out.append(v)
            else:
                match = True
                for k,val in q.items():
                    if v.get(k) != val:
                        match = False; break
                if match: out.append(v)
        return out
    def update_one(self, q, update):
        d = self.find_one(q)
        if not d: return
        if "$set" in update:
            for k,v in update["$set"].items():
                d[k] = v

class DataStore:
    def __init__(self, uri=None):
        self.type = "memory"
        if mongo_available and uri:
            try:
                client = MongoClient(uri, serverSelectionTimeoutMS=2000)
                client.admin.command('ping')
                db = client['exam_portal']
                self.users = db.users
                self.exams = db.exams
                self.submissions = db.submissions
                self.ObjectId = BObjectId
                self.type = "mongo"
                print("Connected to MongoDB at", uri)
                return
            except Exception as e:
                print("Mongo connection failed:", e)
        self.users = MemoryCollection()
        self.exams = MemoryCollection()
        self.submissions = MemoryCollection()
        self.ObjectId = lambda x: x
        self.type = "memory"
        print("Using in-memory datastore")

MONGO_URI = os.environ.get("MONGO_URI")
db = DataStore(MONGO_URI)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY","dev-secret-key")

if socketio_available:
    socketio = SocketIO(app, cors_allowed_origins="*")
else:
    socketio = None

@app.context_processor
def inject_user():
    user = None
    if "user_id" in session:
        try:
            qid = db.ObjectId(session["user_id"])
        except Exception:
            qid = session["user_id"]
        user = db.users.find_one({"_id": qid})
    return {"current_user": user}

@app.route("/")
def index():
    return render_template("index.html")

# Registration (user chooses role)
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    username = request.form.get("username","").strip()
    password = request.form.get("password","")
    role = request.form.get("role","student")
    if not username or not password:
        flash("Username and password required"); return redirect(url_for("register"))
    if db.users.find_one({"username": username}):
        flash("Username already exists"); return redirect(url_for("register"))
    hashed = generate_password_hash(password)
    res = db.users.insert_one({"username": username, "password": hashed, "role": role, "created_at": datetime.datetime.utcnow()})
    session["user_id"] = str(res.inserted_id)
    flash("Registered"); 
    # Redirect to role-specific dashboard
    if role == "staff":
        return redirect(url_for("staff_dashboard"))
    return redirect(url_for("student_dashboard"))

# Separate login routes for student and staff
@app.route("/login/student", methods=["GET","POST"])
def login_student():
    if request.method == "GET":
        return render_template("login_student.html")
    username = request.form.get("username",""); password = request.form.get("password","")
    user = db.users.find_one({"username": username, "role": "student"})
    if not user or not check_password_hash(user.get("password",""), password):
        flash("Invalid student credentials"); return redirect(url_for("login_student"))
    session["user_id"] = str(user.get("_id")); flash("Logged in as student"); return redirect(url_for("student_dashboard"))

@app.route("/login/staff", methods=["GET","POST"])
def login_staff():
    if request.method == "GET":
        return render_template("login_staff.html")
    username = request.form.get("username",""); password = request.form.get("password","")
    user = db.users.find_one({"username": username, "role": "staff"})
    if not user or not check_password_hash(user.get("password",""), password):
        flash("Invalid staff credentials"); return redirect(url_for("login_staff"))
    session["user_id"] = str(user.get("_id")); flash("Logged in as staff"); return redirect(url_for("staff_dashboard"))

# Dashboard endpoints - role protected
@app.route("/dashboard/student")
def student_dashboard():
    if "user_id" not in session: return redirect(url_for("login_student"))
    try:
        qid = db.ObjectId(session["user_id"])
    except Exception:
        qid = session["user_id"]
    user = db.users.find_one({"_id": qid})
    if not user or user.get("role") != "student": session.clear(); return redirect(url_for("login_student"))
    exams = db.exams.find()
    # compute total and rank
    totals = {}
    for s in db.submissions.find():
        sid = s.get("student_id")
        totals[sid] = totals.get(sid, 0) + s.get("marks_obtained",0)
    totals_list = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    rank = None
    for i,(sid,score) in enumerate(totals_list, start=1):
        if sid == session["user_id"]:
            rank = i; break
    total = sum([s.get("marks_obtained",0) for s in db.submissions.find({"student_id": session["user_id"]})])
    return render_template("student_dashboard.html", user=user, exams=exams, rank=rank or "N/A", total=total)

@app.route("/dashboard/staff")
def staff_dashboard():
    if "user_id" not in session: return redirect(url_for("login_staff"))
    try:
        qid = db.ObjectId(session["user_id"])
    except Exception:
        qid = session["user_id"]
    user = db.users.find_one({"_id": qid})
    if not user or user.get("role") != "staff": session.clear(); return redirect(url_for("login_staff"))
    exams = db.exams.find()
    return render_template("staff_dashboard.html", user=user, exams=exams)

# Staff creates exam
@app.route("/exams/create", methods=["GET","POST"])
def create_exam():
    if "user_id" not in session: return redirect(url_for("login_staff"))
    try: user = db.users.find_one({"_id": db.ObjectId(session["user_id"])}) if mongo_available else db.users.find_one({"_id": session["user_id"]})
    except Exception:
        user = db.users.find_one({"_id": session["user_id"]})
    if not user or user.get("role") != "staff": flash("Unauthorized"); return redirect(url_for("staff_dashboard"))
    if request.method == "GET": return render_template("create_exam.html")
    title = request.form.get("title","").strip()
    description = request.form.get("description","").strip()
    questions = []
    q_texts = request.form.getlist("qtext[]")
    q_keys = request.form.getlist("qkey[]")
    q_marks = request.form.getlist("qmarks[]")
    for i,qt in enumerate(q_texts):
        questions.append({"text": qt, "key": q_keys[i] if i < len(q_keys) else "", "marks": int(q_marks[i]) if i < len(q_marks) and q_marks[i].isdigit() else 1})
    exam = {"title": title, "description": description, "questions": questions, "created_by": session["user_id"], "created_at": datetime.datetime.utcnow()}
    res = db.exams.insert_one(exam)
    flash("Exam created"); return redirect(url_for("staff_dashboard"))

@app.route("/exams")
def exams_list():
    exams = db.exams.find()
    return render_template("exams_list.html", exams=exams)

@app.route("/exams/<exam_id>/take", methods=["GET","POST"])
def take_exam(exam_id):
    if "user_id" not in session: return redirect(url_for("login_student"))
    try:
        exam = db.exams.find_one({"_id": db.ObjectId(exam_id)}) if mongo_available else db.exams.find_one({"_id": exam_id})
    except Exception:
        exam = db.exams.find_one({"_id": exam_id})
    if not exam: flash("Exam not found"); return redirect(url_for("student_dashboard"))
    if request.method == "GET":
        return render_template("take_exam.html", exam=exam)
    answers = request.form.getlist("answer[]")
    total_marks = 0; obtained = 0; submission_questions = []
    for i,q in enumerate(exam.get("questions",[])):
        key = q.get("key",""); maxm = q.get("marks",1); ans = answers[i] if i < len(answers) else ""
        score = 0.0
        if key and ans.strip():
            score = auto_grade_text(key, ans, maxm)
        submission_questions.append({"q": q.get("text"), "answer": ans, "marks": score, "max": maxm})
        obtained += score; total_marks += maxm
    sub = {"exam_id": exam.get("_id"), "student_id": session["user_id"], "answers": submission_questions, "marks_obtained": obtained, "max_marks": total_marks, "submitted_at": datetime.datetime.utcnow()}
    db.submissions.insert_one(sub)
    flash(f"Submitted. Marks: {obtained}/{total_marks}")
    # notify staff
    if socketio_available and socketio:
        socketio.emit("submission", {"exam_id": exam.get("_id"), "student": session["user_id"], "marks": obtained}, room="staff")
    return redirect(url_for("student_dashboard"))

@app.route("/exams/<exam_id>/submissions")
def view_submissions(exam_id):
    if "user_id" not in session: return redirect(url_for("login_staff"))
    try: user = db.users.find_one({"_id": db.ObjectId(session["user_id"])}) if mongo_available else db.users.find_one({"_id": session["user_id"]})
    except Exception:
        user = db.users.find_one({"_id": session["user_id"]})
    if not user or user.get("role") != "staff": flash("Unauthorized"); return redirect(url_for("staff_dashboard"))
    subs = [s for s in db.submissions.find() if s.get("exam_id") == exam_id]
    return render_template("submissions.html", submissions=subs, exam_id=exam_id)

def auto_grade_text(key, ans, max_marks):
    if sklearn_available:
        try:
            vec = TfidfVectorizer().fit_transform([key, ans])
            sim = cosine_similarity(vec[0:1], vec[1:2])[0][0]
            return round(sim * max_marks, 2)
        except Exception:
            pass
    import difflib
    r = difflib.SequenceMatcher(None, key.lower(), ans.lower()).ratio()
    return round(r * max_marks, 2)

@app.route("/exams/<exam_id>/leaderboard")
def leaderboard(exam_id):
    subs = [s for s in db.submissions.find() if s.get("exam_id") == exam_id]
    ranked = sorted(subs, key=lambda x: x.get("marks_obtained",0), reverse=True)
    return render_template("leaderboard.html", submissions=ranked)

@app.route("/logout")
def logout():
    session.clear(); flash("Logged out"); return redirect(url_for("index"))

# SocketIO events
if socketio_available and socketio:
    @socketio.on("join_staff")
    def on_join_staff(data):
        join_room("staff")
        emit("joined", {"msg": "joined staff"})

    @socketio.on("student_tab_switch")
    def on_student_tab_switch(data):
        emit("tab_switch", data, room="staff")

if __name__ == "__main__":
    if socketio_available and socketio:
        socketio.run(app, debug=True, host="0.0.0.0", port=5001)
    else:
        app.run(debug=True, host="0.0.0.0", port=5001)
