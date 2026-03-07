"""
Digital Health Record Management System - Database Models
Flask-SQLAlchemy ORM for User, Worker, and Vaccination tables.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """Login account: role is 'admin' or 'doctor'."""
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='admin')  # 'admin' or 'doctor'
    doctor_id = db.Column(db.String(20), unique=True, nullable=True)  # e.g. DOC001; for doctors only

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)


class Worker(db.Model):
    """Migrant worker health record."""
    __tablename__ = 'worker'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    blood_group = db.Column(db.String(10), nullable=False)
    allergies = db.Column(db.String(255), default='')
    diseases = db.Column(db.String(255), default='')
    qr_code_path = db.Column(db.String(255), default='')
    assigned_doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    assigned_doctor = db.relationship('User', backref='assigned_patients', foreign_keys=[assigned_doctor_id])
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    vaccinations = db.relationship('Vaccination', backref='worker', lazy='dynamic', cascade='all, delete-orphan')
    problems = db.relationship('Problem', backref='worker', lazy='dynamic', cascade='all, delete-orphan')
    documents = db.relationship('Document', backref='worker', lazy='dynamic', cascade='all, delete-orphan')
    prescriptions = db.relationship('Prescription', backref='worker', lazy='dynamic', cascade='all, delete-orphan')

    def vaccination_count(self):
        return self.vaccinations.count()

    def __repr__(self):
        return f'<Worker {self.name}>'


class Vaccination(db.Model):
    """Vaccination record linked to a worker."""
    __tablename__ = 'vaccination'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    vaccine_name = db.Column(db.String(120), nullable=False)
    date = db.Column(db.Date, nullable=False)

    def __repr__(self):
        return f'<Vaccination {self.vaccine_name} for Worker {self.worker_id}>'


class Problem(db.Model):
    """Problem/visit record for a worker: application number, doctor id, date, disease, weight. Admin creates; visible to doctor below vaccination."""
    __tablename__ = 'problem'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    application_number = db.Column(db.String(80), nullable=False)
    doctor_id = db.Column(db.String(20), nullable=False)   # Doctor ID (e.g. DOC001)
    date = db.Column(db.Date, nullable=False)
    disease = db.Column(db.String(255), nullable=False)
    weight = db.Column(db.String(50), default='')  # e.g. "70 kg"

    def __repr__(self):
        return f'<Problem {self.application_number} for Worker {self.worker_id}>'


class Document(db.Model):
    """Uploaded reports, prescriptions, and lab results for a worker."""
    __tablename__ = 'document'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    document_type = db.Column(db.String(20), nullable=False)  # 'report', 'prescription', 'lab_result'
    original_filename = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(500), nullable=False)  # relative to static/
    notes = db.Column(db.String(255), default='')
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)

    def __repr__(self):
        return f'<Document {self.original_filename} for Worker {self.worker_id}>'


class Prescription(db.Model):
    """Digital prescription created by doctor: diagnosis, medicines, advice; PDF generated."""
    __tablename__ = 'prescription'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    diagnosis = db.Column(db.String(500), nullable=False)
    advice = db.Column(db.String(500), default='')
    prescribed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)
    prescribed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    prescribed_by = db.relationship('User', backref='prescriptions_issued')
    pdf_path = db.Column(db.String(500), default='')  # relative to static/
    medicines = db.relationship('PrescriptionMedicine', backref='prescription', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Prescription {self.id} for Worker {self.worker_id}>'


class PrescriptionMedicine(db.Model):
    """One medicine line in a prescription."""
    __tablename__ = 'prescription_medicine'
    id = db.Column(db.Integer, primary_key=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey('prescription.id'), nullable=False)
    medicine_name = db.Column(db.String(200), nullable=False)
    dosage = db.Column(db.String(100), default='')   # e.g. "1 tablet"
    frequency = db.Column(db.String(100), default='') # e.g. "twice daily"
    duration = db.Column(db.String(100), default='')  # e.g. "5 days"

    def __repr__(self):
        return f'<PrescriptionMedicine {self.medicine_name}>'
