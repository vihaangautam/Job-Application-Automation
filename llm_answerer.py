"""
╔══════════════════════════════════════════════════════════════╗
║   LLM-Powered Answer Engine for Job Application Bots         ║
║   Uses Ollama (local LLM) for intelligent form filling       ║
╚══════════════════════════════════════════════════════════════╝

Replaces the dumb keyword-matching find_answer() with a 3-tier system:
  1. Deterministic rules (personal info — instant)
  2. Keyword matching (SAVED_ANSWERS — instant)
  3. Ollama LLM (intelligent fallback — 1-3 seconds)

Includes SQLite caching to prevent redundant local LLM calls.
"""

import json
import difflib
import urllib.request
import urllib.error
import logging
import sqlite3
import hashlib
import re
import config

log = logging.getLogger(__name__)

# ─── SQLite Cache to avoid duplicate LLM calls ─────────────────────
DB_PATH = "answer_cache.db"

def init_cache():
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                answer TEXT
            )
        """)
        con.commit()
        con.close()
    except Exception as e:
        log.warning(f"Cache database init failed: {e}")

# Initialize the cache database when the module is imported
init_cache()

def cache_key(question, options, is_numeric=False):
    raw = question.strip().lower() + str(sorted(options or [])) + f"|num:{is_numeric}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def get_cached(question, options, is_numeric=False):
    try:
        key = cache_key(question, options, is_numeric)
        con = sqlite3.connect(DB_PATH)
        row = con.execute("SELECT answer FROM cache WHERE key=?", (key,)).fetchone()
        con.close()
        return row[0] if row else None
    except Exception as e:
        log.debug(f"Cache read error: {e}")
        return None

def set_cached(question, options, answer, is_numeric=False):
    try:
        key = cache_key(question, options, is_numeric)
        con = sqlite3.connect(DB_PATH)
        con.execute("INSERT OR REPLACE INTO cache VALUES (?,?)", (key, answer))
        con.commit()
        con.close()
    except Exception as e:
        log.debug(f"Cache write error: {e}")

# ─── Build Profile Context for LLM ──────────────────────────
def _build_profile_context():
    """Build a rich text context from all config.py data and inject detailed resume if available."""
    import os
    p = config.PERSONAL
    e = config.EDUCATION
    exp = config.EXPERIENCE
    w = config.WORK_AUTH
    
    # Clone technical skills from config to avoid mutating original
    s = {k: list(v) for k, v in config.SKILLS.items()}
    
    # Dynamically inject enabled adjacent skills to the profile context
    adaptive_cfg = getattr(config, "ADAPTIVE_LYING", {})
    if adaptive_cfg.get("enabled", False):
        adjacent_skills = adaptive_cfg.get("adjacent_skills", {})
        for skill_name, is_enabled in adjacent_skills.items():
            if is_enabled:
                name_cap = skill_name.capitalize()
                if skill_name.lower() == "typescript" and "TypeScript" not in s["languages"]:
                    s["languages"].append("TypeScript")
                elif skill_name.lower() == "flask" and "Flask" not in s["frameworks"]:
                    s["frameworks"].append("Flask")
                elif skill_name.lower() == "graphql" and "GraphQL" not in s["databases"]:
                    s["databases"].append("GraphQL")
                elif skill_name.lower() not in ["typescript", "flask", "graphql"]:
                    # Fallback general injection
                    if name_cap not in s["tools"]:
                        s["tools"].append(name_cap)

    base = f"""CANDIDATE PROFILE:
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

    # Inject detailed SDE resume if available
    resume_path = getattr(config, "RESUME_TXT_PATH", "resume.md")
    if os.path.exists(resume_path):
        try:
            with open(resume_path, "r", encoding="utf-8") as f:
                resume_text = f.read()
            base += f"\n\nDETAILED RESUME & PROJECTS:\n{resume_text}"
        except Exception as err:
            log.warning(f"Failed to read detailed resume file at {resume_path}: {err}")
    
    return base.strip()


