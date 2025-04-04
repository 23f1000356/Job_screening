# AI-Powered Job Screening Application

An intelligent recruitment assistant that automates resume screening, candidate shortlisting, and interview scheduling using AI matching algorithms.

## Features

- **JD Summarization**: Automatically extracts key elements from job descriptions
- **CV-JD Matching**: Uses AI to match candidate resumes with job descriptions
- **Candidate Shortlisting**: Automatically shortlists candidates based on match scores
- **Interview Scheduling**: Sends interview invitations to shortlisted candidates  
- **Bulk Resume Processing**: Upload and process multiple resumes at once
- **Dashboard Analytics**: Visualize recruitment metrics with interactive charts

## Setup Instructions

### Prerequisites

- Python 3.8+
- Virtual environment (recommended)

### Installation

1. Clone the repository or unzip the project files
2. Navigate to the project directory:
   ```
   cd job_screening
   ```
3. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
4. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
5. Initialize the database by running the application once:
   ```
   python app.py
   ```

## Usage

1. Start the application:
   ```
   python app.py
   ```
2. Open your browser and navigate to:
   ```
   http://localhost:5000
   ```
3. Login with the default admin credentials:
   - Username: admin
   - Password: admin

## Job Description Import

For the matching algorithm to work, you need to import job descriptions:

1. Create a CSV file with the following columns:
   - `id` (optional): Job ID
   - `title` (required): Job title
   - `description` (required): Full job description
   - `requirements` (optional): Job requirements

2. Navigate to "Import Jobs" in the sidebar and upload your CSV file

## Working with the Application

### Adding a Job Manually

1. Navigate to the Jobs page
2. Click "Add New Job"
3. Fill in the job details and submit

### Uploading a Resume

1. Navigate to the Upload Resume page
2. Select a job from the dropdown
3. Enter candidate details
4. Upload the resume file and submit

### Bulk Resume Upload

1. Navigate to the Bulk Upload page
2. Select a job from the dropdown
3. Choose multiple resume files
4. Upload and process

### Settings

1. Navigate to the Settings page to configure:
   - Match score threshold
   - Email templates
   - Account settings

## Technologies Used

- **Backend**: Flask, SQLAlchemy
- **Frontend**: Bootstrap 5, Chart.js
- **ML/NLP**: Scikit-learn, NLTK
- **Database**: SQLite (default)

## Default Threshold

By default, candidates with a match score above 70% will be shortlisted. This can be adjusted in the Settings page.

## Production Deployment

For production deployment, consider:

1. Using a production WSGI server like Gunicorn
2. Setting up a proper database like PostgreSQL
3. Configuring proper email settings
4. Setting secure secret keys

Example production start command:
```
gunicorn -w 4 -b 0.0.0.0:8000 app:app
``` 
