# VERB – Verbal Communication & Interview Practice App

**Author:** Uraib Shahid  
**University:** NHL Stenden  
**Year:** 2026

---

## What is VERB?

VERB is a web application designed to help users improve their verbal communication and interview skills. Users can select a topic, choose how many questions they want to answer, and complete a mock interview by speaking their answers into the microphone. After the test, VERB analyses the recordings and gives a detailed score breakdown across multiple speaking metrics.

---

## Features

- Register and login system with local SQLite database
- Choose between 3 interview topics: Behavioral, Computer Science, or Cyber Security
- Questions randomly selected from curated JSON question banks sourced from Glassdoor and real candidate interview reports (Google, Amazon, Meta, Microsoft)
- Voice recording using the browser's MediaRecorder API
- 15 second preparation timer before each question, then automatic recording starts
- Audio transcription using OpenAI Whisper (tiny model)
- Scoring across 4 metrics: Speaking Time, Repetition, Pauses, Terminology
- Visual results page with animated score rings and overall score out of 100
- Fully structured using Object-Oriented Programming (OOP)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python, Flask |
| Database | SQLite |
| Transcription | OpenAI Whisper |
| Audio conversion | FFmpeg |
| Audio recording | MediaRecorder API (browser) |

---

## Project Structure
```
verb/
├── app.py                  # Flask app — all routes and OOP classes
├── scoring.py              # Scorer class — audio analysis and metric scoring
├── data/
│   ├── behavioral/
│   │   └── questions.json
│   ├── computer_science/
│   │   ├── algorithms/
│   │   │   └── questions.json
│   │   └── technical/
│   │       └── questions.json
│   └── cyber_security/
│       └── questions.json
├── database/
│   └── verb.db             # SQLite database (auto-created on first run)
├── audio/                  # Saved recordings per user (auto-created)
├── static/
│   └── css/
│       └── styles.css
└── templates/
    ├── base.html
    ├── regilog.html        # Login & Register page
    ├── index.html          # Home page
    ├── interview.html      # Interview setup page
    ├── test.html           # Test/recording page
    └── results.html        # Results page
```

---

## How to Run

### 1. Install dependencies
```bash
pip install flask whisper numpy
```

### 2. Install FFmpeg

Download from https://ffmpeg.org and add it to your system PATH.

### 3. Run the app
```bash
python app.py
```

### 4. Open in browser

Go to `http://127.0.0.1:5000`

---

## How it Works

1. User registers and logs in
2. On the home page, clicks "Start Interview Test"
3. Selects a topic (Behavioral / Computer Science / Cyber Security) and number of questions (5, 10, or 15)
4. Test begins — each question fades in, a 15 second prep timer counts down automatically, then the microphone starts recording
5. User answers the question and presses the mic button to stop
6. Audio is saved to the server and the next question loads
7. After all questions are done, the app redirects to the results page
8. Flask processes all audio files — converts to WAV using FFmpeg, transcribes with Whisper, runs scoring functions
9. Results are displayed with animated score rings and an overall score out of 100

---

## Scoring System

| Metric | Weight | Description |
|---|---|---|
| Speaking Time | 30% | How long the user spoke vs ideal answer length |
| Pauses | 25% | Silence gaps detected in the audio |
| Terminology | 25% | Relevant keywords used in the answer |
| Repetition | 20% | Word diversity — how much the user repeated themselves |

---

## OOP Structure

| Class | Responsibility |
|---|---|
| `Database` | SQLite connection, user creation, user lookup |
| `QuestionLoader` | Loading and randomly selecting questions from JSON files |
| `AudioManager` | Saving, clearing, and managing audio files per user |
| `Scorer` | All audio processing, transcription, and metric scoring |

---

## Question Sources

Questions are sourced from aggregated interview reports on Glassdoor, LeetCode discussions, and candidate experiences from interviews at Google, Amazon, Meta, and Microsoft. They are stored locally in JSON format with metadata including category, difficulty, frequency, and source.

---

## Notes

- This app runs fully locally — no internet connection required after setup
- The `audio/` and `database/` folders are excluded from version control
- Whisper runs on CPU using the `tiny` model for speed