# ─── Ollama API Call ─────────────────────────────────────────
def _call_ollama(question, options=None, is_numeric=False):
    """Call Ollama local LLM to get an intelligent answer based on prompt constraints."""
    profile = _build_profile_context()

    # Construct smart extrapolation / adaptive lying guidelines if enabled in config
    adaptive_guidelines = ""
    adaptive_cfg = getattr(config, "ADAPTIVE_LYING", {})
    if adaptive_cfg.get("enabled", False):
        adjacent = [k for k, v in adaptive_cfg.get("adjacent_skills", {}).items() if v]
        non_adjacent = [k for k, v in adaptive_cfg.get("adjacent_skills", {}).items() if not v]
        default_unknown = adaptive_cfg.get("default_unknown", "1")
        adaptive_guidelines = f"""
ADAPTIVE SKILLS RULES (Case-Insensitive):
If asked about a technology/skill NOT explicitly mentioned in the profile or resume:
- If it matches a skill in this learnable list {adjacent} (case-insensitive): answer "Yes" or "{default_unknown}".
- Otherwise (or if it matches a skill in {non_adjacent}): answer "No" or "0".
"""

    if options:
        # Dropdown Option Picker
        prompt = f"""You are filling a job application form.
CANDIDATE PROFILE:
{profile}
{adaptive_guidelines}
QUESTION: {question}
You MUST answer with EXACTLY one of the following available options, word for word, and absolutely nothing else:
{chr(10).join(options)}

Answer:"""
    elif is_numeric:
        # Numeric field
        prompt = f"""You are filling a job application form.
CANDIDATE PROFILE:
{profile}
{adaptive_guidelines}
QUESTION: {question}
Reply with a single integer only. No words, no units, no punctuation.
Answer:"""
    else:
        # Free text description
        prompt = f"""You are filling a job application form.
CANDIDATE PROFILE:
{profile}
{adaptive_guidelines}
QUESTION: {question}
Reply in under 10 words. Be specific, concise, and highly professional.
Answer:"""

    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,   # Low temperature for highly consistent answers
            "num_predict": 100,   # Keep answers short
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
            for prefix in ["Answer:", "answer:", "A:", "Response:", "response:", "My answer:", "The answer is:"]:
                if answer.startswith(prefix):
                    answer = answer[len(prefix):].strip()
            # Split lines for dropdowns or numeric fields
            if options or is_numeric or len(answer) > 200:
                answer = answer.split('\n')[0].strip()

            log.info(f"🤖 LLM answered: '{question[:50]}' → '{answer[:80]}'")
            return answer

    except urllib.error.URLError as e:
        log.warning(f"⚠️ Ollama not reachable: {e}. Is Ollama running?")
        return None
    except Exception as e:
        log.warning(f"⚠️ LLM call failed: {e}")
        return None


# ─── Deterministic Answers (no LLM needed) ───────────────────
def _deterministic_answer(question):
    """Answer common personal-info questions instantly without LLM using strict word boundaries."""
    q = question.lower().strip()
    p = config.PERSONAL
    e = config.EDUCATION
    exp = config.EXPERIENCE

    # Name
    if re.search(r"\bfirst\s*name\b|\bgiven\s*name\b", q):
        return p["first_name"]
    if re.search(r"\blast\s*name\b|\bsurname\b|\bfamily\s*name\b", q):
        return p["last_name"]
    if re.search(r"\bfull\s*name\b|\byour\s*name\b|\bcandidate\s*name\b", q):
        return f"{p['first_name']} {p['last_name']}"

    # Contact
    if re.search(r"\bemail\b|\be-mail\b", q):
        return p["email"]
    if re.search(r"\bphone\b|\bmobile\b|\bcontact\s*number\b|\bcell\s*number\b", q):
        return p["phone"]

    # Location
    if re.search(r"\bcurrent\s*city\b|\bcity\s*you\s*live\b", q):
        return p["city"]
    if re.search(r"\bstate\b|\bprovince\b", q):
        return p["state"]
    if re.search(r"\bzip\b|\bpin\s*code\b|\bpostal\b", q):
        return p["zip_code"]
    if re.search(r"\bcountry\b", q):
        return p["country"]
    if re.search(r"\blocation\b", q) and re.search(r"\b(current|your)\b", q):
        return p["location"]

    # URLs
    if re.search(r"\blinkedin\b", q):
        return p["linkedin_url"]
    if re.search(r"\bgithub\b", q):
        return config.GITHUB_URL
    if re.search(r"\bportfolio\b|\bwebsite\b|\bpersonal\s*(site|url)\b", q):
        return config.PORTFOLIO_URL

    # Demographics
    if re.search(r"\bgender\b", q):
        return p["gender"]
    if re.search(r"\bage\b|\byour\s*age\b|\bage\s*\(years\)", q):
        return p["age"]
    if re.search(r"\bethnicity\b|\brace\b", q):
        return p.get("ethnicity", "Asian")
    if re.search(r"\bveteran\b", q):
        return p.get("veteran", "No")
    if re.search(r"\bdisability\b|\bhandicap\b", q):
        return p.get("disability", "No")

    # Education
    if re.search(r"\buniversity\b|\bcollege\b|\bschool\s*name\b|\binstitution\b", q):
        return e["university"]
    if re.search(r"\bgraduation\s*year\b|\byear\s*of\s*graduation\b|\bpassing\s*year\b|\bpassed\s*out\b", q):
        return e["graduation_year"]
    if re.search(r"\bgpa\b|\bcgpa\b|\bgrade\s*point\b", q):
        return e["gpa"]
    if re.search(r"\bdegree\b|\bqualification\b", q) and not re.search(r"\bhighest\b", q):
        return e["degree"]
    if re.search(r"\bhighest\b", q) and re.search(r"\b(education|degree|qualification)\b", q):
        return e["highest_level"]

    # Current work
    if re.search(r"\bcurrent\s*company\b|\bcurrent\s*employer\b|\bpresent\s*company\b|\bcompany\s*name\b", q):
        return exp["current_company"]
    if re.search(r"\bcurrent\s*title\b|\bcurrent\s*role\b|\bcurrent\s*position\b|\bdesignation\b|\bjob\s*title\b", q):
        return exp["current_title"]

    return None


