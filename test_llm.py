import sys
import os
import logging

# Configure basic logging to see llm_answerer output
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler(sys.stdout)])

# Reconfigure stdout/stderr to UTF-8 on Windows to prevent UnicodeEncodeError when printing emojis
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from llm_answerer import find_answer

# Clear out database caches for these test queries so we get live LLM answers
import sqlite3
try:
    con = sqlite3.connect("answer_cache.db")
    con.execute("DELETE FROM cache")
    con.commit()
    con.close()
    print("🧹 Cleared LLM cache database for clean verification.")
except Exception as e:
    print(f"⚠️ Cache clear skipped: {e}")

tests = [
    # (question, options, is_numeric, expected_keyword_or_value)
    ("What is your age?", None, False, "21"),
    ("What programming language do you prefer?", ["Python", "Java", "Go"], False, "Python"),
    ("Years of experience with FastAPI?", None, True, "1"),
    ("Do you have experience with Django?", ["Yes", "No"], False, "Yes"),
    ("Years of experience with Swift?", None, True, "0"),  # swift is False in adjacent_skills -> Should be "0"
    ("Do you have experience with Flask?", ["Yes", "No"], False, "Yes"),  # flask is True in adjacent_skills -> Should be "Yes"
    ("What is your current CTC?", None, True, "800000"),  
    ("Percentage of time managing stakeholders?", None, True, "40"),  # shouldn't trigger age! (no 21)
    ("Do you have agentic workflow experience?", ["Yes", "No"], False, "Yes"),  # shouldn't trigger age! (no 21)
]

print("\n" + "="*80)
print("🧪 RUNNING LLM ENGINE & DYNAMIC CONTEXT INTEGRATION TESTS")
print("="*80)

failures = 0
for q, opts, is_num, expected in tests:
    result = find_answer(q, options=opts, is_numeric=is_num)
    status = "✅"
    
    # Check if expected is correctly matched
    expected_lower = str(expected).lower()
    result_lower = str(result).lower()
    
    if expected_lower not in result_lower and result_lower not in expected_lower:
        status = "❌"
        failures += 1
        
    print(f"{status} Q: '{q}'\n   → Got: '{result}' (Expected: '{expected}')\n")

print("="*80)
if failures == 0:
    print("🏆 ALL INTEGRATION TESTS PASSED SUCCESSFULLY!")
else:
    print(f"⚠️ TEST SUITE COMPLETED WITH {failures} FAILURE(S).")
print("="*80 + "\n")
