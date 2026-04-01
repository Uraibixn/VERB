from scoring import analyze_all  # import your scoring functions

# ✅ Step 1: Define your 7 test questions with all scoring metadata
questions = [
    {
        "question": "Stack vs Queue",
        "keywords": ["Last-In-First-Out", "First-In-First-Out", "recursion", "backtracking", "scheduling", "breadth-first search"],
        "target_time": 20,  # seconds
        "pauses": ["…", "… Stacks… stacks"],
        "repetitions": ["Stacks… stacks"]
    },
    {
        "question": "Deadlock in Operating Systems",
        "keywords": ["deadlock", "processes", "resources"],
        "target_time": 35,
        "pauses": ["…", "… a traffic jam"],
        "repetitions": ["traffic jam… a traffic jam"]
    },
    {
        "question": "Symmetric vs Asymmetric Encryption",
        "keywords": ["symmetric encryption", "asymmetric encryption", "public key", "private key", "decryption"],
        "target_time": 50,
        "pauses": ["…", "… which is slower"],
        "repetitions": []
    },
    {
        "question": "Binary Search",
        "keywords": ["binary search", "algorithm", "sorted array", "target"],
        "target_time": 25,
        "pauses": ["…", "… until it finds"],
        "repetitions": []
    },
    {
        "question": "Process vs Thread",
        "keywords": ["process", "thread", "memory space", "execution"],
        "target_time": 40,
        "pauses": ["…", "… that shares"],
        "repetitions": ["Threads are faster… faster"]
    },
    {
        "question": "Polymorphism in OOP",
        "keywords": ["polymorphism", "object", "interface", "classes"],
        "target_time": 20,
        "pauses": ["…", "… like using"],
        "repetitions": []
    },
    {
        "question": "SQL Injection",
        "keywords": ["SQL injection", "SQL code", "database", "prepared statements", "parameterized queries", "input validation"],
        "target_time": 55,
        "pauses": ["…", "… prepared statements"],
        "repetitions": ["prepared statements… prepared statements"]
    }
]

# ✅ Step 2: Run the analysis on the folder containing your recordings
metrics, overall = analyze_all("test_user", questions)

# ✅ Step 3: Print the metrics nicely
print("------ METRICS ------")
for m in metrics:
    print(f"{m['label']}: {m['pct']}% | Worst: {m['worst']} | Detail: {m['detail']}")
print("--------------------")
print("OVERALL SCORE:", overall)