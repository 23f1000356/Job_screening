import os
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user # type: ignore
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import secrets
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

from database import db, User, Job, Candidate, Interview
from model import ResumeJobMatcher, extract_text_from_pdf, should_shortlist_candidate

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///job_screening.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size
app.config['SHORTLIST_THRESHOLD'] = 0.7  # 70% match score for shortlisting

# Email configuration (mock)
EMAIL_HOST = 'smtp.example.com'
EMAIL_PORT = 587
EMAIL_USER = 'recruiter@example.com'
EMAIL_PASSWORD = 'password123'

# Allowed file extensions
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt'}

# Initialize extensions
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Initialize matcher
matcher = ResumeJobMatcher()

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'resumes'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'temp'), exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def send_interview_email(candidate, interview):
    sender_email = EMAIL_USER
    receiver_email = candidate.email
    
    message = MIMEMultipart("alternative")
    message["Subject"] = f"Interview Invitation for {candidate.job.title} position"
    message["From"] = sender_email
    message["To"] = receiver_email

    text = f"""
    Dear {candidate.name},

    We are pleased to inform you that your resume has been shortlisted for the position of {candidate.job.title}.

    You are invited for an interview on {interview.scheduled_date.strftime('%A, %B %d, %Y')} at {interview.scheduled_date.strftime('%I:%M %p')}.
    
    Location: {interview.location}
    
    Please confirm your attendance by replying to this email.

    Best regards,
    The Hiring Team
    """

    html = f"""
    <html>
      <body>
        <p>Dear {candidate.name},</p>
        <p>We are pleased to inform you that your resume has been shortlisted for the position of <strong>{candidate.job.title}</strong>.</p>
        <p>You are invited for an interview on <strong>{interview.scheduled_date.strftime('%A, %B %d, %Y')}</strong> at <strong>{interview.scheduled_date.strftime('%I:%M %p')}</strong>.</p>
        <p>Location: {interview.location}</p>
        <p>Please confirm your attendance by replying to this email.</p>
        <p>Best regards,<br>The Hiring Team</p>
      </body>
    </html>
    """

    message.attach(MIMEText(text, "plain"))
    message.attach(MIMEText(html, "html"))

    try:
        # In production, you would actually send the email
        # For now, we'll just return True
        print(f"Mock email sent to {receiver_email}")
        return True
    except Exception as e:
        print(f"Failed to send email: {str(e)}")
        return False

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('register.html')
            
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already exists', 'danger')
            return render_template('register.html')
            
        new_user = User(
            username=username,
            email=email
        )
        new_user.set_password(password)
        
        # Make the first user an admin
        if User.query.count() == 0:
            new_user.is_admin = True
            
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    jobs = Job.query.order_by(Job.created_at.desc()).all()
    total_jobs = len(jobs)
    
    candidates = Candidate.query.all()
    total_candidates = len(candidates)
    
    shortlisted = Candidate.query.filter_by(is_shortlisted=True).count()
    
    stats = {
        'total_jobs': total_jobs,
        'total_candidates': total_candidates,
        'shortlisted': shortlisted
    }
    
    return render_template('dashboard.html', 
                          jobs=jobs, 
                          total_jobs=total_jobs,
                          total_candidates=total_candidates,
                          shortlisted=shortlisted)

@app.route('/jobs')
@login_required
def jobs():
    jobs = Job.query.order_by(Job.created_at.desc()).all()
    return render_template('jobs.html', jobs=jobs)

@app.route('/job/<int:job_id>')
@login_required
def view_job(job_id):
    job = Job.query.get_or_404(job_id)
    candidates = Candidate.query.filter_by(job_id=job_id).all()
    return render_template('job_detail.html', job=job, candidates=candidates)