# ─── Keyword Matching (from SAVED_ANSWERS) ───────────────────
def _keyword_match(question):
    """Original keyword matching logic — uses config.SAVED_ANSWERS with precise word boundaries."""
    q = question.lower().strip()
    
    # 1. Loop through SAVED_ANSWERS using word boundaries
    for keyword, answer in config.SAVED_ANSWERS.items():
        kw = keyword.lower().strip()
        # Use regex to match the exact keyword as a phrase/word boundary
        if re.search(r'\b' + re.escape(kw) + r'\b', q):
            # Special guard: if keyword is generic experience but question asks about a specific technology, bypass
            if kw in ["years of experience", "experience"] and len(q.replace(kw, "").strip()) > 5:
                continue
            return str(answer)

    # 2. Generic Fallbacks (ONLY triggers on general profile questions, NOT skill-specific questions)
    has_general_word = re.search(r"\b(overall|total|professional|work)\b", q)
    has_exp_word = re.search(r"\b(year|years|experience)\b", q)
    
    is_generic_experience = (has_general_word and has_exp_word) or (q in ["years of experience", "experience", "experience (years)"])
    
    if is_generic_experience:
        return config.EXPERIENCE.get("total_years", "1")
        
    if re.search(r"\b(salary|expected ctc|current ctc|compensation|pay|package)\b", q):
        if re.search(r"\b(expected|target)\b", q):
            return config.EXPERIENCE.get("expected_salary", "1200000")
        return config.EXPERIENCE.get("current_salary", "800000")
        
    if re.search(r"\b(notice|join|start date|available from)\b", q):
        return config.WORK_AUTH.get("notice_period", "Immediately")

    return None


# ─── Main Entry Point ────────────────────────────────────────
def find_answer(question_text, options=None, is_numeric=False):
    """
    Smart 3-tier answer engine:
      1. Deterministic rules (personal info — instant, free)
      2. Keyword matching (SAVED_ANSWERS — instant, free)
      3. Ollama LLM (intelligent — 1-3 seconds)

    Args:
        question_text: The question/label text from the application form
        options: Optional list of dropdown/radio option strings
        is_numeric: If True, constraints LLM output to integers only

    Returns:
        str: The best answer
    """
    if not question_text or not question_text.strip():
        return "Yes"

    # SQLite Cache Lookup
    cached = get_cached(question_text, options, is_numeric)
    if cached is not None:
        return cached

    # ── Tier 1: Deterministic (instant) ──
    answer = _deterministic_answer(question_text)
    if answer:
        set_cached(question_text, options, answer, is_numeric)
        log.info(f"📋 Deterministic: '{question_text[:40]}' → '{answer[:30]}'")
        return answer

    # ── Tier 2: Keyword match (instant) ──
    answer = _keyword_match(question_text)
    if answer:
        set_cached(question_text, options, answer, is_numeric)
        log.info(f"🔑 Keyword: '{question_text[:40]}' → '{answer[:30]}'")
        return answer

    # ── Tier 3: Ollama LLM (smart fallback) ──
    answer = _call_ollama(question_text, options, is_numeric)
    if answer:
        set_cached(question_text, options, answer, is_numeric)
        return answer

    # ── Ultimate fallback ──
    fallback_val = "1" if is_numeric else "Yes"
    log.warning(f"⚠️ All tiers failed for: '{question_text[:60]}' → defaulting to '{fallback_val}'")
    set_cached(question_text, options, fallback_val, is_numeric)
    return fallback_val


# ─── Fuzzy Option Matcher ────────────────────────────────────
def best_match_option(answer, options):
    """
    Given an LLM answer and a list of available form options,
    return the best-matching option string.

    Cascade:
      1. Exact match
      2. Case-insensitive exact match
      3. Substring containment (answer in option or option in answer)
      4. difflib fuzzy match (threshold > 0.5)
      5. Return first option as last resort
    """
    if not options:
        return answer
    if not answer:
        return options[0] if options else ""

    answer_clean = answer.strip()

    # 1. Exact match
    for opt in options:
        if opt.strip() == answer_clean:
            return opt

    # 2. Case-insensitive exact match
    answer_lower = answer_clean.lower()
    for opt in options:
        if opt.strip().lower() == answer_lower:
            return opt

    # 3. Substring containment
    for opt in options:
        opt_lower = opt.strip().lower()
        if answer_lower in opt_lower or opt_lower in answer_lower:
            return opt

    # 4. Fuzzy match (difflib)
    matches = difflib.get_close_matches(answer_clean, [o.strip() for o in options], n=1, cutoff=0.5)
    if matches:
        for opt in options:
            if opt.strip() == matches[0]:
                return opt

    # 5. Last resort: return first option
    log.warning(f"⚠️ No good match for '{answer_clean}' in {options}. Using first option: '{options[0]}'")
    return options[0]
