import gitlab
import re
import os
import google.generativeai as genai

from dotenv import load_dotenv

# -----------------------------
# LOAD ENV
# -----------------------------
load_dotenv(".env.local")

GITLAB_URL = os.getenv("GITLAB_URL")
PRIVATE_TOKEN = os.getenv("PRIVATE_TOKEN")
PROJECT_ID = os.getenv("PROJECT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# -----------------------------
# VALIDATE ENV
# -----------------------------
required_vars = {
    "GITLAB_URL": GITLAB_URL,
    "PRIVATE_TOKEN": PRIVATE_TOKEN,
    "PROJECT_ID": PROJECT_ID,
    "GEMINI_API_KEY": GEMINI_API_KEY
}

for key, value in required_vars.items():
    if not value:
        raise Exception(f"Missing {key}")

# -----------------------------
# CONFIGURE GEMINI
# -----------------------------
genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel(
    "gemini-3.5-flash"
)

# -----------------------------
# CONNECT TO GITLAB
# -----------------------------
print("\nConnecting to GitLab...\n")

gl = gitlab.Gitlab(
    GITLAB_URL,
    private_token=PRIVATE_TOKEN
)

project = gl.projects.get(PROJECT_ID)

print(f"Connected to project: {project.name}")

# -----------------------------
# FIND FAILED PIPELINE
# -----------------------------
print("\nSearching for failed pipeline...\n")

pipelines = project.pipelines.list(
    order_by="updated_at",
    sort="desc"
)

failed_pipeline = None

for pipeline in pipelines:

    if pipeline.status == "failed":
        failed_pipeline = pipeline
        break

if not failed_pipeline:
    print("No failed pipeline found.")
    exit()

print(f"Found failed pipeline: {failed_pipeline.id}")

# -----------------------------
# FETCH LOGS
# -----------------------------
jobs = failed_pipeline.jobs.list()

structured_errors = []

for job in jobs:

    build_job = project.jobs.get(job.id)

    print(f"\nChecking Job: {build_job.name}")

    raw_log = build_job.trace()

    log = raw_log.decode("utf-8", errors="ignore")

    matches = re.findall(
        r'([A-Za-z0-9_/\.-]+\.java):\[(\d+),(\d+)\] (.*)',
        log
    )

    for match in matches:

        structured_errors.append({
            "job": build_job.name,
            "file": match[0],
            "line": match[1],
            "column": match[2],
            "error": match[3]
        })

# -----------------------------
# PRINT STRUCTURED ERRORS
# -----------------------------
print("\n==============================")
print("STRUCTURED BUILD ERRORS")
print("==============================\n")

if not structured_errors:
    print("No structured errors found.")
    exit()

seen = set()

for err in structured_errors:

    unique_key = (
        err["file"],
        err["line"],
        err["column"],
        err["error"]
    )

    if unique_key in seen:
        continue

    seen.add(unique_key)

    print(f"Job    : {err['job']}")
    print(f"File   : {err['file']}")
    print(f"Line   : {err['line']}")
    print(f"Column : {err['column']}")
    print(f"Error  : {err['error']}")
    print()

    # -----------------------------
    # GEMINI ANALYSIS
    # -----------------------------
    prompt = f"""
You are a senior Java and Spring Boot build engineer.

Analyze this compilation failure.

File:
{err['file']}

Line:
{err['line']}

Column:
{err['column']}

Error:
{err['error']}

Provide:
1. Root cause
2. Exact fix
3. Minimal safe patch
4. Correct code example
"""

    print("Sending error to Gemini...\n")

    response = model.generate_content(prompt)

    print("==============================")
    print("GEMINI ANALYSIS")
    print("==============================\n")

    print(response.text)

    print("\n====================================\n")