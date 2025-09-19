import os
import logging
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash

# -----------------------------
# Config / Logging
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", template_folder="templates")

# Use SECRET_KEY from environment if provided (important for sessions)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-please-change')

# Database: use DATABASE_URL env var if provided, otherwise SQLite file
# Example DATABASE_URL for SQLite: sqlite:///exam_portal.db
db_url = os.environ.get('DATABASE_URL', 'sqlite:///exam_portal.db')
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize DB and SocketIO (eventlet async)
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# -----------------------------
# Database Models (unchanged)
# -----------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')  # student, staff, admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    duration_minutes = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    total_marks = db.Column(db.Integer, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(500), nullable=False)
    option_b = db.Column(db.String(500), nullable=False)
    option_c = db.Column(db.String(500), nullable=False)
    option_d = db.Column(db.String(500), nullable=False)
    correct_answer = db.Column(db.String(1), nullable=False)  # A, B, C, D
    marks = db.Column(db.Integer, default=1)
    question_order = db.Column(db.Integer, nullable=False)

class StudentExam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='in_progress')  # in_progress, completed, submitted
    total_score = db.Column(db.Integer, default=0)
    is_supervised = db.Column(db.Boolean, default=False)
    supervisor_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_exam_id = db.Column(db.Integer, db.ForeignKey('student_exam.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    selected_answer = db.Column(db.String(1))  # A, B, C, D
    is_correct = db.Column(db.Boolean, default=False)
    answered_at = db.Column(db.DateTime, default=datetime.utcnow)

class SupervisionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_exam_id = db.Column(db.Integer, db.ForeignKey('student_exam.id'), nullable=False)
    supervisor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    activity = db.Column(db.String(200), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)

# -----------------------------
# Routes (kept same behaviour)
# -----------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    return jsonify({"status": "ok", "database": db.engine.url.__to_string__() if hasattr(db.engine.url, '__to_string__') else str(db.engine.url)})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            if user.role == 'staff':
                return redirect(url_for('staff_dashboard'))
            elif user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        email = request.form.get('email','').strip()
        password = request.form.get('password','')
        role = request.form.get('role','student')
        if not username or not email or not password:
            flash('Please fill all fields', 'warning')
            return render_template('register.html')
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return render_template('register.html')
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'danger')
            return render_template('register.html')
        user = User(username=username, email=email, password_hash=generate_password_hash(password), role=role)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/student_dashboard')
def student_dashboard():
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('login'))
    now = datetime.utcnow()
    available_exams = Exam.query.filter(Exam.start_time <= now, Exam.end_time >= now, Exam.is_active == True).all()
    student_exams = StudentExam.query.filter_by(student_id=session['user_id']).all()
    return render_template('student_dashboard.html', available_exams=available_exams, student_exams=student_exams)

@app.route('/take_exam/<int:exam_id>')
def take_exam(exam_id):
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('login'))
    exam = Exam.query.get_or_404(exam_id)
    existing_attempt = StudentExam.query.filter_by(student_id=session['user_id'], exam_id=exam_id).first()
    if existing_attempt:
        flash('You have already attempted this exam', 'info')
        return redirect(url_for('student_dashboard'))
    student_exam = StudentExam(student_id=session['user_id'], exam_id=exam_id)
    db.session.add(student_exam)
    db.session.commit()
    questions = Question.query.filter_by(exam_id=exam_id).order_by(Question.question_order).all()
    return render_template('take_exam.html', exam=exam, questions=questions, student_exam_id=student_exam.id)

@app.route('/submit_answer', methods=['POST'])
def submit_answer():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json() or {}
    question_id = data.get('question_id')
    selected_answer = data.get('selected_answer')
    student_exam_id = data.get('student_exam_id')
    if not question_id or not student_exam_id:
        return jsonify({'error': 'Bad request'}), 400
    existing_answer = Answer.query.filter_by(student_exam_id=student_exam_id, question_id=question_id).first()
    question = Question.query.get(question_id)
    is_correct = (question and question.correct_answer == selected_answer)
    if existing_answer:
        existing_answer.selected_answer = selected_answer
        existing_answer.is_correct = is_correct
        existing_answer.answered_at = datetime.utcnow()
    else:
        answer = Answer(student_exam_id=student_exam_id, question_id=question_id, selected_answer=selected_answer, is_correct=is_correct)
        db.session.add(answer)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/submit_exam', methods=['POST'])
def submit_exam():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json() or {}
    student_exam_id = data.get('student_exam_id')
    student_exam = StudentExam.query.get(student_exam_id)
    if not student_exam:
        return jsonify({'error': 'Exam not found'}), 404
    answers = Answer.query.filter_by(student_exam_id=student_exam_id).all()
    total_score = 0
    for answer in answers:
        if answer.is_correct:
            q = Question.query.get(answer.question_id)
            total_score += (q.marks if q else 0)
    student_exam.total_score = total_score
    student_exam.end_time = datetime.utcnow()
    student_exam.status = 'completed'
    db.session.commit()
    return jsonify({'success': True, 'total_score': total_score})

