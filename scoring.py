import os
import json
import wave
import contextlib
import subprocess
import numpy as np
import whisper  # 67


class Scorer: # in this class everything related to score lives inside of this
    HALLUCINATIONS = ["thank you", "thanks for watching", "you", ".", ""] # when theres bits of silence whisper ERROR
    STOP_WORDS = {
        "the","a","an","and","or","but","in","on","at","to",
        "for","of","i","we","it","is","was","that","this","you"
    } # the words that do not count while measuring the repetition 

    # def __init__ runs when u load in an object it intializes / constructs 

    def __init__(self, model_size="tiny"):
        self.model = whisper.load_model(model_size)
        # here we load in the whisper AI model into the memory, 
        # tiny is the shortest and lightest version

    # ── audio utilities ──────────────────────────────────────────────
    # the browser records in webm but whisper needs wav

    # conversion
    # we convert this using ffmpeg (external audio tool )
    def convert_to_wav(self, input_path, output_path):
        command = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-ar", "16000", # sets the sample rate to 16000 Hz
            "-ac", "1", # mono (1 channel)
            output_path
        ] # why? because whisper works best with those settings.

        # so subproccess.run (runs ffmpeg which then uses "command" as in the input)
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # instead of printing the errors we store them using stdout=subprocess.PIPE(normal messages), stderr=subprocess.PIPE
        # subproccess.run runs a system (like i would in the terminal)

        #return code (did it succeed or fail)
        if result.returncode != 0:
            print(f"Conversion failed for {input_path}: {result.stderr.decode()}")
            # the stored errors are in bytes, decode converts it into strings so its readable text and we can print it.
        else:
            print(f"Converted {input_path} to {output_path}")

    def is_too_short(self, filepath, min_seconds=2.0): # here we check if the audio is too short 
        # (to score it 0)
        try:
            with contextlib.closing(wave.open(filepath, 'r')) as f:
                # contextlib.closing Ensures file is properly closed after use
                frames = f.getnframes()
                # frames are tiny chunks of audio data, audio -> frames, images -> pixels. 
                # here we get the number of frames.

                # here we get sample rate of frames (how many frames per second)
                rate   = f.getframerate()

                # prevent division errors

                if rate <= 0:
                    return True
                # heres how we get the duration of the audio. 
                return (frames / float(rate)) < min_seconds
        except Exception:
            return True

    def transcribe(self, filepath):

        # self.model (using the whisper model) 
        # transcribe (runs the speech to text)


        result     = self.model.transcribe(filepath, fp16=False)
        # dont use 16 bit floating point precision, more compatible, slower but safer