@app.route('/add_job', methods=['GET', 'POST'])
@login_required
def add_job():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        requirements = request.form.get('requirements')
        
        new_job = Job(
            title=title,
            description=description,
            requirements=requirements,
            created_by=current_user.id
        )
        
        db.session.add(new_job)
        db.session.commit()
        
        flash('Job added successfully!', 'success')
        return redirect(url_for('jobs'))
    
    return render_template('add_job.html')

@app.route('/upload_resume', methods=['GET', 'POST'])
@login_required
def upload_resume():
    jobs = Job.query.all()
    
    if request.method == 'POST':
        job_id = request.form.get('job_id')
        name = request.form.get('name')
        email = request.form.get('email')
        
        if not job_id or not name or not email:
            flash('Please fill all required fields', 'danger')
            return redirect(url_for('upload_resume'))
            
        job = Job.query.get(job_id)
        if not job:
            flash('Invalid job selected', 'danger')
            return redirect(url_for('upload_resume'))
            
        # Check if resume file was uploaded
        if 'resume' not in request.files:
            flash('No resume file uploaded', 'danger')
            return redirect(url_for('upload_resume'))
            
        resume_file = request.files['resume']
        
        if resume_file.filename == '':
            flash('No resume file selected', 'danger')
            return redirect(url_for('upload_resume'))
            
        if resume_file and allowed_file(resume_file.filename):
            # Create a unique filename
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = secure_filename(f"{timestamp}_{resume_file.filename}")
            resume_path = os.path.join(app.config['UPLOAD_FOLDER'], 'resumes', filename)
            
            # Save the file
            resume_file.save(resume_path)
            
            # Extract text from resume
            resume_text = extract_text_from_pdf(resume_path)
            
            # Match resume with job
            match_result = matcher.match_resume_to_job(
                resume_text, 
                job.description, 
                job.requirements,
                app.config['SHORTLIST_THRESHOLD'],
                use_simple_matching=True  # Use the user's matching algorithm
            )
            
            match_score = match_result['similarity_score']
            is_shortlisted = match_result['is_match']
            matching_keywords = match_result.get('matching_keywords', [])
            
            # Save candidate to database
            new_candidate = Candidate(
                name=name,
                email=email,
                resume_path=resume_path,
                job_id=job_id,
                match_score=match_score,
                is_shortlisted=is_shortlisted
            )
            
            db.session.add(new_candidate)
            db.session.commit()
            
            # If candidate is shortlisted, schedule interview
            if is_shortlisted:
                interview_date = datetime.now() + timedelta(days=3)  # Schedule interview 3 days from now
                
                new_interview = Interview(
                    candidate_id=new_candidate.id,
                    scheduled_date=interview_date,
                    location="Video call (link will be sent later)",
                    notes="Automatically scheduled based on resume match."
                )
                
                db.session.add(new_interview)
                db.session.commit()
                
                # Send interview email
                if send_interview_email(new_candidate, new_interview):
                    new_interview.email_sent = True
                    db.session.commit()
            
            # Store match results in session for display
            session['match_results'] = {
                'candidate_id': new_candidate.id,
                'name': name,
                'job_title': job.title,
                'match_score': round(match_score * 100, 2) if not isinstance(match_score, float) else round(match_score, 2),
                'is_shortlisted': is_shortlisted,
                'matching_keywords': matching_keywords
            }
            
            return redirect(url_for('upload_results'))
        else:
            flash('Invalid file type. Please upload a PDF, DOC, DOCX, or TXT file', 'danger')
            return redirect(url_for('upload_resume'))
    
    return render_template('upload_resume.html', jobs=jobs)

