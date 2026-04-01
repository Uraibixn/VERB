import os
import json
import wave
import contextlib
import subprocess
import numpy as np
import whisper


class Scorer:
    HALLUCINATIONS = ["thank you", "thanks for watching", "you", ".", ""]
    STOP_WORDS = {
        "the","a","an","and","or","but","in","on","at","to",
        "for","of","i","we","it","is","was","that","this","you"
    }

    def __init__(self, model_size="tiny"):
        self.model = whisper.load_model(model_size)

    # ── audio utilities ──────────────────────────────────────────────

    def convert_to_wav(self, input_path, output_path):
        command = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-ar", "16000",
            "-ac", "1",
            output_path
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            print(f"Conversion failed for {input_path}: {result.stderr.decode()}")
        else:
            print(f"Converted {input_path} to {output_path}")

    def is_too_short(self, filepath, min_seconds=2.0):
        try:
            with contextlib.closing(wave.open(filepath, 'r')) as f:
                frames = f.getnframes()
                rate   = f.getframerate()
                if rate <= 0:
                    return True
                return (frames / float(rate)) < min_seconds
        except Exception:
            return True

    def transcribe(self, filepath):
        result     = self.model.transcribe(filepath, fp16=False)
        transcript = result.get("text", "").strip()
        if transcript.lower() in self.HALLUCINATIONS:
            return ""
        return transcript

    # ── scoring metrics ──────────────────────────────────────────────

    def score_speaking_time(self, filepath, ideal_min=30, ideal_max=90):
        try:
            with contextlib.closing(wave.open(filepath, 'r')) as f:
                duration = f.getnframes() / float(f.getframerate())
        except Exception:
            duration = 0

        if ideal_min <= duration <= ideal_max:
            score = 100
        elif duration < ideal_min:
            penalty = int(((ideal_min - duration) / ideal_min) * 100)
            score   = max(0, 100 - penalty)
        else:
            penalty = min(20, int(((duration - ideal_max) / ideal_max) * 100))
            score   = max(0, 100 - penalty)

        return max(0, min(100, score)), round(duration, 1)

    def score_repetition(self, transcript):
        words    = [w.strip('.,!?').lower() for w in transcript.split()]
        filtered = [w for w in words if w not in self.STOP_WORDS and len(w) > 2]
        total    = len(filtered)

        if total == 0:
            return 0, 0

        repeated = total - len(set(filtered))
        flaw     = int((repeated / total) * 100)
        return max(0, min(100, 100 - flaw)), repeated

    def score_terminology(self, transcript, keywords):
        if not keywords:
            return 75, 0

        found  = sum(1 for kw in keywords if kw.lower() in transcript.lower())
        missed = len(keywords) - found
        flaw   = int((missed / len(keywords)) * 100)
        return max(0, min(100, 100 - flaw)), found

    def score_pauses(self, filepath):
        try:
            with contextlib.closing(wave.open(filepath, 'r')) as wf:
                frames      = wf.readframes(wf.getnframes())
                audio       = np.frombuffer(frames, dtype=np.int16)
                sample_rate = wf.getframerate()
        except Exception:
            return 0, 0

        duration = len(audio) / sample_rate if sample_rate > 0 else 0
        if duration < 0.5:
            return 0, 0

        audio           = np.abs(audio)
        silence_samples = int(sample_rate * 0.8)
        silent          = audio < 500
        pause_count     = 0
        current_silence = 0

        for s in silent:
            if s:
                current_silence += 1
            else:
                if current_silence >= silence_samples:
                    pause_count += 1
                current_silence = 0

        if current_silence >= silence_samples:
            pause_count += 1

        flaw_map = {0: 0, 1: 15, 2: 15, 3: 35, 4: 35, 5: 55, 6: 55}
        flaw     = flaw_map.get(pause_count, 75)
        return max(0, min(100, 100 - flaw)), pause_count

    def calculate_overall(self, scores):
        return int(
            scores["time"]        * 0.30 +
            scores["repetition"]  * 0.20 +
            scores["pause"]       * 0.25 +
            scores["terminology"] * 0.25
        )

    def score_to_color(self, score):
        if score >= 70:
            return "#C8F135"
        elif score >= 45:
            return "#e67e22"
        else:
            return "#c0392b"

    # ── main analysis ─────────────────────────────────────────────────

    def analyze_all(self, username, questions):
        audio_folder = f"audio/{username}"
        score_folder = os.path.join(audio_folder, "scores")
        os.makedirs(score_folder, exist_ok=True)

        total_time  = []
        total_rep   = []
        total_pause = []
        total_term  = []

        worst_time  = (101, "N/A")
        worst_rep   = (101, "N/A")
        worst_pause = (101, "N/A")
        worst_term  = (101, "N/A")

        for i, q in enumerate(questions):
            q_label    = f"Q{i + 1}"
            score_file = os.path.join(score_folder, f"q{i}.json")

            if os.path.exists(score_file):
                with open(score_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                t = data.get("t", 0)
                r = data.get("r", 0)
                p = data.get("p", 0)
                k = data.get("k", 0)
                duration = data.get("duration", 0)
                r_count  = data.get("r_count",  0)
                p_count  = data.get("p_count",  0)
                k_found  = data.get("k_found",  0)
                print(f"{q_label} loaded from cache")

            else:
                wav_path = None
                for ext in [".webm", ".m4a"]:
                    candidate = os.path.join(audio_folder, f"q{i}{ext}")
                    if os.path.exists(candidate):
                        wav_path = os.path.join(audio_folder, f"q{i}.wav")
                        self.convert_to_wav(candidate, wav_path)
                        break

                if wav_path is None or not os.path.exists(wav_path):
                    print(f"No audio for {q_label}, scoring 0")
                    t = r = p = k = duration = r_count = p_count = k_found = 0

                elif self.is_too_short(wav_path):
                    print(f"{q_label} too short, scoring 0")
                    t = r = p = k = duration = r_count = p_count = k_found = 0

                else:
                    transcript = self.transcribe(wav_path)
                    print(f"{q_label} transcript: {transcript}")

                    if not transcript.strip():
                        print(f"{q_label} silent, scoring 0")
                        t = r = p = k = duration = r_count = p_count = k_found = 0
                    else:
                        keywords  = q.get("keywords", [])
                        target    = q.get("target_time", 40)
                        ideal_min = max(5, target - 10)
                        ideal_max = target + 15

                        t, duration = self.score_speaking_time(wav_path, ideal_min, ideal_max)
                        r, r_count  = self.score_repetition(transcript)
                        p, p_count  = self.score_pauses(wav_path)
                        k, k_found  = self.score_terminology(transcript, keywords)

                with open(score_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        "t": t, "r": r, "p": p, "k": k,
                        "transcript": transcript if 'transcript' in locals() else "",
                        "duration": duration, "r_count": r_count,
                        "p_count": p_count, "k_found": k_found
                    }, f)

            total_time.append(t)
            total_rep.append(r)
            total_pause.append(p)
            total_term.append(k)

            if t < worst_time[0]:
                worst_time = (t, f"{q_label} ({duration}s)")
            if r < worst_rep[0]:
                worst_rep = (r, f"{q_label} ({r_count} repeated words)")
            if p < worst_pause[0]:
                worst_pause = (p, f"{q_label} ({p_count} pauses)")
            if k < worst_term[0]:
                worst_term = (k, f"{q_label} ({k_found} keywords matched)")

        n         = len(questions)
        time_pct  = int(sum(total_time)  / n) if n else 0
        rep_pct   = int(sum(total_rep)   / n) if n else 0
        pause_pct = int(sum(total_pause) / n) if n else 0
        term_pct  = int(sum(total_term)  / n) if n else 0

        scores  = {"time": time_pct, "repetition": rep_pct,
                   "pause": pause_pct, "terminology": term_pct}
        overall = self.calculate_overall(scores)

        metrics = [
            {"label": "Speaking Time", "pct": time_pct,  "score": f"{time_pct/10:.1f}/10",
             "color": self.score_to_color(time_pct),  "worst": worst_time[1],
             "detail": "Based on ideal answer length per question.", "row": 1},
            {"label": "Repetition",    "pct": rep_pct,   "score": f"{rep_pct/10:.1f}/10",
             "color": self.score_to_color(rep_pct),   "worst": worst_rep[1],
             "detail": "Measures word diversity across answers.", "row": 1},
            {"label": "Pauses",        "pct": pause_pct, "score": f"{pause_pct/10:.1f}/10",
             "color": self.score_to_color(pause_pct), "worst": worst_pause[1],
             "detail": "Detected silence pauses in speech.", "row": 1},
            {"label": "Terminology",   "pct": term_pct,  "score": f"{term_pct/10:.1f}/10",
             "color": self.score_to_color(term_pct),  "worst": worst_term[1],
             "detail": "Keyword matches in your answers.", "row": 2},
        ]

        return metrics, overall