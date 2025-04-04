from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    requirements = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    candidates = db.relationship('Candidate', backref='job', lazy=True)
    
    def __repr__(self):
        return f'<Job {self.title}>'

class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    resume_path = db.Column(db.String(255), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'))
    match_score = db.Column(db.Float, default=0.0)
    is_shortlisted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    interviews = db.relationship('Interview', backref='candidate', lazy=True)
    
    def __repr__(self):
        return f'<Candidate {self.name}>'

class Interview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidate.id'))
    scheduled_date = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(255), nullable=True)
    meeting_link = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_confirmed = db.Column(db.Boolean, default=False)
    email_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Interview for Candidate {self.candidate_id}>' 