@app.route('/upload_multiple', methods=['GET', 'POST'])
@login_required
def upload_multiple():
    jobs = Job.query.all()
    
    if request.method == 'POST':
        job_id = request.form.get('job_id')
        
        if not job_id:
            flash('Please select a job', 'danger')
            return redirect(url_for('upload_multiple'))
            
        job = Job.query.get(job_id)
        if not job:
            flash('Invalid job selected', 'danger')
            return redirect(url_for('upload_multiple'))
            
        # Check if resume files were uploaded
        if 'resumes' not in request.files:
            flash('No resume files uploaded', 'danger')
            return redirect(url_for('upload_multiple'))
            
        resume_files = request.files.getlist('resumes')
        
        if len(resume_files) == 0 or resume_files[0].filename == '':
            flash('No resume files selected', 'danger')
            return redirect(url_for('upload_multiple'))
            
        # Process each resume
        processed_count = 0
        shortlisted_count = 0
        
        bulk_results = []
        
        for resume_file in resume_files:
            if resume_file and allowed_file(resume_file.filename):
                # Create a unique filename
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = secure_filename(f"{timestamp}_{resume_file.filename}")
                resume_path = os.path.join(app.config['UPLOAD_FOLDER'], 'resumes', filename)
                
                # Save the file
                resume_file.save(resume_path)
                
                # Extract candidate name from filename
                candidate_name = resume_file.filename.split('.')[0].replace('_', ' ').title()
                # Generate mock email
                candidate_email = f"{candidate_name.lower().replace(' ', '.')}@example.com"
                
                # Extract text from resume
                resume_text = extract_text_from_pdf(resume_path)
                
                # Match resume with job
                match_result = matcher.match_resume_to_job(
                    resume_text, 
                    job.description, 
                    job.requirements,
                    app.config['SHORTLIST_THRESHOLD'],
                    use_simple_matching=True  # Use the user's matching algorithm
                )
                
                match_score = match_result['similarity_score']
                is_shortlisted = match_result['is_match']
                matching_keywords = match_result.get('matching_keywords', [])
                
                # Save candidate to database
                new_candidate = Candidate(
                    name=candidate_name,
                    email=candidate_email,
                    resume_path=resume_path,
                    job_id=job_id,
                    match_score=match_score,
                    is_shortlisted=is_shortlisted
                )
                
                db.session.add(new_candidate)
                db.session.commit()
                
                # If candidate is shortlisted, schedule interview
                if is_shortlisted:
                    interview_date = datetime.now() + timedelta(days=3)  # Schedule interview 3 days from now
                    
                    new_interview = Interview(
                        candidate_id=new_candidate.id,
                        scheduled_date=interview_date,
                        location="Video call (link will be sent later)",
                        notes="Automatically scheduled based on resume match."
                    )
                    
                    db.session.add(new_interview)
                    db.session.commit()
                    
                    # Send interview email
                    if send_interview_email(new_candidate, new_interview):
                        new_interview.email_sent = True
                        db.session.commit()
                        
                    shortlisted_count += 1
                
                # Add to results
                bulk_results.append({
                    'candidate_id': new_candidate.id,
                    'name': candidate_name,
                    'match_score': round(match_score * 100, 2) if not isinstance(match_score, float) else round(match_score, 2),
                    'is_shortlisted': is_shortlisted,
                    'matching_keywords': matching_keywords
                })
                
                processed_count += 1
        
        # Store bulk results in session
        session['bulk_results'] = {
            'job_title': job.title,
            'processed_count': processed_count,
            'shortlisted_count': shortlisted_count,
            'candidates': bulk_results
        }
        
        flash(f'Successfully processed {processed_count} resumes. {shortlisted_count} candidates shortlisted.', 'success')
        return redirect(url_for('upload_results'))
    
    return render_template('upload_multiple.html', jobs=jobs)

@app.route('/upload_results')
@login_required
def upload_results():
    match_results = session.get('match_results')
    bulk_results = session.get('bulk_results')
    
    return render_template('upload_results.html', match_results=match_results, bulk_results=bulk_results)