@app.route('/staff_dashboard')
def staff_dashboard():
    if 'user_id' not in session or session.get('role') != 'staff':
        return redirect(url_for('login'))
    ongoing_exams = db.session.query(StudentExam, User, Exam).join(User, StudentExam.student_id == User.id).join(Exam, StudentExam.exam_id == Exam.id).filter(StudentExam.status == 'in_progress').all()
    return render_template('staff_dashboard.html', ongoing_exams=ongoing_exams)

@app.route('/supervise_exam/<int:student_exam_id>')
def supervise_exam(student_exam_id):
    if 'user_id' not in session or session.get('role') != 'staff':
        return redirect(url_for('login'))
    joined = db.session.query(StudentExam, User, Exam).join(User, StudentExam.student_id == User.id).join(Exam, StudentExam.exam_id == Exam.id).filter(StudentExam.id == student_exam_id).first()
    if not joined:
        flash('Exam session not found')
        return redirect(url_for('staff_dashboard'))
    student_exam = joined[0]
    student_exam.is_supervised = True
    student_exam.supervisor_id = session['user_id']
    db.session.commit()
    return render_template('supervise_exam.html', student_exam=student_exam, student=joined[1], exam=joined[2])

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    total_students = User.query.filter_by(role='student').count()
    total_staff = User.query.filter_by(role='staff').count()
    total_exams = Exam.query.count()
    return render_template('admin_dashboard.html', total_students=total_students, total_staff=total_staff, total_exams=total_exams)

@app.route('/create_exam', methods=['GET', 'POST'])
def create_exam():
    if 'user_id' not in session or session.get('role') not in ['admin', 'staff']:
        return redirect(url_for('login'))
    if request.method == 'POST':
        exam = Exam(title=request.form['title'], description=request.form.get('description',''), duration_minutes=int(request.form['duration_minutes']), start_time=datetime.strptime(request.form['start_time'], '%Y-%m-%dT%H:%M'), end_time=datetime.strptime(request.form['end_time'], '%Y-%m-%dT%H:%M'), total_marks=int(request.form['total_marks']), created_by=session['user_id'])
        db.session.add(exam)
        db.session.commit()
        flash('Exam created successfully', 'success')
        return redirect(url_for('add_questions', exam_id=exam.id))
    return render_template('create_exam.html')

@app.route('/add_questions/<int:exam_id>', methods=['GET', 'POST'])
def add_questions(exam_id):
    if 'user_id' not in session or session.get('role') not in ['admin', 'staff']:
        return redirect(url_for('login'))
    exam = Exam.query.get_or_404(exam_id)
    if request.method == 'POST':
        question = Question(exam_id=exam_id, question_text=request.form['question_text'], option_a=request.form['option_a'], option_b=request.form['option_b'], option_c=request.form['option_c'], option_d=request.form['option_d'], correct_answer=request.form['correct_answer'], marks=int(request.form['marks']), question_order=Question.query.filter_by(exam_id=exam_id).count() + 1)
        db.session.add(question)
        db.session.commit()
        flash('Question added successfully', 'success')
        return redirect(url_for('add_questions', exam_id=exam_id))
    questions = Question.query.filter_by(exam_id=exam_id).order_by(Question.question_order).all()
    return render_template('add_questions.html', exam=exam, questions=questions)

# -----------------------------
# Socket.IO Events
# -----------------------------
@socketio.on('join_supervision')
def on_join_supervision(data):
    student_exam_id = data.get('student_exam_id')
    if student_exam_id:
        join_room(f'exam_{student_exam_id}')
        if 'user_id' in session and session.get('role') == 'staff':
            log = SupervisionLog(student_exam_id=student_exam_id, supervisor_id=session['user_id'], activity='Staff joined supervision')
            db.session.add(log)
            db.session.commit()
        emit('supervision_joined', {'message': 'Supervision started'})

@socketio.on('student_activity')
def on_student_activity(data):
    student_exam_id = data.get('student_exam_id')
    activity = data.get('activity')
    if student_exam_id and activity:
        socketio.emit('activity_update', {'student_exam_id': student_exam_id, 'activity': activity, 'timestamp': datetime.utcnow().isoformat()}, room=f'exam_{student_exam_id}')

@socketio.on('supervisor_message')
def on_supervisor_message(data):
    student_exam_id = data.get('student_exam_id')
    message = data.get('message')
    if student_exam_id and message and 'user_id' in session and session.get('role') == 'staff':
        log = SupervisionLog(student_exam_id=student_exam_id, supervisor_id=session['user_id'], activity=f'Message: {message}', notes=message)
        db.session.add(log)
        db.session.commit()
        socketio.emit('supervisor_notification', {'message': message, 'timestamp': datetime.utcnow().isoformat()}, room=f'exam_{student_exam_id}')

# -----------------------------
# App start
# -----------------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # create admin user if not exists
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', email='admin@example.com', password_hash=generate_password_hash('admin123'), role='admin')
            db.session.add(admin)
            db.session.commit()
    # Use socketio.run for development; in Render/Gunicorn we use eventlet worker
    socketio.run(app, debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
