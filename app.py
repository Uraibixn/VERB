import os
import time
import threading
from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3
from datetime import datetime
import json
import random
import shutil
import requests
from scoring import Scorer

app = Flask(__name__)
app.secret_key = "verb_secret_key"


class Database:

    def __init__(self, db_path="database/verb.db"):
        self.db_path = db_path

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self):
        conn = self.get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close() 

    def find_user(self, username, password): 
        conn = self.get_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ? AND password = ?",
            (username, password)
        ).fetchone()
        conn.close()
        return user

    def create_user(self, username, email, password):
        conn = self.get_connection()
        conn.execute(
            "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
            (username, email, password)
        )
        conn.commit()
        conn.close()


class QuestionLoader:
    def __init__(self):
        self.paths = {
            "behavioral":    "data/behavioral/questions.json",
            "cs_behavioral": "data/behavioral/questions.json",
            "cs_algorithms": "data/computer_science/algorithms/questions.json",
            "cs_technical":  "data/computer_science/technical/questions.json",
            "cyber_behavioral": "data/behavioral/questions.json",
            "cyber":         "data/cyber_security/questions.json",
        }

    def load(self, path):
        with open(path) as f:
            return json.load(f)

    def get_questions(self, topic, length): # a function that helps finding the right questions
        questions = []

        if topic == "cs": # for the topic of computer science

            # theres 3 different types of cs questions.
            behavioral = self.load(self.paths["cs_behavioral"])
            algorithms = self.load(self.paths["cs_algorithms"])
            technical  = self.load(self.paths["cs_technical"])

            if behavioral: 
                questions.append(random.choice(behavioral))

            remaining = length - len(questions)
            if remaining > 0:
                num_alg  = remaining // 2
                num_tech = remaining - num_alg
                questions += random.sample(algorithms, min(num_alg, len(algorithms)))
                questions += random.sample(technical,  min(num_tech, len(technical)))

        elif topic == "cyber":
            behavioral = self.load(self.paths["cyber_behavioral"])
            cyber      = self.load(self.paths["cyber"])
            questions += random.sample(behavioral, min(1, len(behavioral)))
            questions += random.sample(cyber, min(length - len(questions), len(cyber)))

        else:
            all_questions = self.load(self.paths["behavioral"])
            questions = random.sample(all_questions, min(length, len(all_questions)))

        return questions[:length]


class AudioManager: # here we check the audio
    def __init__(self, base_folder="audio"):
        self.base_folder = base_folder

    def get_folder(self, username):
        return os.path.join(self.base_folder, username)

    def clear(self, username):
        folder = self.get_folder(username)
        if os.path.exists(folder):
            shutil.rmtree(folder)

    def save(self, audio_file, username, q_index):
        folder = self.get_folder(username)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"q{q_index}.webm")
        audio_file.save(path)
        return path


# instantiate shared objects
db       = Database()
loader   = QuestionLoader()
audio_mgr = AudioManager()
scorer   = Scorer()


def _get_transcript_for_followup(username, question_text, question_index=None):
    helper_start = time.time()
    if question_index is None:
        questions = session.get("questions", [])
        try:
            question_index = questions.index(question_text)
        except ValueError:
            return ""

    audio_path = os.path.join(audio_mgr.get_folder(username), f"q{question_index}.webm")
    if not os.path.exists(audio_path):
        return ""

    try:
        transcription_start = time.time()
        transcript = scorer.transcribe(audio_path)
        transcription_elapsed = time.time() - transcription_start
        print(f"[TIMING] Whisper transcription: {transcription_elapsed:.2f}s")
        helper_elapsed = time.time() - helper_start
        print(f"[TIMING] Transcript lookup + transcription helper: {helper_elapsed:.2f}s")
        return transcript
    except Exception as exc:
        print(f"Follow-up transcription failed for q{question_index}: {exc}")
        return ""


def generate_followup_question(question, transcript): 
    # this the prompt thats given to llama
    # i provide the function both the question, and the answer*(transcript)
    prompt = f"""
You are a strict technical interviewer.

You will be given:
- a question
- a candidate answer

Your job is to write ONE follow-up question.

IMPORTANT STYLE RULES:
- Ask ONLY ONE question
- Maximum 18 words
- Must be short, sharp, and spoken naturally
- No explanations
- No prefaces
- No framing like "Can you explain", "How does", "What do you mean" unless necessary
- Avoid long academic wording
- Do NOT combine multiple questions

CONTENT RULES:
- The question MUST reference something specific from the candidate answer
- Focus on the MOST interesting or technical point they mentioned
- If they mention a technology -> drill into that technology
- If they mention a project -> drill into that project
- If they mention an algorithm -> drill into complexity, edge cases, or implementation
- If they are vague -> force clarification with a concrete example request

GOOD STYLE EXAMPLES:
- "What was the hardest bug you hit in Unity?"
- "Where does DFS fail in real graphs?"
- "How did you measure performance there?"
- "What broke in production?"
- "Why was that approach necessary?"

BAD STYLE (FORBIDDEN):
- "Can you explain more about your experience and how it relates to..."
- "How would you implement this in a real-world scenario considering..."
- "Could you elaborate on the tradeoffs between..."

OUTPUT FORMAT:
Return ONLY the question. No quotes. No labels.


Candidate question:
{question}

Candidate answer:
{transcript}
""".strip()
    
    # used for debugging purposes

    print("\n=== FOLLOW UP DEBUG ===")
    print("QUESTION:", question)
    print("TRANSCRIPT:", transcript)
    print("=======================\n")

    for model in ("llama3", "mistral"): #trying llama 3 first (fallback -> mistral)
        try:
            start_time = time.time()
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,   
                    "stream": False,
                },
                timeout=120,
            )
            response.raise_for_status()
            elapsed = time.time() - start_time
            print(f"OLLAMA RESPONSE TIME: {elapsed:.2f}s")
            data = response.json()
            followup = data.get("response", "").strip()
            if followup:
                print("\n=== FOLLOW UP GENERATED ===")
                print(followup)
                print("==========================\n")
                return followup
        except requests.RequestException as exc:
            print(f"Ollama error with {model}: {exc}")
        except ValueError as exc:
            print(f"Invalid Ollama response with {model}: {exc}")

    return "Can you explain that in more detail?"

