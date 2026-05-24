"""
╔══════════════════════════════════════════════════════════════╗
║   LLM-Powered Answer Engine for Job Application Bots        ║
║   Uses Ollama (local LLM) for intelligent form filling      ║
╚══════════════════════════════════════════════════════════════╝

Replaces the dumb keyword-matching find_answer() with a 3-tier system:
  1. Deterministic rules (personal info — instant)
  2. Keyword matching (SAVED_ANSWERS — instant)
  3. Ollama LLM (intelligent fallback — 1-3 seconds)
"""

import json
import urllib.request
import urllib.error
import logging
import config

log = logging.getLogger(__name__)

# ─── Cache to avoid duplicate LLM calls ─────────────────────
_answer_cache = {}


# ─── Build Profile Context for LLM ──────────────────────────
def _build_profile_context():
    """Build a rich text context from all config.py data."""
    p = config.PERSONAL
    e = config.EDUCATION
    exp = config.EXPERIENCE
    w = config.WORK_AUTH
    s = config.SKILLS

    context = f"""CANDIDATE PROFILE:
- Name: {p['first_name']} {p['last_name']}
- Email: {p['email']}
- Phone: {p['phone']}
- Location: {p['location']} ({p['city']}, {p['state']}, {p['country']})
- Zip Code: {p['zip_code']}
- Gender: {p['gender']}
- Age: {p['age']}
- LinkedIn: {p['linkedin_url']}
- GitHub: {config.GITHUB_URL}
- Portfolio: {config.PORTFOLIO_URL}

EDUCATION:
- {e['degree']} from {e['university']}
- Graduation Year: {e['graduation_year']}
- GPA/CGPA: {e['gpa']}
- Highest Level: {e['highest_level']}

EXPERIENCE:
- Total Years: {exp['total_years']}
- Current Company: {exp['current_company']}
- Current Title: {exp['current_title']}
- Current Salary: {exp['current_salary']} {exp['currency']}
- Expected Salary: {exp['expected_salary']} {exp['currency']}

WORK AUTHORIZATION:
- Authorized to work in India: {w['authorized_to_work']}
- Require visa sponsorship: {w['require_sponsorship']}
- Notice period: {w['notice_period']}
- Willing to relocate: {w['willing_to_relocate']}
- Open to remote work: {w['remote_work']}

TECHNICAL SKILLS:
- Programming Languages: {', '.join(s.get('languages', []))}
- Frameworks: {', '.join(s.get('frameworks', []))}
- Databases: {', '.join(s.get('databases', []))}
- Cloud & DevOps: {', '.join(s.get('cloud_devops', []))}
- AI/ML: {', '.join(s.get('ai_ml', []))}
- Tools: {', '.join(s.get('tools', []))}

LANGUAGES SPOKEN: {', '.join(config.LANGUAGES_SPOKEN)}

CERTIFICATIONS: {'; '.join(config.CERTIFICATIONS)}"""
    return context


# ─── System Prompt (built once, cached) ──────────────────────
_SYSTEM_PROMPT = None

def _get_system_prompt():
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        profile = _build_profile_context()
        _SYSTEM_PROMPT = f"""You are a job application form assistant. You answer questions for a candidate applying to jobs.

{profile}

STRICT RULES — follow these exactly:
1. Give SHORT, DIRECT answers only. No explanations, no reasoning, no preamble.
2. For Yes/No questions → answer ONLY "Yes" or "No".
3. For numeric questions (years, salary, count) → answer with ONLY a number.
4. For technology experience questions (e.g., "years of Python experience"):
   - If the candidate knows the technology → answer "1"
   - If they don't know it → answer "0"
5. When dropdown options are provided → respond with the EXACT text of the best matching option.
6. For text fields asking "why" or "describe" → give a 1-2 sentence professional answer.
7. For name/contact/URL fields → use the candidate's actual data.
8. For salary → use annual INR figures unless the question specifies otherwise.
9. For willingness questions (relocate, travel, remote, overtime) → answer "Yes".
10. For cover letter requests → write 2-3 concise, professional sentences about the candidate's fit.
11. NEVER say "I don't know", "N/A", or ask clarifying questions. Always provide a concrete answer.
12. NEVER wrap your answer in quotes unless the question asks for a quoted string.
13. If the question mentions a specific skill/technology the candidate does NOT have, be honest but brief (say "0" for years or "No" for familiarity)."""
    return _SYSTEM_PROMPT


# ─── Ollama API Call ─────────────────────────────────────────
def _call_ollama(question, options=None):
    """Call Ollama local LLM to get an intelligent answer."""
    prompt = f'Job application form question: "{question}"'
    if options:
        # Filter out empty options
        clean_options = [o.strip() for o in options if o.strip() and o.strip() != "Select an option"]
        if clean_options:
            prompt += f"\n\nAvailable options to choose from:\n"
            for i, opt in enumerate(clean_options, 1):
                prompt += f"  {i}. {opt}\n"
            prompt += "\nRespond with EXACTLY one of the options above, word for word."
    prompt += "\n\nYour answer:"

    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": _get_system_prompt()},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,   # Low temperature for consistent answers
            "num_predict": 150,   # Keep answers short
        }
    }

    try:
        url = f"{config.OLLAMA_URL}/api/chat"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            answer = result.get("message", {}).get("content", "").strip()

            # Clean up common LLM artifacts
            answer = answer.strip('"\'')
            # Remove "Answer:" prefix if model adds it
            for prefix in ["Answer:", "answer:", "A:", "Response:", "response:", "My answer:", "The answer is:"]:
                if answer.startswith(prefix):
                    answer = answer[len(prefix):].strip()
            # Take only first line if multi-line (for short-answer fields)
            if options or len(answer) > 200:
                answer = answer.split('\n')[0].strip()

            log.info(f"🤖 LLM answered: '{question[:50]}' → '{answer[:80]}'")
            return answer

    except urllib.error.URLError as e:
        log.warning(f"⚠️ Ollama not reachable: {e}. Is Ollama running? (Run: ollama serve)")
        return None
    except Exception as e:
        log.warning(f"⚠️ LLM call failed: {e}")
        return None


