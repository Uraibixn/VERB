import os
from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3
from datetime import datetime
import json
import random
import shutil
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

    def get_questions(self, topic, length):
        questions = []

        if topic == "cs":
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


class AudioManager:
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

    return render_template("test.html", body_class="test-page",
                           questions=questions, username=username)


@app.route("/save_audio", methods=["POST"])
def save_audio():
    audio   = request.files.get("audio")
    q_index = request.form.get("question_index")
    username = session.get("username", "unknown")

    if audio:
        audio_mgr.save(audio, username, q_index)

    return jsonify({"status": "saved"})


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