# i warm up the model here so when the website loads in the model is already ready

def _warmup_ollama():
    print("Warming up Ollama...")
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3",
                "prompt": "Hi",
                "stream": False,
            },
            timeout=120,
        )
        response.raise_for_status()
        print("Ollama warm-up complete.")
    except requests.RequestException as exc:
        print(f"Ollama warm-up failed: {exc}")


def _start_ollama_warmup():
    warmup_thread = threading.Thread(target=_warmup_ollama, daemon=True)
    warmup_thread.start()


if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    _start_ollama_warmup()


@app.route("/")
def home():
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = db.find_user(username, password)
        if user:
            session["username"] = username
            return redirect("/index")
        else:
            error = "Wrong username or password."
    return render_template("regilog.html", body_class="regilog-page", error=error)


@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"]
    email    = request.form["email"]
    password = request.form["password"]
    try:
        db.create_user(username, email, password)
        return redirect("/login")
    except sqlite3.IntegrityError:
        return render_template("regilog.html", body_class="regilog-page",
                               error="Username or email already exists.")


@app.route("/index")
def index():
    if "username" not in session:
        return redirect("/login")
    return render_template("index.html", body_class="index-page", username=session["username"])


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/interview")
def interview():
    if "username" not in session:
        return redirect("/login")
    date = datetime.now().strftime("%A, %B %d %Y")
    return render_template("interview.html", body_class="interview-page",
                           username=session["username"], date=date)


@app.route("/set_session", methods=["POST"])
def set_session():
    data = request.get_json()
    session["topic"]  = data["topic"]
    session["length"] = data["length"]
    return jsonify({"status": "ok"})


@app.route("/test")
def test():
    if "username" not in session:
        return redirect("/login")

    topic    = session.get("topic", "behavioral")
    length   = int(session.get("length", 5))
    username = session["username"]

    questions = loader.get_questions(topic, length)

    audio_mgr.clear(username)

    session["questions"]      = [q["question"] for q in questions]
    session["questions_full"] = questions
    n = len(questions)
    max_followups = min(3, n)
    follow_up_count = random.randint(1, max_followups) if max_followups > 0 else 0
    follow_up_targets = random.sample(range(n), follow_up_count) if follow_up_count else []

    session["follow_up_targets"] = follow_up_targets
    session["follow_up_remaining"] = follow_up_count
    session["in_follow_up"] = False
    session["current_follow_up_q"] = None

    print("FOLLOW UPS:", session["follow_up_targets"])

    return render_template("test.html", body_class="test-page",
                           questions=questions, username=username,
                           follow_up_targets=session.get("follow_up_targets", []))


@app.route("/save_audio", methods=["POST"])
def save_audio():
    route_start = time.time()
    print("[TIMING] Entered save_audio route")
    audio   = request.files.get("audio")
    q_index = request.form.get("question_index")
    username = session.get("username", "unknown")

    if audio:
        save_start = time.time()
        audio_mgr.save(audio, username, q_index)
        save_elapsed = time.time() - save_start
        print(f"[TIMING] Saved uploaded file: {save_elapsed:.2f}s")

    route_elapsed = time.time() - route_start
    print(f"[TIMING] Total save_audio route duration: {route_elapsed:.2f}s")
    return jsonify({"status": "saved"})


@app.route("/generate_followup", methods=["POST"])
def generate_followup():
    route_start = time.time()
    print("[TIMING] Entered generate_followup route")
    if "username" not in session:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    transcript = (data.get("transcript") or "").strip()
    question_index = data.get("question_index")

    if not question:
        return jsonify({"error": "question is required"}), 400

    if not transcript:
        transcript = _get_transcript_for_followup(session["username"], question, question_index)

    route_helper_start = time.time()
    followup = generate_followup_question(question, transcript)
    route_helper_elapsed = time.time() - route_helper_start
    print(f"[TIMING] generate_followup helper duration: {route_helper_elapsed:.2f}s")

    route_elapsed = time.time() - route_start
    print(f"[TIMING] Total generate_followup route duration: {route_elapsed:.2f}s")
    return jsonify({"followup": followup})


@app.route("/results")
def results():
    if "username" not in session:
        return redirect("/login")

    username  = session["username"]
    questions = session.get("questions_full", [])
    topic     = session.get("topic", "behavioral").capitalize()
    length    = session.get("length", 5)
    date      = datetime.now().strftime("%a, %d %b %Y · %H:%M")

    metrics, overall_score = scorer.analyze_all(username, questions)

    return render_template("results.html",
        body_class="results-page",
        metrics=metrics,
        overall_score=overall_score,
        topic=topic,
        total_questions=length,
        date=date
    )


if __name__ == "__main__":
    db.init()
    app.run(debug=True, port=5000)