# ─── Deterministic Answers (no LLM needed) ───────────────────
def _deterministic_answer(question):
    """Answer common personal-info questions instantly without LLM."""
    q = question.lower().strip()
    p = config.PERSONAL

    # Name
    if any(w in q for w in ["first name", "given name"]):
        return p["first_name"]
    if any(w in q for w in ["last name", "surname", "family name"]):
        return p["last_name"]
    if any(w in q for w in ["full name", "your name", "candidate name"]):
        return f"{p['first_name']} {p['last_name']}"

    # Contact
    if any(w in q for w in ["email", "e-mail"]):
        return p["email"]
    if any(w in q for w in ["phone", "mobile", "contact number", "cell number"]):
        return p["phone"]

    # Location
    if "city" in q and "current" not in q.replace("current city", ""):
        pass  # Let keyword or LLM handle generic "city" mentions
    if any(w in q for w in ["current city", "city you live"]):
        return p["city"]
    if any(w in q for w in ["state", "province"]):
        return p["state"]
    if any(w in q for w in ["zip", "pin code", "postal"]):
        return p["zip_code"]
    if "country" in q:
        return p["country"]
    if "location" in q and ("current" in q or "your" in q):
        return p["location"]

    # URLs
    if "linkedin" in q:
        return p["linkedin_url"]
    if "github" in q:
        return config.GITHUB_URL
    if any(w in q for w in ["portfolio", "website", "personal site", "personal url"]):
        return config.PORTFOLIO_URL

    # Demographics
    if "gender" in q:
        return p["gender"]
    if "age" in q:
        return p["age"]
    if any(w in q for w in ["ethnicity", "race"]):
        return p.get("ethnicity", "Asian")
    if "veteran" in q:
        return p.get("veteran", "No")
    if "disability" in q or "handicap" in q:
        return p.get("disability", "No")

    # Education
    if any(w in q for w in ["university", "college", "school name", "institution"]):
        return config.EDUCATION["university"]
    if any(w in q for w in ["graduation year", "year of graduation", "passing year", "passed out"]):
        return config.EDUCATION["graduation_year"]
    if any(w in q for w in ["gpa", "cgpa", "grade point"]):
        return config.EDUCATION["gpa"]
    if any(w in q for w in ["degree", "qualification"]) and "highest" not in q:
        return config.EDUCATION["degree"]
    if "highest" in q and any(w in q for w in ["education", "degree", "qualification"]):
        return config.EDUCATION["highest_level"]

    # Current work
    if any(w in q for w in ["current company", "current employer", "present company", "company name"]):
        return config.EXPERIENCE["current_company"]
    if any(w in q for w in ["current title", "current role", "current position", "designation", "job title"]):
        return config.EXPERIENCE["current_title"]

    return None


# ─── Keyword Matching (from SAVED_ANSWERS) ───────────────────
def _keyword_match(question):
    """Original keyword matching logic — uses config.SAVED_ANSWERS."""
    q = question.lower().strip()
    for keyword, answer in config.SAVED_ANSWERS.items():
        if keyword.lower() in q:
            return str(answer)

    # Fixed fallbacks using config values (BUG FIX: was hardcoded "5")
    if any(w in q for w in ["year", "experience", "how long", "how many"]):
        return config.EXPERIENCE.get("total_years", "1")
    if any(w in q for w in ["salary", "ctc", "compensation", "pay", "package"]):
        return config.EXPERIENCE.get("current_salary", "800000")
    if any(w in q for w in ["notice", "join", "start date", "available from"]):
        return config.WORK_AUTH.get("notice_period", "Immediately")

    return None


# ─── Main Entry Point ────────────────────────────────────────
def find_answer(question_text, options=None):
    """
    Smart 3-tier answer engine:
      1. Deterministic rules (personal info — instant, free)
      2. Keyword matching (SAVED_ANSWERS — instant, free)
      3. Ollama LLM (intelligent — 1-3 seconds)

    Args:
        question_text: The question/label text from the application form
        options: Optional list of dropdown/radio option strings

    Returns:
        str: The best answer
    """
    if not question_text or not question_text.strip():
        return "Yes"

    # Cache key includes options for dropdown-specific answers
    cache_key = f"{question_text.strip().lower()}|{','.join(options) if options else ''}"
    if cache_key in _answer_cache:
        return _answer_cache[cache_key]

    # ── Tier 1: Deterministic (instant) ──
    answer = _deterministic_answer(question_text)
    if answer:
        _answer_cache[cache_key] = answer
        log.info(f"📋 Deterministic: '{question_text[:40]}' → '{answer[:30]}'")
        return answer

    # ── Tier 2: Keyword match (instant) ──
    answer = _keyword_match(question_text)
    if answer:
        _answer_cache[cache_key] = answer
        log.info(f"🔑 Keyword: '{question_text[:40]}' → '{answer[:30]}'")
        return answer

    # ── Tier 3: Ollama LLM (smart fallback) ──
    answer = _call_ollama(question_text, options)
    if answer:
        _answer_cache[cache_key] = answer
        return answer

    # ── Ultimate fallback ──
    log.warning(f"⚠️ All tiers failed for: '{question_text[:60]}' → defaulting to 'Yes'")
    _answer_cache[cache_key] = "Yes"
    return "Yes"
