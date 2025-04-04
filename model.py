import pandas as pd
import numpy as np
import re
import os
import nltk
import fitz  # PyMuPDF
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Download necessary NLTK data
try:
    nltk.data.find('tokenizers/punkt')
    nltk.data.find('corpora/stopwords')
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('punkt')
    nltk.download('stopwords')
    nltk.download('wordnet')

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF file using PyMuPDF"""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        print(f"Error extracting text from PDF: {str(e)}")
        return ""

def simple_tokenizer(text):
    """Convert text to a set of keywords"""
    if not isinstance(text, str):
        return set()
        
    # Replace common problematic characters
    text = text.replace(''', "'").replace(''', "'").replace('"', '"').replace('"', '"').replace('–', '-')
    
    # Convert to lowercase and remove most punctuation
    text = re.sub(r'[^a-zA-Z0-9\s\']', ' ', text.lower())
    
    # Replace multiple spaces with a single space
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Split into tokens
    tokens = text.split()
    
    # Keep only words with length > 2
    keywords = [word for word in tokens if len(word) > 2]
    
    return set(keywords)

def extract_cv_keywords(text):
    """Extract keywords from CV by sections"""
    sections = {
        "education": [],
        "experience": [],
        "skills": [],
        "certifications": [],
        "achievements": [],
        "tech_stack": []
    }

    lines = text.split('\n')
    current_section = ""

    for line in lines:
        lower = line.lower()
        if "education" in lower:
            current_section = "education"
        elif "experience" in lower:
            current_section = "experience"
        elif "skill" in lower:
            current_section = "skills"
        elif "certification" in lower:
            current_section = "certifications"
        elif "achievement" in lower:
            current_section = "achievements"
        elif "tech stack" in lower or "technologies" in lower:
            current_section = "tech_stack"
        elif line.strip() == "":
            current_section = ""

        if current_section and len(line.strip()) > 3:
            sections[current_section].append(line.strip())

    all_text = " ".join([" ".join(v) for v in sections.values()])
    return simple_tokenizer(all_text)

def extract_jd_keywords(description, requirements=None):
    """Extract keywords from job description"""
    all_text = description
    if requirements:
        all_text += " " + requirements
    return simple_tokenizer(all_text)

class ResumeJobMatcher:
    def __init__(self):
        self.stop_words = set(stopwords.words('english'))
        self.lemmatizer = WordNetLemmatizer()
        self.vectorizer = TfidfVectorizer()
        self.job_descriptions = None
        self.job_vectors = None
        
    def preprocess_text(self, text):
        """Clean and preprocess text data"""
        if not isinstance(text, str):
            return ""
            
        # Convert to lowercase and remove punctuation
        text = text.lower()
        
        # Replace common problematic characters
        text = text.replace(''', "'").replace(''', "'").replace('"', '"').replace('"', '"').replace('–', '-')
        
        # Remove punctuation but preserve apostrophes in words like "don't"
        text = re.sub(r'[^\w\s\']', ' ', text)
        
        # Replace multiple spaces with a single space
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Tokenize and remove stopwords
        word_tokens = word_tokenize(text)
        filtered_text = [self.lemmatizer.lemmatize(w) for w in word_tokens if w not in self.stop_words]
        
        return " ".join(filtered_text)
    
    def load_job_descriptions(self, job_df):
        """Load job descriptions from DataFrame"""
        if isinstance(job_df, pd.DataFrame) and 'description' in job_df.columns:
            # Preprocess job descriptions
            job_df['processed_description'] = job_df['description'].apply(self.preprocess_text)
            self.job_descriptions = job_df
            
            # Vectorize job descriptions
            self.job_vectors = self.vectorizer.fit_transform(job_df['processed_description'])
            return True
        return False
    
    def match_resume_to_jobs(self, resume_text, threshold=0.6):
        """Match a resume against all job descriptions"""
        if self.job_vectors is None or self.job_descriptions is None:
            raise ValueError("Job descriptions not loaded. Call load_job_descriptions first.")
        
        # Preprocess resume
        processed_resume = self.preprocess_text(resume_text)
        
        # Vectorize resume using the same vectorizer
        resume_vector = self.vectorizer.transform([processed_resume])
        
        # Calculate cosine similarity
        similarities = cosine_similarity(resume_vector, self.job_vectors).flatten()
        
        # Create result DataFrame
        results = pd.DataFrame({
            'job_id': self.job_descriptions['id'],
            'job_title': self.job_descriptions['title'],
            'similarity_score': similarities
        })
        
        # Sort by similarity score
        results = results.sort_values('similarity_score', ascending=False)
        
        # Flag positions that match above threshold
        results['is_match'] = results['similarity_score'] >= threshold
        
        return results
    
    def match_resume_to_job(self, resume_text, job_description, requirements=None, threshold=0.6, use_simple_matching=False):
        """Match a single resume against a single job description"""
        if use_simple_matching:
            # Use the user's simple matching algorithm
            if isinstance(resume_text, str) and resume_text.strip():
                cv_keywords = extract_cv_keywords(resume_text)
                jd_keywords = extract_jd_keywords(job_description, requirements)
                
                if not jd_keywords:
                    return {'similarity_score': 0, 'is_match': False}
                
                common = cv_keywords.intersection(jd_keywords)
                match_percent = (len(common) / len(jd_keywords)) * 100
                
                return {
                    'similarity_score': match_percent / 100,  # Convert percentage to 0-1 scale
                    'is_match': match_percent >= (threshold * 100),
                    'matching_keywords': list(common)
                }
            else:
                return {'similarity_score': 0, 'is_match': False, 'matching_keywords': []}
        else:
            # Use the TF-IDF and cosine similarity approach
            # Preprocess texts
            processed_resume = self.preprocess_text(resume_text)
            processed_job = self.preprocess_text(job_description)
            if requirements:
                processed_job += " " + self.preprocess_text(requirements)
            
            # Vectorize texts
            vectorizer = TfidfVectorizer()
            vectors = vectorizer.fit_transform([processed_job, processed_resume])
            
            # Calculate cosine similarity
            similarity = cosine_similarity(vectors[0:1], vectors[1:2])[0][0]
            
            # Determine if it's a match
            is_match = similarity >= threshold
            
            return {
                'similarity_score': similarity,
                'is_match': is_match
            }
    
    def load_job_descriptions_from_csv(self, csv_path):
        """Load job descriptions from a CSV file"""
        try:
            job_df = pd.read_csv(csv_path)
            required_cols = ['id', 'title', 'description']
            
            if not all(col in job_df.columns for col in required_cols):
                missing = [col for col in required_cols if col not in job_df.columns]
                raise ValueError(f"CSV missing required columns: {', '.join(missing)}")
                
            return self.load_job_descriptions(job_df)
        except Exception as e:
            print(f"Error loading job descriptions from CSV: {str(e)}")
            return False
            
    def match_cv_folder_with_jobs(self, cv_folder, job_df, threshold=0.6, use_simple_matching=True):
        """Match all CVs in a folder with job descriptions in a DataFrame"""
        results = []
        
        cv_files = [f for f in os.listdir(cv_folder) if f.lower().endswith('.pdf')]
        
        for cv_file in cv_files:
            cv_path = os.path.join(cv_folder, cv_file)
            cv_text = extract_text_from_pdf(cv_path)
            
            best_score = 0
            best_match_id = None
            best_match_title = None
            best_match_keywords = []
            
            for _, row in job_df.iterrows():
                match_result = self.match_resume_to_job(
                    cv_text, 
                    row['description'], 
                    row.get('requirements', None),
                    threshold, 
                    use_simple_matching
                )
                
                match_score = match_result['similarity_score']
                if match_score > best_score:
                    best_score = match_score
                    best_match_id = row['id']
                    best_match_title = row['title']
                    best_match_keywords = match_result.get('matching_keywords', [])
            
            # Convert score to percentage
            score_percent = best_score * 100 if not use_simple_matching else best_score
            
            results.append({
                'cv_filename': cv_file,
                'name': cv_file.split('.')[0].replace('_', ' ').title(),  # Simple name extraction
                'best_match_job_id': best_match_id,
                'best_match_job_title': best_match_title,
                'match_score': score_percent, 
                'is_match': score_percent >= (threshold * 100),
                'matching_keywords': best_match_keywords
            })
            
        return pd.DataFrame(results)

# Function to determine if a candidate should be shortlisted
def should_shortlist_candidate(match_score, threshold=0.7):
    """Determine if a candidate should be shortlisted based on match score"""
    return match_score >= threshold 