@app.route('/candidates')
@login_required
def candidates():
    candidates = Candidate.query.all()
    shortlisted_count = Candidate.query.filter_by(is_shortlisted=True).count()
    interviewed_count = Interview.query.filter(Interview.scheduled_date < datetime.now()).count()
    
    # Calculate average match score
    if candidates:
        avg_match_score = sum(c.match_score for c in candidates) / len(candidates)
    else:
        avg_match_score = 0
    
    jobs = Job.query.all()
    
    return render_template('candidates.html', 
                          candidates=candidates,
                          shortlisted_count=shortlisted_count,
                          interviewed_count=interviewed_count,
                          avg_match_score=avg_match_score,
                          jobs=jobs)

@app.route('/candidate_detail/<int:id>')
@login_required
def candidate_detail(id):
    candidate = Candidate.query.get_or_404(id)
    interview = Interview.query.filter_by(candidate_id=id).first()
    
    # Extract resume text
    resume_text = extract_text_from_pdf(candidate.resume_path)
    
    # Calculate component scores (mock data for now)
    skill_match_score = min(candidate.match_score * 1.1, 100)
    experience_match_score = min(candidate.match_score * 0.9, 100)
    education_match_score = min(candidate.match_score * 1.05, 100)
    
    # Extract skills (mock data)
    skills = ["Python", "SQL", "Data Analysis", "Machine Learning", "JavaScript", "Project Management"]
    
    # AI analysis (mock)
    ai_analysis = f"Candidate shows strong experience in software development with a focus on {skills[0]} and {skills[1]}. Education background is relevant to the position. Technical skills align well with job requirements."
    
    return render_template('candidate_detail.html',
                          candidate=candidate,
                          interview=interview,
                          resume_text=resume_text,
                          skill_match_score=skill_match_score,
                          experience_match_score=experience_match_score,
                          education_match_score=education_match_score,
                          skills=skills,
                          ai_analysis=ai_analysis)

@app.route('/interviews')
@login_required
def interviews():
    interviews = Interview.query.all()
    
    # Calculate stats
    today = datetime.now().date()
    upcoming_count = Interview.query.filter(Interview.scheduled_date > datetime.now()).count()
    completed_count = Interview.query.filter(Interview.scheduled_date < datetime.now()).count()
    today_count = Interview.query.filter(Interview.scheduled_date.cast(db.Date) == today).count()
    
    jobs = Job.query.all()
    
    return render_template('interviews.html', 
                          interviews=interviews,
                          upcoming_count=upcoming_count,
                          completed_count=completed_count,
                          today_count=today_count,
                          today=today,
                          jobs=jobs)

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')

@app.route('/api/job/<int:job_id>')
@login_required
def api_job(job_id):
    job = Job.query.get_or_404(job_id)
    
    return jsonify({
        'id': job.id,
        'title': job.title,
        'description': job.description,
        'requirements': job.requirements,
        'candidate_count': len(job.candidates)
    })

@app.route('/api/resend_invite/<int:interview_id>')
@login_required
def resend_invite(interview_id):
    interview = Interview.query.get_or_404(interview_id)
    candidate = Candidate.query.get(interview.candidate_id)
    
    if send_interview_email(candidate, interview):
        interview.email_sent = True
        db.session.commit()
        return jsonify({'success': True, 'message': 'Invitation sent successfully'})
    else:
        return jsonify({'success': False, 'message': 'Failed to send invitation'})

@app.route('/api/update_match_threshold', methods=['POST'])
@login_required
def update_match_threshold():
    data = request.json
    threshold = data.get('threshold')
    
    if threshold is None or not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 1:
        return jsonify({'success': False, 'message': 'Invalid threshold value'})
    
    app.config['SHORTLIST_THRESHOLD'] = threshold
    
    return jsonify({'success': True, 'message': 'Threshold updated successfully'})

