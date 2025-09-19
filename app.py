from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os, datetime, uuid, logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# -----------------------------
# Logging setup
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# MongoDB Connection
# -----------------------------
try:
    from pymongo import MongoClient
    from bson import ObjectId as BObjectId
    mongo_available = True
except Exception as e:
    logger.error(f"MongoDB modules not available: {e}")
    mongo_available = False

# -----------------------------
# Sklearn (auto-grading)
# -----------------------------
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    sklearn_available = True
    logger.info("Scikit-learn available")
except Exception as e:
    sklearn_available = False
    logger.warning(f"Scikit-learn not available: {e}")

# -----------------------------
# Password hashing
# -----------------------------
try:
    from werkzeug.security import generate_password_hash, check_password_hash
    logger.info("Werkzeug security available")
except Exception:
    import hashlib, binascii
    def generate_password_hash(password):
        salt = b"static-salt-2024-secure"
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
        return binascii.hexlify(dk).decode()
    def check_password_hash(hashed, password):
        return generate_password_hash(password) == hashed

# -----------------------------
# SocketIO
# -----------------------------
try:
    from flask_socketio import SocketIO, emit, join_room
    socketio_available = True
    logger.info("SocketIO available")
except Exception as e:
    socketio_available = False
    logger.warning(f"SocketIO not available: {e}")

# -----------------------------
# In-memory fallback
# -----------------------------
class MemoryCollection:
    def __init__(self):
        self._data = {}
        self._counter = 0
    
    def find_one(self, q):
        for v in self._data.values():
            if all(v.get(k) == val for k, val in q.items()):
                return v
        return None
    
    def insert_one(self, doc):
        self._counter += 1
        _id = f"mem_{self._counter}_{uuid.uuid4().hex[:8]}"
        d = dict(doc)
        d["_id"] = _id
        self._data[_id] = d
        class Result: 
            def __init__(self, inserted_id): self.inserted_id = inserted_id
        return Result(_id)
    
    def find(self, q=None):
        return list(self._data.values())
    
    def update_one(self, q, update):
        d = self.find_one(q)
        if d and "$set" in update:
            d.update(update["$set"])
            self._data[d["_id"]] = d

class DataStore:
    def __init__(self, uri=None):
        self.type = "memory"
        if mongo_available and uri:
            try:
                client = MongoClient(uri, serverSelectionTimeoutMS=5000)
                client.admin.command("ping")  # test connection
                db = client["exam_portal"]
                self.users = db.users
                self.exams = db.exams
                self.submissions = db.submissions
                self.ObjectId = BObjectId
                self.type = "mongo"
                logger.info("✅ Connected to MongoDB")
                return
            except Exception as e:
                logger.error(f"MongoDB connection failed: {e}")
        # fallback
        self.users = MemoryCollection()
        self.exams = MemoryCollection()
        self.submissions = MemoryCollection()
        self.ObjectId = lambda x: str(x)
        logger.info("⚠ Using in-memory datastore")

# -----------------------------
# App + DB + SocketIO init
# -----------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")

MONGO_URI = os.getenv("MONGO_URI")
db = DataStore(MONGO_URI)

socketio = None
if socketio_available:
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# -----------------------------
# Context processor
# -----------------------------
@app.context_processor
def inject_user():
    user = None
    if "user_id" in session:
        try:
            qid = db.ObjectId(session["user_id"]) if db.type == "mongo" else session["user_id"]
            user = db.users.find_one({"_id": qid})
        except Exception as e:
            logger.error(f"Session user fetch failed: {e}")
            session.pop("user_id", None)
    return {"current_user": user}

# -----------------------------
# Routes (keep your existing ones)
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/health")
def health_check():
    return jsonify({
        "status": "healthy",
        "database": db.type,
        "socketio": socketio_available,
        "sklearn": sklearn_available
    })

# (⚡ Keep your register, login, dashboards, exams, submissions, leaderboard, logout routes here — unchanged)
# I did not delete any — just shortened this snippet for readability.

# -----------------------------
# SocketIO events
# -----------------------------
if socketio:
    @socketio.on("join_staff")
    def on_join_staff(data):
        join_room("staff")
        emit("joined", {"msg": "Joined staff notifications"})

    @socketio.on("student_tab_switch")
    def on_student_tab_switch(data):
        emit("tab_switch", data, room="staff")

# -----------------------------
# Error handlers
# -----------------------------
@app.errorhandler(404)
def not_found(error):
    return render_template("index.html"), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {error}")
    session.clear()
    return redirect(url_for("index"))

# -----------------------------
# Startup
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    if socketio:
        logger.info(f"Starting with SocketIO on port {port}")
        socketio.run(app, host="0.0.0.0", port=port, debug=False)
    else:
        logger.info(f"Starting Flask only on port {port}")
        app.run(host="0.0.0.0", port=port, debug=False)
