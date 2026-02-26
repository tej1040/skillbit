import os
import random
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from passlib.context import CryptContext
from dotenv import load_dotenv
import pypdf

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- DB ---------------- #
def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# ---------------- UTILS ---------------- #
def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

# ---------------- MODELS ---------------- #
class UserSignup(BaseModel):
    email: str
    password: str
    role: str
    name: str
    company: str = ""
    designation: str = ""

class UserLogin(BaseModel):
    email: str
    password: str

class JobPost(BaseModel):
    title: str
    company: str
    location: str
    salary: str
    description: str
    experience: str
    skills: str
    referral_bonus: int
    recruiter_email: str

# ---------------- ROOT ---------------- #
@app.get("/")
def root():
    return {"status": "SkillBit API is running"}

# ---------------- AUTH ---------------- #
@app.post("/api/signup")
def signup(u: UserSignup):
    try:
        with get_conn() as conn:
            with conn.cursor() as c:
                c.execute(
                    """INSERT INTO users
                    (email, password, role, name, tokens, company, designation)
                    VALUES (%s, %s, %s, %s, 50, %s, %s)""",
                    (u.email, get_password_hash(u.password), u.role, u.name, u.company, u.designation),
                )
            conn.commit()
        return {"status": "success"}
    except:
        return {"status": "error", "message": "Email exists"}

@app.post("/api/login")
def login(u: UserLogin):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("SELECT * FROM users WHERE email=%s", (u.email,))
            user = c.fetchone()

    if user and verify_password(u.password, user["password"]):
        return {"status": "success", "user": dict(user)}

    return {"status": "error", "message": "Invalid Credentials"}

# ---------------- JOBS ---------------- #
@app.post("/api/jobs")
def post_job(job: JobPost):
    date = datetime.now().strftime("%Y-%m-%d")

    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                """INSERT INTO jobs
                (title, company, location, salary, description, experience, skills, referral_bonus, recruiter_email, posted_date)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    job.title,
                    job.company,
                    job.location,
                    job.salary,
                    job.description,
                    job.experience,
                    job.skills,
                    job.referral_bonus,
                    job.recruiter_email,
                    date,
                ),
            )
        conn.commit()

    return {"status": "success"}

@app.get("/api/jobs")
def get_jobs(search: str = ""):
    with get_conn() as conn:
        with conn.cursor() as c:
            if search:
                query = f"%{search}%"
                c.execute(
                    """SELECT * FROM jobs
                    WHERE title ILIKE %s OR company ILIKE %s
                    ORDER BY id DESC""",
                    (query, query),
                )
            else:
                c.execute("SELECT * FROM jobs ORDER BY id DESC")

            return c.fetchall()

# ---------------- APPLY ---------------- #
@app.post("/api/apply")
async def apply_for_job(user_email: str = Form(...), job_id: int = Form(...)):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("SELECT * FROM jobs WHERE id=%s", (job_id,))
            job = c.fetchone()

            cost = 6 if job["referral_bonus"] > 0 else 0

            c.execute("SELECT tokens FROM users WHERE email=%s", (user_email,))
            user_tokens = c.fetchone()["tokens"]

            if user_tokens < cost:
                return {"status": "error", "message": "Insufficient Credits"}

            c.execute("UPDATE users SET tokens = tokens - %s WHERE email=%s", (cost, user_email))

            date = datetime.now().strftime("%Y-%m-%d")
            ai_score = random.randint(70, 95)

            c.execute(
                """INSERT INTO applications
                (job_id, user_email, job_title, company, status, date, ai_score)
                VALUES (%s,%s,%s,%s,'Received',%s,%s)""",
                (job_id, user_email, job["title"], job["company"], date, ai_score),
            )

        conn.commit()

    return {"status": "success", "message": "Application Sent!", "ai_score": ai_score}

# ---------------- RESUME UPLOAD ---------------- #
@app.post("/api/upload-resume")
async def upload_resume(email: str = Form(...), resume: UploadFile = File(...)):
    try:
        pdf_reader = pypdf.PdfReader(resume.file)
        text = "".join([page.extract_text() for page in pdf_reader.pages])[:5000]

        with get_conn() as conn:
            with conn.cursor() as c:
                c.execute(
                    "UPDATE users SET resume_text=%s, tokens=tokens+20 WHERE email=%s",
                    (text, email),
                )
            conn.commit()

        return {"status": "success"}

    except:
        return {"status": "error", "message": "Failed"}