@app.route('/import_jobs', methods=['GET', 'POST'])
@login_required
def import_jobs():
    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
            
        csv_file = request.files['csv_file']
        
        if csv_file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
            
        if csv_file and csv_file.filename.endswith('.csv'):
            # Save the CSV file temporarily
            csv_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp', secure_filename(csv_file.filename))
            csv_file.save(csv_path)
            
            try:
                # Try different encodings
                encodings = ['utf-8', 'latin-1', 'ISO-8859-1', 'cp1252']
                df = None
                
                for encoding in encodings:
                    try:
                        df = pd.read_csv(csv_path, encoding=encoding)
                        print(f"Successfully read CSV with encoding: {encoding}")
                        break
                    except UnicodeDecodeError:
                        continue
                
                if df is None:
                    flash('Could not read CSV file with any of the supported encodings. Please save your file with UTF-8 encoding.', 'danger')
                    return redirect(request.url)
                
                # Rename columns if they have alternative names
                column_mapping = {
                    'Job Title': 'title',
                    'Description': 'description',
                    'Requirements': 'requirements',
                    'JOB TITLE': 'title',
                    'DESCRIPTION': 'description',
                    'REQUIREMENTS': 'requirements',
                    'job title': 'title',
                    'description': 'description',
                    'requirements': 'requirements'
                }
                
                df = df.rename(columns=column_mapping)
                
                # Check for required columns
                required_columns = ['title', 'description']
                missing_columns = [col for col in required_columns if col not in df.columns]
                
                if missing_columns:
                    # Try to identify columns that might contain the required information
                    if 'title' in missing_columns and any(col for col in df.columns if 'title' in col.lower()):
                        possible_title_columns = [col for col in df.columns if 'title' in col.lower()]
                        df['title'] = df[possible_title_columns[0]]
                        missing_columns.remove('title')
                        
                    if 'description' in missing_columns and any(col for col in df.columns if 'description' in col.lower() or 'desc' in col.lower()):
                        possible_desc_columns = [col for col in df.columns if 'description' in col.lower() or 'desc' in col.lower()]
                        df['description'] = df[possible_desc_columns[0]]
                        missing_columns.remove('description')
                
                # Check again if we still have missing columns
                if missing_columns:
                    flash(f'Required column(s) not found: {", ".join(missing_columns)}. Your CSV must have columns for job title and description.', 'danger')
                    return redirect(request.url)
                
                # Add jobs to database
                added_count = 0
                for _, row in df.iterrows():
                    # Get values with empty string fallback
                    title = row.get('title', '')
                    description = row.get('description', '')
                    requirements = row.get('requirements', '')
                    
                    # Skip if missing required fields
                    if not isinstance(title, str) or not isinstance(description, str):
                        continue
                        
                    if not title or not description:
                        continue
                        
                    new_job = Job(
                        title=title,
                        description=description,
                        requirements=requirements,
                        created_by=current_user.id
                    )
                    
                    db.session.add(new_job)
                    added_count += 1
                
                db.session.commit()
                
                flash(f'Successfully imported {added_count} jobs', 'success')
                return redirect(url_for('jobs'))
                
            except Exception as e:
                flash(f'Error processing CSV file: {str(e)}', 'danger')
                return redirect(request.url)
            finally:
                # Clean up temporary file
                if os.path.exists(csv_path):
                    os.remove(csv_path)
        else:
            flash('Please upload a CSV file', 'danger')
            return redirect(request.url)
    
    # Get recent jobs for display
    recent_jobs = Job.query.order_by(Job.created_at.desc()).limit(5).all()
    
    return render_template('import_jobs.html', recent_jobs=recent_jobs)

@app.route('/download_resume/<int:id>')
@login_required
def download_resume(id):
    candidate = Candidate.query.get_or_404(id)
    return send_file(candidate.resume_path, as_attachment=True)