#exmaple of result (its a dictionary)
#         {
#   "text": "Hello my name is John",
#   "segments": [...],
#   "language": "en"
# }
        # since we only care about the text (if missing return "")
        transcript = result.get("text", "").strip() # the strip removes spaces and newlines
        if transcript.lower() in self.HALLUCINATIONS: # check for hallucinations
            return ""
        return transcript

    # ── scoring metrics ──────────────────────────────────────────────
    
    # Too short  → heavy penalty
    # Ideal length → perfect score
    # Too long  → small penalty

    def score_speaking_time(self, filepath, ideal_min=30, ideal_max=90):
        try:
            with contextlib.closing(wave.open(filepath, 'r')) as f:
                # Open the audio file safely and make sure it gets closed (opening the file)
                # calculating the duration of the file
                duration = f.getnframes() / float(f.getframerate())
        except Exception:
            duration = 0 # if any error happens assume 0 seconds. 

        if ideal_min <= duration <= ideal_max: # the perfect length
            score = 100
        elif duration < ideal_min: # the short length
            penalty = int(((ideal_min - duration) / ideal_min) * 100) # so basically how far below minimum are you?
            # 30 - 15 (duration) = 15 
            # calculate ratio         / idea_min(30) = 0.5
            # (this means ur missing 50% of ur required time. 0.5)
            # convert ratio to percentage     0.5 * 100 = penalty (50)

            score   = max(0, 100 - penalty) # max(0,) prevents negative scores
        else: # the long length (too long)
            penalty = min(20, int(((duration - ideal_max) / ideal_max) * 100)) 
            # here the penalty is capped at 20, why?
            # being too long isnt as bad as too short. 
            score   = max(0, 100 - penalty) 

        return max(0, min(100, score)), round(duration, 1) 
        # returns score (0 and 100), returns rounded up duration (upto 1 decimal 42.3 sec)

    # more repetetions lower score, more variety higher score
    def score_repetition(self, transcript):
        # clean and normalize words; 
        # transcript.split() -> "Hello, I am here!" → ["Hello,", "I", "am", "here!"] (splits sentences into words)
        # w.strip removes punctuation, lower converts to lowercase
        words    = [w.strip('.,!?').lower() for w in transcript.split()]

        # filter removes useless words (stop words)
        filtered = [w for w in words if w not in self.STOP_WORDS and len(w) > 2]

        # count total meaningful words
        total    = len(filtered)

        # avoid division by 0, no meaningful words = zero score
        if total == 0:
            return 0, 0

        repeated = total - len(set(filtered)) # counting repeated words
        # len(set(filtered)) number of unique words

        flaw     = int((repeated / total) * 100) # What percentage of words are repeated


        return max(0, min(100, 100 - flaw)), repeated

    # Checks if the user used the required keywords in their answer
    # Gives a score based on how many keywords were missed
    def score_terminology(self, transcript, keywords):
        if not keywords: # if keywords list is empty return average score (75, 0 keywords found)
            return 75, 0

        found  = sum(1 for kw in keywords if kw.lower() in transcript.lower())
        # looping over keywords (converting the keywords into lower and checking in list and then keeping count)


        missed = len(keywords) - found # counting missed keywords

        flaw   = int((missed / len(keywords)) * 100) # calculate the flaw % 
        return max(0, min(100, 100 - flaw)), found #Score = 100 - flaw, Clamped between 0 and 100, Also return found for feedback


        # keywords = ["apple", "banana", "cherry"]
        # transcript = "I ate an apple and a cherry"

        # Loop → check each keyword:
        # "apple" → yes → 1
        # "banana" → no → 0
        # "cherry" → yes → 1

        # Sum → 1 + 0 + 1 = 2 found

    def score_pauses(self, filepath):  # detecting pauses in the persons speech
        # too many pauses = lower score
        try:
            with contextlib.closing(wave.open(filepath, 'r')) as wf:
                # open WAV in read mode 
                frames      = wf.readframes(wf.getnframes()) # reading all the audio frames
                audio       = np.frombuffer(frames, dtype=np.int16) # converting audio binary data into numbers
                # int 16 because WAV is usually 16-bit
                sample_rate = wf.getframerate() # samples per seconds (rates of frames per seconds)
        except Exception:
            return 0, 0

        duration = len(audio) / sample_rate if sample_rate > 0 else 0
        # len(audio) / sample_rate → total seconds
        if duration < 0.5: # preventing scoring extremely short clips
            return 0, 0

        audio           = np.abs(audio) # Only care about amplitude, ignore negative values (sound wave can go below 0)
        silence_samples = int(sample_rate * 0.8) # How many samples = 0.8 seconds

        # 0.8s is considered a “pause”

        silent          = audio < 500 # boolean array, if amplitude < 500 (consider silent)
        # Essentially: mark every tiny chunk of audio as silent or not


        pause_count     = 0 # default values
        current_silence = 0 # default values

        for s in silent: # loop through every frame
            if s: 
                current_silence += 1 # count consecutive silent frames
            else:
                if current_silence >= silence_samples: # if current silence is long enough to be a real pause
                    pause_count += 1 # increase the pause counter
                current_silence = 0 # back to default value

        if current_silence >= silence_samples:
            pause_count += 1

        flaw_map = {0: 0, 1: 15, 2: 15, 3: 35, 4: 35, 5: 55, 6: 55}
        # 0 pauses 0 pen, 1-2 15 pen, 3-4 35 pen, 5-6, 55 pen, more than 6 is 75 pen
        flaw     = flaw_map.get(pause_count, 75) # default 75 penalty if it goes more than 6 
        return max(0, min(100, 100 - flaw)), pause_count
        # Clamped to 0-100, also returning pause_count for feedback.

    def calculate_overall(self, scores): # combining the 4 metrics into 1 overall score
        
        # scores is a dictionary like:
        # scores = {
        #     "time": 85,        # speaking time score
        #     "repetition": 90,  # repetition score
        #     "pause": 70,       # pause score
        #     "terminology": 80  # keyword score
        # }

        # overall= time∗0.30 + repetition∗0.20 + pause∗0.25 + terminology∗0.25


        return int(
            scores["time"]        * 0.30 +
            scores["repetition"]  * 0.20 +
            scores["pause"]       * 0.25 +
            scores["terminology"] * 0.25
        )

    def score_to_color(self, score): # mapping the numeric score to visual color
        # basically for fun and shows how bad or good a score is with COLOORRS :)
        if score >= 70:
            return "#C8F135"
        elif score >= 45:
            return "#e67e22"
        else:
            return "#c0392b"

    # ── main analysis ─────────────────────────────────────────────────

    def analyze_all(self, username, questions):
        # audio_folder → where all the user’s audio files live (audio/username)
        audio_folder = f"audio/{username}"
        # score_folder → where we save cached scores per question
        score_folder = os.path.join(audio_folder, "scores")
        # os.makedirs(..., exist_ok=True) → create the folder if it doesn’t exist
        os.makedirs(score_folder, exist_ok=True)

        # List to collect scores for all questions.
        total_time  = []
        total_rep   = []
        total_pause = []
        total_term  = []

        # tracking the worst scoring question for each metric
        # 101 is jst a placeholder (insuring it will be between 0 to 100 (always lower than 101))
        worst_time  = (101, "N/A")
        worst_rep   = (101, "N/A")
        worst_pause = (101, "N/A")
        worst_term  = (101, "N/A")

        # here we loop through questions for the user
        for i, q in enumerate(questions): #enumerate keeps track of the index and the data of the index
            q_label    = f"Q{i + 1}" # user-friendly label, like Q1
            score_file = os.path.join(score_folder, f"q{i}.json") # the cached JSON path for this question (file/folder path)


            # if we have already scored this question, load it (saving time)
            if os.path.exists(score_file):
                with open(score_file, 'r', encoding='utf-8') as f: # utf ensures we read all characters safely (letters, punctuations)
                    data = json.load(f) # Reads the JSON file content and converts it into a Python dictionary
                t = data.get("t", 0) # getting the value for a key safely (if none then returns 0 default instead of crashing)
                r = data.get("r", 0)
                p = data.get("p", 0)
                k = data.get("k", 0)
                duration = data.get("duration", 0)
                r_count  = data.get("r_count",  0)
                p_count  = data.get("p_count",  0)
                k_found  = data.get("k_found",  0)
                print(f"{q_label} loaded from cache") # prints the cache 

            else:
                wav_path = None
                # checking if theres audio for this question
                for ext in [".webm", ".m4a"]:
                    candidate = os.path.join(audio_folder, f"q{i}{ext}")
                    if os.path.exists(candidate):
                        wav_path = os.path.join(audio_folder, f"q{i}.wav")
                        self.convert_to_wav(candidate, wav_path)  # convert it into wav for proccessing
                        break

                # Handle missing or too short audio
                # If no audio → give 0 score
                # If audio is too short → give 0 score
                
                if wav_path is None or not os.path.exists(wav_path):
                    print(f"No audio for {q_label}, scoring 0")
                    t = r = p = k = duration = r_count = p_count = k_found = 0

                elif self.is_too_short(wav_path):
                    print(f"{q_label} too short, scoring 0")
                    t = r = p = k = duration = r_count = p_count = k_found = 0

                # Transcribe & Score

                else:
                    transcript = self.transcribe(wav_path)
                    print(f"{q_label} transcript: {transcript}") # prints the transcript (answer) for each question

                    # if text is empty give score 0
                    if not transcript.strip():
                        print(f"{q_label} silent, scoring 0")
                        t = r = p = k = duration = r_count = p_count = k_found = 0
                    else:
                        # calculate all four metrics using the functions we already went through
                        keywords  = q.get("keywords", [])
                        target    = q.get("target_time", 40)
                        ideal_min = max(5, target - 10)
                        ideal_max = target + 15

                        t, duration = self.score_speaking_time(wav_path, ideal_min, ideal_max)
                        r, r_count  = self.score_repetition(transcript)
                        p, p_count  = self.score_pauses(wav_path)
                        k, k_found  = self.score_terminology(transcript, keywords)

                # here we save the score for future,
                # stores the score, transcripts and counts (caching)
                with open(score_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        "t": t, "r": r, "p": p, "k": k,
                        "transcript": transcript if 'transcript' in locals() else "",
                        "duration": duration, "r_count": r_count,
                        "p_count": p_count, "k_found": k_found
                    }, f)

            # here we track the totals and the worst answers

            total_time.append(t) # appending here to calculate average later
            total_rep.append(r)
            total_pause.append(p)
            total_term.append(k) # append basically adds to the end of the list

            # compare to current worst
            if t < worst_time[0]:
                worst_time = (t, f"{q_label} ({duration}s)") # updating the new current worst now
            if r < worst_rep[0]:
                worst_rep = (r, f"{q_label} ({r_count} repeated words)")
            if p < worst_pause[0]:
                worst_pause = (p, f"{q_label} ({p_count} pauses)")
            if k < worst_term[0]:
                worst_term = (k, f"{q_label} ({k_found} keywords matched)")

        n         = len(questions) # which is the length of how many questions the program asked
        time_pct  = int(sum(total_time)  / n) if n else 0 # if n else 0 is a safeguard if the list is empty
        rep_pct   = int(sum(total_rep)   / n) if n else 0
        pause_pct = int(sum(total_pause) / n) if n else 0
        term_pct  = int(sum(total_term)  / n) if n else 0

        scores  = {"time": time_pct, "repetition": rep_pct,
                   "pause": pause_pct, "terminology": term_pct}
        # combining it into a dictionary 

        overall = self.calculate_overall(scores)
        # calling the function, 
        # Gives one overall score combining all metrics using the weights: t 30 r 20 p 25 k 25

        metrics = [
            # here pct is the percentage score
            # label is a name for the metrics
            # score converts the percentage into a scale of 0 to 10 for display value
            {"label": "Speaking Time", "pct": time_pct,  "score": f"{time_pct/10:.1f}/10",
             "color": self.score_to_color(time_pct),  "worst": worst_time[1],
             #color sets the color based on the score, 
             #worst shows which question was worst for this metric
             "detail": "Based on ideal answer length per question.", "row": 1},
             #detail description for UI or report, row used for layout
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
        # returns metrics: detailed data for each metric for UI/report
        # return overall: single score combining everything