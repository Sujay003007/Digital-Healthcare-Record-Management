"""
Digital Health Record Management System for Migrant Workers
QR-Based Health Identity - Flask Backend
"""

import os
import socket
import uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, send_file, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
import qrcode

from models import db, User, Worker, Vaccination, Document, Prescription, PrescriptionMedicine, Problem

# ---------------------------------------------------------------------------
# App & Config
# ---------------------------------------------------------------------------
app = Flask(__name__)
# Trust X-Forwarded-* headers (ngrok, cloudflare, load balancers) so URLs work from any network
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max for uploads
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)  # Doctor (and admin) session: 8 hours

QR_CODES_DIR = os.path.join(app.static_folder, 'qr_codes')
UPLOADS_DIR = os.path.join(app.static_folder, 'uploads')
PRESCRIPTIONS_PDF_DIR = os.path.join(app.static_folder, 'uploads', 'prescriptions')
os.makedirs(QR_CODES_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(PRESCRIPTIONS_PDF_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[-1].lower() in ALLOWED_EXTENSIONS

db.init_app(app)

# ---------------------------------------------------------------------------
# Flask-Login
# ---------------------------------------------------------------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def admin_required(f):
    """Restrict route to admin role only."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or getattr(current_user, 'role', None) != 'admin':
            flash('Admin access required.', 'warning')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


def doctor_required(f):
    """Restrict route to doctor role only."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or getattr(current_user, 'role', None) != 'doctor':
            flash('Doctor access required.', 'warning')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


def patient_login_required(f):
    """Restrict route to logged-in patient portal (Worker) using session key."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('patient_worker_id'):
            flash('Please log in as patient to access this page.', 'warning')
            return redirect(url_for('patient_login'))
        return f(*args, **kwargs)
    return decorated

def _display_doctor_id(user):
    """Return doctor_id for display; manual if set, else fallback DOC<id>."""
    if not user or getattr(user, 'role', None) != 'doctor':
        return ''
    did = getattr(user, 'doctor_id', None)
    return (did and str(did).strip()) or f'DOC{user.id}'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_local_ip():
    """Get this machine's local network IP so mobile can reach the app when scanning QR."""
    # Method 1: connect to external host to find outbound interface (works on most systems)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and ip not in ("127.0.0.1", "0.0.0.0"):
            return ip
    except Exception:
        pass
    # Method 2: iterate network interfaces (fallback for Windows/VPN edge cases)
    try:
        import socket as sock
        hostname = sock.gethostname()
        for addr in sock.getaddrinfo(hostname, None, sock.AF_INET):
            ip = addr[4][0]
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass
    return None


def get_base_url_for_qr():
    """
    Base URL for QR codes and share links. Works from any network:
    - If PUBLIC_URL env is set (e.g. when deployed), use that.
    - If behind a proxy (ngrok, cloud), request has real host → use it.
    - If localhost, use local IP so same-WiFi scan works (never use 127.0.0.1 in QR).
    """
    public_url = os.environ.get('PUBLIC_URL', '').strip()
    if public_url:
        return public_url.rstrip('/')
    if request and request.host:
        host = request.host.split(":")[0]
        port = request.host.split(":")[-1] if ":" in request.host else "5000"
        if host in ("localhost", "127.0.0.1"):
            local_ip = get_local_ip()
            if local_ip:
                return f"http://{local_ip}:{port}"
            # No reachable IP - return request host but QR will not work from phone
        # Behind proxy (ngrok, cloud) or already public host
        scheme = request.environ.get('HTTP_X_FORWARDED_PROTO', request.scheme)
        return f"{scheme}://{request.host}".rstrip("/")
    if request:
        return request.url_root.rstrip("/")
    return "http://localhost:5000"


def is_local_url(url):
    """True if URL is local (same WiFi only); QR scan from another network (e.g. mobile data) will not work."""
    if not url:
        return True
    url = url.lower()
    return (
        url.startswith('http://127.') or
        url.startswith('http://localhost') or
        url.startswith('http://192.168.') or
        url.startswith('http://10.') or
        url.startswith('http://172.16.') or url.startswith('http://172.17.') or
        url.startswith('http://172.18.') or url.startswith('http://172.19.') or
        (url.startswith('http://172.') and len(url) >= 12)
    )


def generate_qr_for_worker(worker_id, base_url=None):
    """Generate QR code image linking to worker profile. Returns relative path."""
    if base_url is None:
        base_url = get_base_url_for_qr()
    profile_url = f"{base_url}/profile/{worker_id}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(profile_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#0d6efd', back_color='white')
    filename = f"worker_{worker_id}.png"
    filepath = os.path.join(QR_CODES_DIR, filename)
    img.save(filepath)
    return f"qr_codes/{filename}"


def validate_worker_form(data):
    """Validate worker registration form. Returns (is_valid, error_message)."""
    name = (data.get('name') or '').strip()
    age = data.get('age')
    gender = (data.get('gender') or '').strip()
    phone = (data.get('phone') or '').strip()
    address = (data.get('address') or '').strip()
    blood_group = (data.get('blood_group') or '').strip()
    if not name or len(name) < 2:
        return False, 'Name must be at least 2 characters.'
    try:
        age = int(age)
        if age < 1 or age > 120:
            return False, 'Age must be between 1 and 120.'
    except (TypeError, ValueError):
        return False, 'Invalid age.'
    if not gender:
        return False, 'Gender is required.'
    if not phone or len(phone) < 6:
        return False, 'Valid phone number is required.'
    if not address or len(address) < 5:
        return False, 'Address must be at least 5 characters.'
    if not blood_group:
        return False, 'Blood group is required.'
    return True, None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    """Landing: choose Admin or Doctor login."""
    if current_user.is_authenticated:
        if getattr(current_user, 'role', None) == 'doctor':
            return redirect(url_for('doctor_dashboard'))
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated and getattr(current_user, 'role', None) == 'admin':
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        if not username or not password:
            flash('Username and password are required.', 'danger')
            return render_template('login_admin.html')
        user = User.query.filter_by(username=username, role='admin').first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            session.permanent = True
            flash(f'Welcome, {user.username}.', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid admin username or password.', 'danger')
    return render_template('login_admin.html')


@app.route('/doctor/login', methods=['GET', 'POST'])
def doctor_login():
    if current_user.is_authenticated and getattr(current_user, 'role', None) == 'doctor':
        return redirect(url_for('doctor_dashboard'))
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        if not username or not password:
            flash('Username and password are required.', 'danger')
            return render_template('login_doctor.html')
        user = User.query.filter_by(username=username, role='doctor').first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            session.permanent = True
            flash(f'Welcome, Dr. {user.username}. Session active for 8 hours.', 'success')
            return redirect(url_for('doctor_dashboard'))
        flash('Invalid doctor username or password.', 'danger')
    return render_template('login_doctor.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/patient/login', methods=['GET', 'POST'])
def patient_login():
    """Patient portal login: use Patient ID and registered phone number."""
    # If already in patient session, go straight to profile
    if session.get('patient_worker_id'):
        return redirect(url_for('patient_profile'))
    if request.method == 'POST':
        patient_id_raw = (request.form.get('patient_id') or '').strip()
        phone = (request.form.get('phone') or '').strip()
        if not patient_id_raw or not phone:
            flash('Patient ID and phone number are required.', 'danger')
            return render_template('patient_login.html', form=request.form)
        try:
            worker_id = int(patient_id_raw)
        except ValueError:
            flash('Invalid Patient ID. Please enter the numeric ID shown on your card or QR page.', 'danger')
            return render_template('patient_login.html', form=request.form)
        worker = Worker.query.filter_by(id=worker_id, phone=phone).first()
        if not worker:
            flash('No patient found with this ID and phone. Please check your details.', 'danger')
            return render_template('patient_login.html', form=request.form)
        session['patient_worker_id'] = worker.id
        session['patient_name'] = worker.name
        flash(f'Welcome, {worker.name}.', 'success')
        return redirect(url_for('patient_profile'))
    return render_template('patient_login.html', form={})


@app.route('/patient/logout')
def patient_logout():
    """Log out from patient portal only (does not affect admin/doctor login)."""
    session.pop('patient_worker_id', None)
    session.pop('patient_name', None)
    flash('You have been logged out from the patient portal.', 'info')
    return redirect(url_for('index'))


@app.route('/doctor/dashboard')
@login_required
def doctor_dashboard():
    if getattr(current_user, 'role', None) != 'doctor':
        return redirect(url_for('dashboard'))
    workers = Worker.query.order_by(Worker.id.asc()).all()
    search = (request.args.get('search') or '').strip()
    if search:
        if search.isdigit():
            workers = Worker.query.filter(
                (Worker.name.ilike(f'%{search}%')) | (Worker.phone.ilike(f'%{search}%')) | (Worker.id == int(search))
            ).order_by(Worker.id.asc()).all()
        else:
            workers = Worker.query.filter(
                (Worker.name.ilike(f'%{search}%')) | (Worker.phone.ilike(f'%{search}%'))
            ).order_by(Worker.id.asc()).all()
    phone_base_url = get_base_url_for_qr() if request else None
    url_is_local = is_local_url(phone_base_url)
    return render_template('doctor_dashboard.html', workers=workers, search=search, phone_base_url=phone_base_url, url_is_local=url_is_local)


@app.route('/dashboard')
@login_required
def dashboard():
    if getattr(current_user, 'role', None) == 'doctor':
        return redirect(url_for('doctor_dashboard'))
    total_workers = Worker.query.count()
    total_vaccinations = db.session.query(Vaccination).count()
    workers = Worker.query.order_by(Worker.id.asc()).all()
    search = (request.args.get('search') or '').strip()
    if search:
        workers = Worker.query.filter(
            Worker.name.ilike(f'%{search}%') |
            Worker.phone.ilike(f'%{search}%') |
            Worker.address.ilike(f'%{search}%')
        ).order_by(Worker.id.asc()).all()
    recent_workers = Worker.query.order_by(Worker.id.desc()).limit(5).all()
    phone_base_url = get_base_url_for_qr() if request else None
    url_is_local = is_local_url(phone_base_url)
    return render_template(
        'dashboard.html',
        total_workers=total_workers,
        total_vaccinations=total_vaccinations,
        workers=workers,
        search=search,
        recent_workers=recent_workers,
        phone_base_url=phone_base_url,
        url_is_local=url_is_local,
    )


@app.route('/register', methods=['GET', 'POST'])
@login_required
@admin_required
def register():
    doctors = User.query.filter_by(role='doctor').order_by(User.username).all()
    if request.method == 'POST':
        ok, err = validate_worker_form(request.form)
        if not ok:
            flash(err, 'danger')
            return render_template('register.html', form=request.form, doctors=doctors)
        name = request.form.get('name', '').strip()
        age = int(request.form.get('age'))
        gender = request.form.get('gender', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        blood_group = request.form.get('blood_group', '').strip()
        allergies = (request.form.get('allergies') or '').strip()
        diseases = (request.form.get('diseases') or '').strip()
        assigned_doctor_id = request.form.get('assigned_doctor_id')
        worker = Worker(
            name=name, age=age, gender=gender, phone=phone, address=address,
            blood_group=blood_group, allergies=allergies, diseases=diseases
        )
        if assigned_doctor_id:
            try:
                worker.assigned_doctor_id = int(assigned_doctor_id)
            except (ValueError, TypeError):
                pass
        db.session.add(worker)
        db.session.commit()
        qr_path = generate_qr_for_worker(worker.id)
        worker.qr_code_path = qr_path
        db.session.commit()
        flash(f'Patient "{name}" registered successfully. QR code generated.', 'success')
        return redirect(url_for('profile', id=worker.id))
    return render_template('register.html', form={}, doctors=doctors)


@app.route('/manage_doctors', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_doctors():
    """Admin: list doctors and set Doctor ID manually (type-in)."""
    doctors = User.query.filter_by(role='doctor').order_by(User.username).all()
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        doctor_id_value = (request.form.get('doctor_id') or '').strip()
        if user_id:
            try:
                u = User.query.get(int(user_id))
                if u and u.role == 'doctor':
                    # Allow empty to clear; otherwise enforce unique
                    if not doctor_id_value:
                        u.doctor_id = None
                    else:
                        existing = User.query.filter(User.doctor_id == doctor_id_value, User.id != u.id).first()
                        if existing:
                            flash(f'Doctor ID "{doctor_id_value}" is already used by another user.', 'danger')
                            return render_template('manage_doctors.html', doctors=doctors)
                        u.doctor_id = doctor_id_value[:20]
                    db.session.commit()
                    flash('Doctor ID updated.', 'success')
            except (ValueError, TypeError):
                pass
        return redirect(url_for('manage_doctors'))
    return render_template('manage_doctors.html', doctors=doctors)


@app.route('/profile/<int:id>')
def profile(id):
    worker = Worker.query.get_or_404(id)
    # Regenerate QR on each view so it always encodes the current base URL
    # (e.g. PUBLIC_URL when deployed, or local IP when on same WiFi)
    try:
        qr_path = generate_qr_for_worker(worker.id)
        worker.qr_code_path = qr_path
        db.session.commit()
    except Exception:
        pass  # keep existing QR path if generation fails
    vaccinations = Vaccination.query.filter_by(worker_id=id).order_by(Vaccination.date.desc()).all()
    documents = Document.query.filter_by(worker_id=id).order_by(Document.uploaded_at.desc()).all()
    prescriptions = Prescription.query.filter_by(worker_id=id).order_by(Prescription.prescribed_at.desc()).all()
    problems = Problem.query.filter_by(worker_id=id).order_by(Problem.date.desc()).all()
    phone_base_url = get_base_url_for_qr() if request else None
    share_url = f"{phone_base_url}/profile/{id}" if phone_base_url else None
    url_is_local = is_local_url(phone_base_url) if phone_base_url else True
    return render_template('profile.html', worker=worker, vaccinations=vaccinations, documents=documents, prescriptions=prescriptions, problems=problems, share_url=share_url, url_is_local=url_is_local)


@app.route('/patient/profile')
@patient_login_required
def patient_profile():
    """Patient portal: view own details, prescriptions, and uploaded documents."""
    worker_id = session.get('patient_worker_id')
    worker = Worker.query.get_or_404(worker_id)
    vaccinations = Vaccination.query.filter_by(worker_id=worker.id).order_by(Vaccination.date.desc()).all()
    documents = Document.query.filter_by(worker_id=worker.id).order_by(Document.uploaded_at.desc()).all()
    prescriptions = Prescription.query.filter_by(worker_id=worker.id).order_by(Prescription.prescribed_at.desc()).all()
    problems = Problem.query.filter_by(worker_id=worker.id).order_by(Problem.date.desc()).all()
    return render_template('patient_profile.html', worker=worker, vaccinations=vaccinations, documents=documents, prescriptions=prescriptions, problems=problems)


@app.route('/add_vaccine/<int:id>', methods=['GET', 'POST'])
@login_required
def add_vaccine(id):
    worker = Worker.query.get_or_404(id)
    if request.method == 'POST':
        vaccine_name = (request.form.get('vaccine_name') or '').strip()
        date_str = request.form.get('date') or ''
        if not vaccine_name or len(vaccine_name) < 2:
            flash('Vaccine name must be at least 2 characters.', 'danger')
            return render_template('add_vaccine.html', worker=worker)
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date.', 'danger')
            return render_template('add_vaccine.html', worker=worker)
        vaccination = Vaccination(worker_id=id, vaccine_name=vaccine_name, date=date)
        db.session.add(vaccination)
        db.session.commit()
        flash(f'Vaccination "{vaccine_name}" added successfully.', 'success')
        return redirect(url_for('profile', id=id))
    return render_template('add_vaccine.html', worker=worker)


@app.route('/edit_worker/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_worker(id):
    worker = Worker.query.get_or_404(id)
    doctors = User.query.filter_by(role='doctor').order_by(User.username).all()
    if request.method == 'POST':
        ok, err = validate_worker_form(request.form)
        if not ok:
            flash(err, 'danger')
            return render_template('edit_worker.html', worker=worker, doctors=doctors)
        worker.name = request.form.get('name', '').strip()
        worker.age = int(request.form.get('age'))
        worker.gender = request.form.get('gender', '').strip()
        worker.phone = request.form.get('phone', '').strip()
        worker.address = request.form.get('address', '').strip()
        worker.blood_group = request.form.get('blood_group', '').strip()
        worker.allergies = (request.form.get('allergies') or '').strip()
        worker.diseases = (request.form.get('diseases') or '').strip()
        assigned_doctor_id = request.form.get('assigned_doctor_id')
        try:
            worker.assigned_doctor_id = int(assigned_doctor_id) if assigned_doctor_id else None
        except (ValueError, TypeError):
            worker.assigned_doctor_id = None
        worker.updated_at = datetime.utcnow()
        db.session.commit()
        # Regenerate QR so it uses current base URL (e.g. same WiFi IP)
        worker.qr_code_path = generate_qr_for_worker(worker.id)
        db.session.commit()
        flash(f'Patient "{worker.name}" updated successfully.', 'success')
        return redirect(url_for('profile', id=id))
    return render_template('edit_worker.html', worker=worker, doctors=doctors)


@app.route('/delete_worker/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_worker(id):
    worker = Worker.query.get_or_404(id)
    name = worker.name
    for doc in worker.documents:
        path_file = os.path.join(app.static_folder, doc.stored_path)
        if os.path.isfile(path_file):
            try:
                os.remove(path_file)
            except OSError:
                pass
    for prescription in worker.prescriptions:
        if prescription.pdf_path:
            path_file = os.path.join(app.static_folder, prescription.pdf_path)
            if os.path.isfile(path_file):
                try:
                    os.remove(path_file)
                except OSError:
                    pass
    db.session.delete(worker)
    db.session.commit()
    flash(f'Patient "{name}" has been removed.', 'info')
    return redirect(url_for('dashboard'))


@app.route('/add_problem/<int:worker_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def add_problem(worker_id):
    worker = Worker.query.get_or_404(worker_id)
    doctors = User.query.filter_by(role='doctor').order_by(User.username).all()
    if request.method == 'POST':
        application_number = (request.form.get('application_number') or '').strip()
        doctor_id_val = (request.form.get('doctor_id') or '').strip()
        date_str = request.form.get('date') or ''
        disease = (request.form.get('disease') or '').strip()
        weight = (request.form.get('weight') or '').strip()[:50]
        if not application_number or not doctor_id_val or not date_str or not disease:
            flash('Application number, Doctor ID, Date and Disease are required.', 'danger')
            return render_template('add_problem.html', worker=worker, doctors=doctors)
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date.', 'danger')
            return render_template('add_problem.html', worker=worker, doctors=doctors)
        problem = Problem(
            worker_id=worker_id,
            application_number=application_number[:80],
            doctor_id=doctor_id_val[:20],
            date=date,
            disease=disease[:255],
            weight=weight,
        )
        db.session.add(problem)
        db.session.commit()
        flash('Problem record added.', 'success')
        return redirect(url_for('profile', id=worker_id))
    return render_template('add_problem.html', worker=worker, doctors=doctors)


@app.route('/edit_problem/<int:worker_id>/<int:problem_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_problem(worker_id, problem_id):
    worker = Worker.query.get_or_404(worker_id)
    problem = Problem.query.filter_by(id=problem_id, worker_id=worker_id).first_or_404()
    doctors = User.query.filter_by(role='doctor').order_by(User.username).all()
    if request.method == 'POST':
        application_number = (request.form.get('application_number') or '').strip()
        doctor_id_val = (request.form.get('doctor_id') or '').strip()
        date_str = request.form.get('date') or ''
        disease = (request.form.get('disease') or '').strip()
        weight = (request.form.get('weight') or '').strip()[:50]
        if not application_number or not doctor_id_val or not date_str or not disease:
            flash('Application number, Doctor ID, Date and Disease are required.', 'danger')
            return render_template('edit_problem.html', worker=worker, problem=problem, doctors=doctors)
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date.', 'danger')
            return render_template('edit_problem.html', worker=worker, problem=problem, doctors=doctors)
        problem.application_number = application_number[:80]
        problem.doctor_id = doctor_id_val[:20]
        problem.date = date
        problem.disease = disease[:255]
        problem.weight = weight
        db.session.commit()
        flash('Problem record updated.', 'success')
        return redirect(url_for('profile', id=worker_id))
    return render_template('edit_problem.html', worker=worker, problem=problem, doctors=doctors)


@app.route('/delete_problem/<int:worker_id>/<int:problem_id>', methods=['POST'])
@login_required
@admin_required
def delete_problem(worker_id, problem_id):
    problem = Problem.query.filter_by(id=problem_id, worker_id=worker_id).first_or_404()
    db.session.delete(problem)
    db.session.commit()
    flash('Problem record removed.', 'info')
    return redirect(url_for('profile', id=worker_id))


@app.route('/edit_vaccine/<int:worker_id>/<int:vac_id>', methods=['GET', 'POST'])
@login_required
def edit_vaccine(worker_id, vac_id):
    worker = Worker.query.get_or_404(worker_id)
    vaccination = Vaccination.query.filter_by(id=vac_id, worker_id=worker_id).first_or_404()
    if request.method == 'POST':
        vaccine_name = (request.form.get('vaccine_name') or '').strip()
        date_str = request.form.get('date') or ''
        if not vaccine_name or len(vaccine_name) < 2:
            flash('Vaccine name must be at least 2 characters.', 'danger')
            return render_template('edit_vaccine.html', worker=worker, vaccination=vaccination)
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date.', 'danger')
            return render_template('edit_vaccine.html', worker=worker, vaccination=vaccination)
        vaccination.vaccine_name = vaccine_name
        vaccination.date = date
        db.session.commit()
        flash('Vaccination updated successfully.', 'success')
        return redirect(url_for('profile', id=worker_id))
    return render_template('edit_vaccine.html', worker=worker, vaccination=vaccination)


@app.route('/delete_vaccine/<int:worker_id>/<int:vac_id>', methods=['POST'])
@login_required
def delete_vaccine(worker_id, vac_id):
    vaccination = Vaccination.query.filter_by(id=vac_id, worker_id=worker_id).first_or_404()
    db.session.delete(vaccination)
    db.session.commit()
    flash('Vaccination record removed.', 'info')
    return redirect(url_for('profile', id=worker_id))


# ---------------------------------------------------------------------------
# Reports & Prescriptions (document uploads)
# ---------------------------------------------------------------------------
@app.route('/upload_document/<int:worker_id>', methods=['POST'])
@login_required
@admin_required
def upload_document(worker_id):
    worker = Worker.query.get_or_404(worker_id)
    if 'document' not in request.files:
        flash('No file selected.', 'danger')
        return redirect(url_for('profile', id=worker_id))
    file = request.files['document']
    if file.filename == '' or not file.filename:
        flash('No file selected.', 'danger')
        return redirect(url_for('profile', id=worker_id))
    if not allowed_file(file.filename):
        flash('Allowed types: PDF, PNG, JPG, JPEG, GIF, WEBP. Max 10MB.', 'danger')
        return redirect(url_for('profile', id=worker_id))
    doc_type = (request.form.get('document_type') or 'report').strip().lower()
    if doc_type not in ('report', 'prescription', 'lab_result'):
        doc_type = 'report'
    notes = (request.form.get('notes') or '').strip()[:255]
    ext = file.filename.rsplit('.', 1)[-1].lower()
    safe_name = secure_filename(file.filename)
    if not safe_name:
        safe_name = 'file'
    unique = uuid.uuid4().hex[:8]
    stored_name = f"worker_{worker_id}_{doc_type}_{unique}.{ext}"
    stored_path = os.path.join(UPLOADS_DIR, stored_name)
    file.save(stored_path)
    rel_path = f"uploads/{stored_name}"
    doc = Document(
        worker_id=worker_id,
        document_type=doc_type,
        original_filename=safe_name,
        stored_path=rel_path,
        notes=notes,
    )
    db.session.add(doc)
    db.session.commit()
    flash(f'"{safe_name}" uploaded as {doc_type}.', 'success')
    return redirect(url_for('profile', id=worker_id))


@app.route('/download_document/<int:worker_id>/<int:doc_id>')
def download_document(worker_id, doc_id):
    doc = Document.query.filter_by(id=doc_id, worker_id=worker_id).first_or_404()
    path_dir = app.static_folder
    path_file = os.path.join(path_dir, doc.stored_path)
    if not os.path.isfile(path_file):
        flash('File not found.', 'danger')
        return redirect(url_for('profile', id=worker_id))
    return send_from_directory(
        path_dir,
        doc.stored_path,
        as_attachment=True,
        download_name=doc.original_filename,
    )


@app.route('/delete_document/<int:worker_id>/<int:doc_id>', methods=['POST'])
@login_required
def delete_document(worker_id, doc_id):
    # Allow both admin and doctor to delete uploaded documents.
    if getattr(current_user, 'role', None) not in ('admin', 'doctor'):
        flash('Only admin or doctor can delete documents.', 'warning')
        return redirect(url_for('profile', id=worker_id))
    doc = Document.query.filter_by(id=doc_id, worker_id=worker_id).first_or_404()
    path_file = os.path.join(app.static_folder, doc.stored_path)
    if os.path.isfile(path_file):
        try:
            os.remove(path_file)
        except OSError:
            pass
    db.session.delete(doc)
    db.session.commit()
    flash('Document removed.', 'info')
    return redirect(url_for('profile', id=worker_id))


# ---------------------------------------------------------------------------
# Digital Prescription System
# ---------------------------------------------------------------------------
def _pdf_safe(text):
    """Ensure text is safe for FPDF (ASCII/Latin-1); avoid Unicode errors."""
    if not text:
        return ''
    try:
        return text.encode('latin-1', errors='replace').decode('latin-1')
    except Exception:
        return ''.join(c if ord(c) < 256 else '?' for c in str(text))


def generate_prescription_pdf(prescription):
    """Generate PDF for a prescription; save to static/uploads/prescriptions/; return relative path."""
    try:
        import importlib
        # fpdf2 installs as "fpdf" (common), but some envs may expose "fpdf2".
        try:
            FPDF = importlib.import_module('fpdf').FPDF
        except Exception:
            FPDF = importlib.import_module('fpdf2').FPDF
    except Exception:
        raise ImportError("PDF library not installed. Run: pip install fpdf2")
    os.makedirs(PRESCRIPTIONS_PDF_DIR, exist_ok=True)
    worker = prescription.worker
    prescribed_by = prescription.prescribed_by
    doctor_name = prescribed_by.username if prescribed_by else 'Doctor'
    doctor_id_str = ''
    if prescribed_by and getattr(prescribed_by, 'doctor_id', None):
        doctor_id_str = f' (ID: {prescribed_by.doctor_id})'
    elif prescribed_by:
        doctor_id_str = f' (ID: DOC{prescribed_by.id})'
    path_dir = PRESCRIPTIONS_PDF_DIR
    filename = f"prescription_worker{worker.id}_{prescription.id}.pdf"
    filepath = os.path.join(path_dir, filename)
    rel_path = f"uploads/prescriptions/{filename}"

    class PDF(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 14)
            self.cell(0, 10, 'DIGITAL PRESCRIPTION', 0, 1, 'C')
            self.ln(2)

        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.cell(0, 10, 'Digital Health Record System - Generated prescription', 0, 0, 'C')

    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Helvetica', '', 11)
    pdf.cell(0, 8, _pdf_safe(f'Patient: {worker.name}  |  Age: {worker.age}  |  Blood Group: {worker.blood_group}'), 0, 1)
    pdf.cell(0, 6, f'Date: {prescription.prescribed_at.strftime("%d %b %Y %H:%M") if prescription.prescribed_at else "N/A"}', 0, 1)
    pdf.cell(0, 6, _pdf_safe(f'Prescribed by: {doctor_name}{doctor_id_str}'), 0, 1)
    pdf.ln(4)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 8, 'Diagnosis', 0, 1)
    pdf.set_font('Helvetica', '', 10)
    pdf.multi_cell(0, 6, _pdf_safe(prescription.diagnosis or '-'))
    pdf.ln(4)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 8, 'Medicines', 0, 1)
    pdf.set_font('Helvetica', '', 10)
    medicines_list = list(prescription.medicines.all())
    for m in medicines_list:
        line = f"  - {_pdf_safe(m.medicine_name)}  |  Dosage: {_pdf_safe(m.dosage or '-')}  |  {_pdf_safe(m.frequency or '-')}  |  {_pdf_safe(m.duration or '-')}"
        pdf.multi_cell(0, 6, line)
    if not medicines_list:
        pdf.multi_cell(0, 6, '  (None)')
    pdf.ln(4)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 8, 'Advice', 0, 1)
    pdf.set_font('Helvetica', '', 10)
    pdf.multi_cell(0, 6, _pdf_safe(prescription.advice or '-'))
    pdf.output(str(filepath))
    return rel_path


def _safe_abs_static_path(rel_path: str):
    """Return absolute path under static/ for a stored relative path; else None."""
    rel_path = (rel_path or '').strip().lstrip('/\\')
    if not rel_path:
        return None
    static_root = os.path.abspath(app.static_folder)
    abs_path = os.path.abspath(os.path.join(static_root, rel_path))
    if not (abs_path == static_root or abs_path.startswith(static_root + os.sep)):
        return None
    return abs_path


@app.route('/prescribe/<int:worker_id>', methods=['GET', 'POST'])
@login_required
@doctor_required
def prescribe(worker_id):
    worker = Worker.query.get_or_404(worker_id)
    if request.method == 'POST':
        diagnosis = (request.form.get('diagnosis') or '').strip()
        if not diagnosis or len(diagnosis) < 2:
            flash('Diagnosis is required (at least 2 characters).', 'danger')
            return render_template('prescribe.html', worker=worker)
        advice = (request.form.get('advice') or '').strip()[:500]
        prescription = Prescription(
            worker_id=worker_id,
            diagnosis=diagnosis,
            advice=advice,
            prescribed_by_id=current_user.id,
        )
        db.session.add(prescription)
        db.session.commit()
        medicine_names = request.form.getlist('medicine_name')
        dosages = request.form.getlist('dosage')
        frequencies = request.form.getlist('frequency')
        durations = request.form.getlist('duration')
        for i, name in enumerate(medicine_names):
            name = (name or '').strip()
            if not name:
                continue
            pm = PrescriptionMedicine(
                prescription_id=prescription.id,
                medicine_name=name[:200],
                dosage=(dosages[i] if i < len(dosages) else '').strip()[:100],
                frequency=(frequencies[i] if i < len(frequencies) else '').strip()[:100],
                duration=(durations[i] if i < len(durations) else '').strip()[:100],
            )
            db.session.add(pm)
        db.session.commit()
        try:
            rel_path = generate_prescription_pdf(prescription)
            prescription.pdf_path = rel_path
            db.session.commit()
            flash('Prescription saved. PDF generated. Patient can download it from the profile.', 'success')
        except Exception as e:
            app.logger.exception('Prescription PDF generation failed')
            flash(f'Prescription saved but PDF failed: {e}. Try "Regenerate PDF" on profile.', 'warning')
        return redirect(url_for('profile', id=worker_id))
    return render_template('prescribe.html', worker=worker)


@app.route('/download_prescription/<int:worker_id>/<int:prescription_id>')
def download_prescription(worker_id, prescription_id):
    prescription = Prescription.query.filter_by(id=prescription_id, worker_id=worker_id).first_or_404()
    pdf_path = (prescription.pdf_path or '').strip()
    abs_file = _safe_abs_static_path(pdf_path) if pdf_path else None

    # If PDF is missing/not generated, try generating it on-demand so download works.
    if not abs_file or not os.path.isfile(abs_file):
        try:
            rel_path = generate_prescription_pdf(prescription)
            prescription.pdf_path = rel_path
            db.session.commit()
            pdf_path = rel_path
            abs_file = _safe_abs_static_path(pdf_path)
        except Exception as e:
            app.logger.exception('On-demand prescription PDF generation failed')
            flash(f'Could not generate PDF: {e}', 'danger')
            return redirect(url_for('profile', id=worker_id))

    if not abs_file or not os.path.isfile(abs_file):
        flash('PDF file missing.', 'warning')
        return redirect(url_for('profile', id=worker_id))

    worker = prescription.worker
    safe_name = _pdf_safe(worker.name).replace(' ', '_')
    date_str = prescription.prescribed_at.strftime('%Y%m%d') if prescription.prescribed_at else str(prescription.id)
    download_name = f"Prescription_{safe_name}_{date_str}.pdf"
    return send_file(abs_file, mimetype='application/pdf', as_attachment=True, download_name=download_name, max_age=0)


@app.route('/regenerate_prescription_pdf/<int:worker_id>/<int:prescription_id>', methods=['POST'])
@login_required
def regenerate_prescription_pdf(worker_id, prescription_id):
    prescription = Prescription.query.filter_by(id=prescription_id, worker_id=worker_id).first_or_404()
    try:
        rel_path = generate_prescription_pdf(prescription)
        prescription.pdf_path = rel_path
        db.session.commit()
        flash('PDF generated. You can download it now.', 'success')
    except Exception as e:
        app.logger.exception('Regenerate PDF failed')
        flash(f'PDF generation failed: {e}', 'danger')
    return redirect(url_for('profile', id=worker_id))


@app.route('/delete_prescription/<int:worker_id>/<int:prescription_id>', methods=['POST'])
@login_required
@admin_required
def delete_prescription(worker_id, prescription_id):
    """Admin: delete a digital prescription and its PDF file."""
    prescription = Prescription.query.filter_by(id=prescription_id, worker_id=worker_id).first_or_404()
    pdf_path = (prescription.pdf_path or '').strip()
    if pdf_path:
        path_file = os.path.join(app.static_folder, pdf_path)
        if os.path.isfile(path_file):
            try:
                os.remove(path_file)
            except OSError:
                pass
    db.session.delete(prescription)
    db.session.commit()
    flash('Prescription removed.', 'info')
    return redirect(url_for('profile', id=worker_id))


# ---------------------------------------------------------------------------
# Init DB & Default Admin
# ---------------------------------------------------------------------------
def init_db():
    with app.app_context():
        db.create_all()
        # Add new columns to existing Worker table if missing (SQLite)
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                result = conn.execute(text('PRAGMA table_info(worker)'))
                cols = [row[1] for row in result]
                if 'created_at' not in cols:
                    conn.execute(text('ALTER TABLE worker ADD COLUMN created_at DATETIME'))
                    conn.commit()
                if 'updated_at' not in cols:
                    conn.execute(text('ALTER TABLE worker ADD COLUMN updated_at DATETIME'))
                    conn.commit()
                if 'assigned_doctor_id' not in cols:
                    conn.execute(text('ALTER TABLE worker ADD COLUMN assigned_doctor_id INTEGER REFERENCES user(id)'))
                    conn.commit()
        except Exception:
            pass
        # Add doctor_id and role column to user table if missing
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                result = conn.execute(text('PRAGMA table_info(user)'))
                cols = [row[1] for row in result]
                if 'role' not in cols:
                    conn.execute(text("ALTER TABLE user ADD COLUMN role VARCHAR(20) DEFAULT 'admin'"))
                    conn.commit()
                    conn.execute(text("UPDATE user SET role = 'admin' WHERE role IS NULL"))
                    conn.commit()
                if 'doctor_id' not in cols:
                    conn.execute(text('ALTER TABLE user ADD COLUMN doctor_id VARCHAR(20)'))
                    conn.commit()
            db.session.commit()
        except Exception:
            pass
        if User.query.filter_by(username='admin').first() is None:
            admin = User(username='admin', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('Default admin created: username=admin, password=admin123')
        if User.query.filter_by(username='doctor').first() is None:
            doctor = User(username='doctor', role='doctor')
            doctor.set_password('doctor123')
            db.session.add(doctor)
            db.session.commit()
            print('Default doctor created: username=doctor, password=doctor123')
        # Ensure existing admin has role
        for u in User.query.filter_by(username='admin').all():
            if getattr(u, 'role', None) != 'admin':
                u.role = 'admin'
                db.session.commit()
                break


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