@app.route('/send_interview_invitation/<int:id>', methods=['POST'])
@login_required
def send_interview_invitation(id):
    candidate = Candidate.query.get_or_404(id)
    
    interview_date = request.form.get('interview_date')
    interview_time = request.form.get('interview_time')
    location = request.form.get('interview_location')
    notes = request.form.get('additional_notes')
    
    if not interview_date or not interview_time:
        flash('Date and time are required', 'danger')
        return redirect(url_for('candidate_detail', id=id))
    
    # Combine date and time
    date_time_str = f"{interview_date} {interview_time}"
    scheduled_date = datetime.strptime(date_time_str, '%Y-%m-%d %H:%M')
    
    # Check if candidate already has an interview
    existing_interview = Interview.query.filter_by(candidate_id=id).first()
    
    if existing_interview:
        # Update existing interview
        existing_interview.scheduled_date = scheduled_date
        existing_interview.location = location
        existing_interview.notes = notes
        
        db.session.commit()
        
        # Send interview email
        if send_interview_email(candidate, existing_interview):
            existing_interview.email_sent = True
            db.session.commit()
        
        flash('Interview updated and invitation sent', 'success')
    else:
        # Create new interview
        new_interview = Interview(
            candidate_id=id,
            scheduled_date=scheduled_date,
            location=location,
            notes=notes
        )
        
        db.session.add(new_interview)
        db.session.commit()
        
        # Send interview email
        if send_interview_email(candidate, new_interview):
            new_interview.email_sent = True
            db.session.commit()
        
        flash('Interview scheduled and invitation sent', 'success')
    
    return redirect(url_for('candidate_detail', id=id))

@app.route('/save_interview_feedback/<int:id>', methods=['POST'])
@login_required
def save_interview_feedback(id):
    interview = Interview.query.get_or_404(id)
    
    rating = request.form.get('rating')
    technical_skills = request.form.get('technical_skills')
    communication_skills = request.form.get('communication_skills')
    notes = request.form.get('notes')
    hiring_decision = request.form.get('hiring_decision')
    
    # In a real app, you would have a Feedback model
    # For now, we'll save as JSON in the notes field
    feedback = {
        'rating': rating,
        'technical_skills': technical_skills,
        'communication_skills': communication_skills,
        'notes': notes,
        'hiring_decision': hiring_decision,
        'added_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    interview.notes = json.dumps(feedback)
    db.session.commit()
    
    flash('Interview feedback saved successfully', 'success')
    return redirect(url_for('interviews'))

@app.route('/download_template')
@login_required
def download_template():
    # Create a sample CSV template with Job Title and Description columns
    template_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp', 'job_template.csv')
    
    with open(template_path, 'w', newline='') as f:
        f.write('Job Title,Description,Requirements\n')
        f.write('"Software Engineer","We are looking for a skilled Software Engineer...","Python, JavaScript, SQL"\n')
        f.write('"Data Analyst","Join our data team to analyze...","SQL, Excel, Statistics"\n')
    
    return send_file(template_path, as_attachment=True, download_name='job_template.csv')

@app.route('/api/interviews')
@login_required
def api_interviews():
    interviews = Interview.query.all()
    interview_data = []
    
    for interview in interviews:
        candidate = Candidate.query.get(interview.candidate_id)
        job = Job.query.get(candidate.job_id)
        
        interview_data.append({
            'id': interview.id,
            'title': f"{candidate.name} - {job.title}",
            'start': interview.scheduled_date.isoformat(),
            'url': url_for('candidate_detail', id=candidate.id),
            'backgroundColor': '#ffc107' if interview.scheduled_date.date() == datetime.now().date() else '#6f42c1',
            'borderColor': '#ffc107' if interview.scheduled_date.date() == datetime.now().date() else '#6f42c1',
            'textColor': '#000000' if interview.scheduled_date.date() == datetime.now().date() else '#ffffff',
            'extendedProps': {
                'candidateId': candidate.id,
                'location': interview.location,
                'confirmed': interview.is_confirmed
            }
        })
    
    return jsonify(interview_data)

def create_tables():
    with app.app_context():
        db.create_all()
        
        # Create admin user if no users exist
        if User.query.count() == 0:
            admin = User(
                username='admin',
                email='admin@example.com',
                is_admin=True
            )
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()

if __name__ == '__main__':
    # Initialize database before running the app
    create_tables()
    app.run(debug=True) 