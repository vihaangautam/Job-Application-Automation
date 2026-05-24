"""
╔══════════════════════════════════════════════════════════════╗
║        LinkedIn Easy Apply Bot — Rayees Yousuf               ║
║        Selenium-based Job Application Automation             ║
╚══════════════════════════════════════════════════════════════╝

Requirements:
    pip install selenium webdriver-manager

Run:
    python job_bot.py
"""

import time
import random
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

# Reconfigure stdout/stderr to UTF-8 on Windows to prevent UnicodeEncodeError when printing emojis
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException,
    ElementNotInteractableException, StaleElementReferenceException
)
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import undetected_chromedriver as uc

import config  # apna config.py
from llm_answerer import find_answer, best_match_option

# ─── Logging Setup ────────────────────────────────────────────
log_file = f"applications_{datetime.now().strftime('%Y%m%d_%H%M')}.log"
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Ensure FileHandler writes with UTF-8 to prevent charmap/UnicodeEncodeError on Windows
has_file_handler = any(isinstance(h, logging.FileHandler) for h in root_logger.handlers)
if not has_file_handler:
    try:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to add UTF-8 FileHandler: {e}")

log = logging.getLogger(__name__)


# ─── Helper: Human-like delay ─────────────────────────────────
def sleep(min_s=1.0, max_s=3.0):
    time.sleep(random.uniform(min_s, max_s))


# ─── Helper: Type like a human ────────────────────────────────
def human_type(element, text):
    element.clear()
    for char in str(text):
        element.send_keys(char)
        time.sleep(random.uniform(0.03, 0.12))


# ─── Helper: React-Friendly Human Clear and Type ───────────────
def human_clear_and_type(field, text):
    """Click, clear using CTRL+A + DELETE (React-friendly), and type with human delays."""
    try:
        field.click()
        sleep(0.1, 0.3)
        field.send_keys(Keys.CONTROL + "a")
        field.send_keys(Keys.DELETE)
        sleep(0.1, 0.2)
        for char in str(text):
            field.send_keys(char)
            time.sleep(random.uniform(0.04, 0.11))
    except Exception as e:
        log.debug(f"Clear and type failed: {e}")


# ─── Helper: Numeric Safety Guard ──────────────────────────────
def sanitize_if_numeric(field, answer, question_text):
    """Detect if field expects numbers and sanitizes LLM output to clean digits."""
    inputmode = field.get_attribute("inputmode") or ""
    field_id = (field.get_attribute("id") or "").lower()
    q = question_text.lower()

    is_numeric = (
        inputmode == "numeric"
        or any(k in field_id for k in ["year", "salary", "ctc", "exp", "experience"])
        or any(k in q for k in ["how many years", "salary", "ctc", "months", "experience"])
    )

    if is_numeric:
        cleaned = re.sub(r"[^\d]", "", str(answer))
        return cleaned if cleaned else "1"
    return answer


# ─── Helper: Human-like Scroll Randomizer ──────────────────────
def human_scroll(driver, container_element):
    """Simulate human-like scrolling inside a result list container."""
    try:
        # Scroll down slightly
        scroll_down = random.randint(280, 420)
        driver.execute_script("arguments[0].scrollTop += arguments[1]", container_element, scroll_down)
        sleep(0.6, 1.4)
        # Slight scroll back (correction)
        scroll_up = random.randint(30, 80)
        driver.execute_script("arguments[0].scrollTop -= arguments[1]", container_element, scroll_up)
        sleep(0.3, 0.7)
    except Exception as e:
        log.debug(f"Human scroll failed: {e}")


# ─── Helper: Safe click ────────────────────────────────────────
def safe_click(driver, element):
    """Attempt standard click first, fallback to JavaScript click if intercepted."""
    try:
        element.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False


# ─── Helper: Get Chrome Major Version ──────────────────────────
def get_chrome_major_version():
    """Dynamically discover the installed Chrome major version on Windows."""
    import os
    import re
    paths = [
        r"C:\Program Files\Google\Chrome\Application",
        r"C:\Program Files (x86)\Google\Chrome\Application",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application")
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                for entry in os.listdir(path):
                    if re.match(r"^\d+(\.\d+)+$", entry):
                        major = entry.split(".")[0]
                        return int(major)
            except Exception as e:
                log.debug(f"Failed to scan directory {path} for Chrome version: {e}")
    return None


# ─── Browser Setup (Undetected Chromedriver) ──────────────────
def get_driver():
    import os
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    
    # ── PERSISTENT PROFILE TO REMEMBER LOGINS AND FORMS ──
    user_data_dir = os.path.join(os.getcwd(), "chrome_profile")
    options.add_argument(f"--user-data-dir={user_data_dir}")

    # uc.Chrome automatically fetches and initializes the best driver manager internally
    chrome_version = get_chrome_major_version()
    if chrome_version:
        log.info(f"Detected Chrome major version: {chrome_version}. Using version_main={chrome_version}")
        driver = uc.Chrome(options=options, version_main=chrome_version)
    else:
        log.info("Could not detect Chrome major version dynamically. Relying on default auto-detection.")
        driver = uc.Chrome(options=options)
        
    return driver


# ─── LinkedIn Login ───────────────────────────────────────────
def linkedin_login(driver):
    log.info("LinkedIn pe login ho raha hai...")
    driver.get("https://www.linkedin.com/login")
    
    print("\n" + "="*60)
    print("🤖 [ACTION REQUIRED] 🤖")
    print("Please login manually in the Chrome window if you aren't already.")
    print("If it asks for OTP or Captcha, please complete it.")
    import os, time
    if not os.environ.get("SKIP_LOGIN_PROMPT"):
        input("👉 Press ENTER here in the terminal when you are fully logged in... ")
    else:
        log.info("Gym mode active! Skipping manual ENTER prompt.")
        time.sleep(3)
    print("="*60 + "\n")
    
    log.info("✅ Proceeding with job application engine...")
    return True


# ─── Search Jobs ──────────────────────────────────────────────
def search_jobs(driver, keyword):
    log.info(f"🔍 Searching: {keyword}")

    url = (
        f"https://www.linkedin.com/jobs/search/?"
        f"keywords={keyword.replace(' ', '%20')}"
        f"&location={config.SEARCH['location'].replace(' ', '%20')}"
        f"&f_AL=true"    # Easy Apply filter
        f"&f_WT=2"       # Remote filter
        f"&f_TPR=r604800" # Past Week (7 Days)
        f"&sortBy=DD"    # Latest first
    )

    # Experience level filter
    exp_map = {
        "Entry Level": "1",
        "Associate": "2",
        "Mid-Senior Level": "3",
        "Director": "4",
    }
    exp_codes = [
        exp_map[e] for e in config.SEARCH["experience_level"] if e in exp_map
    ]
    if exp_codes:
        url += "&f_E=" + "%2C".join(exp_codes)

    driver.get(url)
    sleep(3, 5)


# ─── Get Job Cards ────────────────────────────────────────────
def get_job_cards(driver):
    try:
        wait = WebDriverWait(driver, 10)
        cards = wait.until(EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, ".job-card-container, .jobs-search-results__list-item")
        ))
        return cards
    except TimeoutException:
        log.warning("Job cards nahi mile.")
        return []


# find_answer is imported from llm_answerer.py (LLM-powered)
# best_match_option is imported for fuzzy dropdown/radio matching


# ─── Autocomplete / Typeahead Handler ──────────────────────
def fill_autocomplete_field(driver, field, answer):
    """
    Handle LinkedIn's custom combobox/typeahead inputs.
    These are <input role='combobox'> or inputs with aria-autocomplete.
    Typing spawns a listbox; we must click a suggestion for the value to register.
    """
    try:
        field.clear()
        human_type(field, answer)
        sleep(1.0, 2.0)  # Wait for suggestions to load

        # Look for suggestion listbox appearing
        try:
            listbox = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "div[role='listbox'], ul[role='listbox'], "
                    ".basic-typeahead__triggered-content, "
                    ".fb-typeahead-result-container"
                ))
            )
            suggestions = listbox.find_elements(
                By.CSS_SELECTOR,
                "div[role='option'], li[role='option'], "
                ".basic-typeahead__selectable, "
                ".fb-typeahead-result"
            )

            if suggestions:
                # Find best matching suggestion
                suggestion_texts = [s.text.strip() for s in suggestions if s.text.strip()]
                if suggestion_texts:
                    best = best_match_option(answer, suggestion_texts)
                    for s in suggestions:
                        if s.text.strip() == best:
                            driver.execute_script("arguments[0].click();", s)
                            log.info(f"🎯 Autocomplete: typed '{answer}' → selected '{best}'")
                            return True
                # If no text match, just click first suggestion
                driver.execute_script("arguments[0].click();", suggestions[0])
                log.info(f"🎯 Autocomplete: typed '{answer}' → selected first suggestion")
                return True

        except TimeoutException:
            # No listbox appeared — field might accept raw text
            # Try pressing Enter or Tab to confirm
            field.send_keys(Keys.RETURN)
            sleep(0.3, 0.5)
            log.debug(f"Autocomplete: no suggestions for '{answer}', pressed Enter")
            return True

    except (ElementNotInteractableException, StaleElementReferenceException) as e:
        log.debug(f"Autocomplete fill error: {e}")
        return False


# ─── Fill Form Fields (Enhanced) ─────────────────────────
def fill_field(driver, field, answer, q_text=""):
    """Fill a single form field with the given answer.
    
    Handles: <select>, radio/checkbox, autocomplete combobox, and plain inputs.
    Uses fuzzy matching for dropdowns and smart radio selection.
    """
    tag = field.tag_name.lower()
    field_type = (field.get_attribute("type") or "").lower()

    try:
        if tag == "select":
            sel = Select(field)
            # Get valid option texts (skip placeholders)
            valid_options = [
                opt.text.strip() for opt in sel.options
                if opt.text.strip() and opt.text.strip() not in [
                    "Select an option", "Select", "-- Select --", "Choose...", ""
                ]
            ]
            if valid_options:
                best = best_match_option(answer, valid_options)
                selected = False
                # Try 1: Native Selenium select
                try:
                    sel.select_by_visible_text(best)
                    selected = True
                    log.info(f"📥 Dropdown: '{q_text[:40]}' → '{best}'")
                except Exception:
                    pass
                # Try 2: JavaScript fallback (for hidden/overlay selects)
                if not selected:
                    try:
                        js_result = driver.execute_script("""
                            var sel = arguments[0];
                            var target = arguments[1].trim();
                            for (var i = 0; i < sel.options.length; i++) {
                                if (sel.options[i].text.trim() === target) {
                                    sel.selectedIndex = i;
                                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                                    sel.dispatchEvent(new Event('input', {bubbles: true}));
                                    return true;
                                }
                            }
                            // Partial match fallback
                            var targetLower = target.toLowerCase();
                            for (var i = 0; i < sel.options.length; i++) {
                                var optText = sel.options[i].text.trim().toLowerCase();
                                if (optText.indexOf(targetLower) !== -1 || targetLower.indexOf(optText) !== -1) {
                                    sel.selectedIndex = i;
                                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                                    sel.dispatchEvent(new Event('input', {bubbles: true}));
                                    return true;
                                }
                            }
                            return false;
                        """, field, best)
                        if js_result:
                            selected = True
                            log.info(f"📥 Dropdown (JS): '{q_text[:40]}' → '{best}'")
                    except Exception as e:
                        log.debug(f"JS select failed: {e}")
                # Try 3: Last resort — select first valid option via JS
                if not selected and valid_options:
                    try:
                        driver.execute_script("""
                            var sel = arguments[0];
                            var target = arguments[1].trim();
                            for (var i = 0; i < sel.options.length; i++) {
                                if (sel.options[i].text.trim() === target) {
                                    sel.selectedIndex = i;
                                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                                    sel.dispatchEvent(new Event('input', {bubbles: true}));
                                    break;
                                }
                            }
                        """, field, valid_options[0])
                        log.warning(f"⚠️ Dropdown fallback (JS): '{q_text[:40]}' → '{valid_options[0]}'")
                    except Exception as e:
                        log.debug(f"JS select fallback failed: {e}")
            else:
                log.debug(f"No valid dropdown options found for: {q_text[:40]}")

        elif field_type in ["radio", "checkbox"]:
            # Don't blindly click — handled at question-block level by fill_radio_group()
            if not field.is_selected():
                try:
                    parent_label = field.find_element(By.XPATH, "./following-sibling::label")
                    parent_label.click()
                except Exception:
                    try:
                        driver.execute_script("arguments[0].click();", field)
                    except Exception:
                        field.click()

        elif tag in ["input", "textarea"]:
            if field_type not in ["file", "submit", "button", "hidden"]:
                # Check if this is an autocomplete/combobox field
                role = field.get_attribute("role") or ""
                aria_auto = field.get_attribute("aria-autocomplete") or ""
                if role == "combobox" or aria_auto in ["list", "both"]:
                    fill_autocomplete_field(driver, field, answer)
                else:
                    # Sanitize if numeric
                    answer_clean = sanitize_if_numeric(field, answer, q_text)
                    
                    # Check if field already has the correct value
                    current_val = field.get_attribute("value") or ""
                    if current_val.strip() == str(answer_clean).strip():
                        log.debug(f"Field already has correct value: '{answer_clean}'")
                        return
                    human_clear_and_type(field, answer_clean)

    except (ElementNotInteractableException, StaleElementReferenceException) as e:
        log.debug(f"Field fill error: {e}")


# ─── Fill Radio Group (Smart) ───────────────────────────
def fill_radio_group(driver, q_block, answer):
    """Find the best-matching radio/checkbox option in a question block and click it."""
    try:
        # Find all radio/checkbox inputs with their labels
        radio_inputs = q_block.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
        if not radio_inputs:
            return False

        # Build label-to-input mapping
        options_map = {}  # label_text -> input_element
        for inp in radio_inputs:
            label_text = ""
            try:
                label_el = inp.find_element(By.XPATH, "./following-sibling::label")
                label_text = label_el.text.strip()
            except Exception:
                try:
                    # Try parent label
                    label_el = inp.find_element(By.XPATH, "./ancestor::label")
                    label_text = label_el.text.strip()
                except Exception:
                    pass
            if label_text:
                options_map[label_text] = inp

        if not options_map:
            # No labels found, click first unchecked
            for inp in radio_inputs:
                if not inp.is_selected():
                    safe_click(driver, inp)
                    return True
            return False

        # Use fuzzy matching to find the best label
        best_label = best_match_option(answer, list(options_map.keys()))
        target_input = options_map.get(best_label)

        if target_input and not target_input.is_selected():
            clicked = False
            try:
                label_el = target_input.find_element(By.XPATH, "./following-sibling::label")
                clicked = safe_click(driver, label_el)
            except Exception:
                pass
            if not clicked:
                clicked = safe_click(driver, target_input)
            if clicked:
                log.info(f"🔘 Radio: selected '{best_label}'")
                return True

    except (StaleElementReferenceException, Exception) as e:
        log.debug(f"Radio fill error: {e}")
    return False


# ─── Fill All Form Fields on Current Page ─────────────────────
def fill_form_fields(driver):
    """Scan the current Easy Apply page for all question blocks and fill them."""
    try:
        # Restrict form filling STRICTLY to the active Easy Apply modal container
        # to avoid interacting with background widgets, messaging drawers, or global settings triggers
        container = driver
        for selector in [".jobs-easy-apply-modal", "div[role='dialog']", ".artdeco-modal", ".jobs-easy-apply-content"]:
            try:
                modal_el = driver.find_element(By.CSS_SELECTOR, selector)
                if modal_el.is_displayed():
                    container = modal_el
                    break
            except Exception:
                pass

        questions = container.find_elements(
            By.CSS_SELECTOR,
            ".jobs-easy-apply-form-section__grouping, "
            ".fb-form-element, "
            ".jobs-easy-apply-form-element"
        )

        for q_block in questions:
            try:
                # Extract question text
                label_el = None
                for sel in ["label", ".fb-dash-form-element__label", ".t-bold", "span"]:
                    try:
                        label_el = q_block.find_element(By.CSS_SELECTOR, sel)
                        break
                    except Exception:
                        pass

                q_text = label_el.text if label_el else ""

                # Extract dropdown/radio options for LLM context
                options = []

                # 1. Native <select> options
                try:
                    select_els = q_block.find_elements(By.CSS_SELECTOR, "select")
                    for sel_el in select_els:
                        sel = Select(sel_el)
                        options = [opt.text.strip() for opt in sel.options
                                   if opt.text.strip() and opt.text.strip() not in [
                                       "Select an option", "Select", "-- Select --", "Choose...", ""
                                   ]]
                except Exception:
                    pass

                # 2. Radio button labels
                if not options:
                    try:
                        radio_labels = q_block.find_elements(
                            By.CSS_SELECTOR,
                            "input[type='radio'] + label, "
                            "fieldset label"
                        )
                        options = [lbl.text.strip() for lbl in radio_labels if lbl.text.strip()]
                    except Exception:
                        pass

                # 3. Custom listbox/autocomplete options (LinkedIn-specific)
                if not options:
                    try:
                        listbox_opts = q_block.find_elements(
                            By.CSS_SELECTOR,
                            "div[role='option'], li[role='option'], "
                            ".basic-typeahead__selectable"
                        )
                        options = [opt.text.strip() for opt in listbox_opts if opt.text.strip()]
                    except Exception:
                        pass

                # Determine if numeric context
                is_numeric = False
                try:
                    fields = q_block.find_elements(By.CSS_SELECTOR, "input, select, textarea")
                    for field in fields:
                        if field.tag_name.lower() in ["input", "textarea"]:
                            inputmode = field.get_attribute("inputmode") or ""
                            field_id = (field.get_attribute("id") or "").lower()
                            q = q_text.lower()
                            if (inputmode == "numeric" or 
                                any(k in field_id for k in ["year", "salary", "ctc", "exp", "experience"]) or 
                                any(k in q for k in ["how many years", "salary", "ctc", "months", "experience"])):
                                is_numeric = True
                                break
                except Exception:
                    pass

                # Get answer (with options and is_numeric context for LLM)
                answer = find_answer(q_text, options=options if options else None, is_numeric=is_numeric)

                # Handle custom dropdowns (LinkedIn-specific artdeco dropdown buttons)
                custom_dropdown_selected = False
                try:
                    dropdown_triggers = q_block.find_elements(
                        By.CSS_SELECTOR,
                        "button[aria-haspopup='listbox'], "
                        "button.artdeco-dropdown__trigger, "
                        "button[aria-expanded]"
                    )
                    for trigger in dropdown_triggers:
                        btn_text = trigger.text.lower()
                        if any(w in btn_text for w in ["continue", "next", "review", "submit", "cancel", "dismiss"]):
                            continue
                        
                        # Click to open dropdown trigger
                        if safe_click(driver, trigger):
                            sleep(0.5, 1.0)
                            suggestions = driver.find_elements(
                                By.CSS_SELECTOR,
                                "div[role='option'], li[role='option'], .artdeco-dropdown__item, .basic-typeahead__selectable"
                            )
                            if suggestions:
                                suggestion_texts = [s.text.strip() for s in suggestions if s.text.strip()]
                                if suggestion_texts:
                                    best = best_match_option(answer, suggestion_texts)
                                    clicked_opt = False
                                    for s in suggestions:
                                        if s.text.strip() == best:
                                            safe_click(driver, s)
                                            clicked_opt = True
                                            log.info(f"📥 Custom Dropdown: '{q_text[:40]}' → selected '{best}'")
                                            custom_dropdown_selected = True
                                            break
                                    if not clicked_opt:
                                        safe_click(driver, suggestions[0])
                                        log.info(f"📥 Custom Dropdown (fallback): selected first option '{suggestion_texts[0]}'")
                                        custom_dropdown_selected = True
                                    sleep(0.3)
                except Exception as e:
                    log.debug(f"Custom dropdown fill error: {e}")

                # Handle radio/checkbox groups specially (smart matching)
                has_radios = q_block.find_elements(
                    By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']"
                )
                if has_radios:
                    fill_radio_group(driver, q_block, answer)

                # Fill all other fields in this question block
                fields = q_block.find_elements(
                    By.CSS_SELECTOR,
                    "input, select, textarea"
                )
                for field in fields:
                    f_type = (field.get_attribute("type") or "").lower()
                    # Skip radio/checkbox (already handled above) and file inputs
                    if f_type in ["radio", "checkbox", "file"]:
                        continue
                    # Skip select/inputs that we already filled via custom dropdown to avoid conflicts
                    if custom_dropdown_selected and field.tag_name.lower() == "select":
                        continue
                    fill_field(driver, field, answer, q_text=q_text)
                    sleep(0.2, 0.5)

            except StaleElementReferenceException:
                pass

        # ─── PASS 2: Ultra-Generic Pass (handles custom/nested ATS forms like PyjamaHR) ───
        # Confined strictly to the active modal/form container
        all_fields = container.find_elements(
            By.CSS_SELECTOR,
            "input, select, textarea, button[aria-haspopup='listbox'], button.artdeco-dropdown__trigger, button[aria-expanded]"
        )

        for field in all_fields:
            try:
                f_type = (field.get_attribute("type") or "").lower()
                tag = field.tag_name.lower()

                # Skip submits, cancels, files, and hidden inputs
                if f_type in ["hidden", "submit", "button", "file"] and tag != "button":
                    continue

                if tag == "button":
                    btn_text = field.text.lower()
                    if any(w in btn_text for w in ["continue", "next", "review", "submit", "cancel", "dismiss"]):
                        continue

                # Find the question/label text for this specific field
                q_text = ""

                # 1. Try finding associated label by 'id'/'for'
                f_id = field.get_attribute("id")
                if f_id:
                    try:
                        lbl = container.find_element(By.CSS_SELECTOR, f"label[for='{f_id}']")
                        q_text = lbl.text.strip()
                    except Exception:
                        pass

                # 2. Try looking for ancestor labels or surrounding text (parent)
                if not q_text:
                    try:
                        parent = field.find_element(By.XPATH, "./..")
                        for sel in ["label", "span", "p", ".t-bold", ".fb-dash-form-element__label", "h3", "h4"]:
                            try:
                                lbl = parent.find_element(By.CSS_SELECTOR, sel)
                                if lbl.text.strip():
                                    q_text = lbl.text.strip()
                                    break
                            except Exception:
                                pass
                    except Exception:
                        pass

                # 3. Try grandparent surrounding text
                if not q_text:
                    try:
                        gparent = field.find_element(By.XPATH, "./../..")
                        for sel in ["label", "span", "p", ".t-bold", ".fb-dash-form-element__label", "h3", "h4"]:
                            try:
                                lbl = gparent.find_element(By.CSS_SELECTOR, sel)
                                if lbl.text.strip():
                                    q_text = lbl.text.strip()
                                    break
                            except Exception:
                                pass
                    except Exception:
                        pass

                # 4. Try aria-label or placeholder
                if not q_text:
                    q_text = field.get_attribute("aria-label") or field.get_attribute("placeholder") or ""

                q_text = q_text.strip()
                if not q_text:
                    continue

                # Clean up newlines in label text to make matching consistent
                q_text = " ".join(q_text.split())

                # Determine if numeric context
                is_numeric = False
                if tag in ["input", "textarea"]:
                    inputmode = field.get_attribute("inputmode") or ""
                    field_id = (field.get_attribute("id") or "").lower()
                    q = q_text.lower()
                    if (inputmode == "numeric" or 
                        any(k in field_id for k in ["year", "salary", "ctc", "exp", "experience"]) or 
                        any(k in q for k in ["how many years", "salary", "ctc", "months", "experience"])):
                        is_numeric = True

                # Skip if already filled
                if tag in ["input", "textarea"]:
                    current_val = field.get_attribute("value") or ""
                    if current_val.strip() and f_type not in ["radio", "checkbox"]:
                        continue
                elif tag == "select":
                    sel = Select(field)
                    try:
                        if sel.first_selected_option.text.strip() not in ["Select an option", "Select", "-- Select --", "Choose...", ""]:
                            continue
                    except Exception:
                        pass

                # Extract dropdown options for context
                options = []
                if tag == "select":
                    try:
                        sel = Select(field)
                        options = [opt.text.strip() for opt in sel.options
                                   if opt.text.strip() and opt.text.strip() not in [
                                       "Select an option", "Select", "-- Select --", "Choose...", ""
                                   ]]
                    except Exception:
                        pass
                elif f_type in ["radio", "checkbox"]:
                    # Radio groups are filled at parent level
                    try:
                        parent = field.find_element(By.XPATH, "./..")
                        radios = parent.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
                        if len(radios) > 1:
                            # Verify if any radio in this group is already selected
                            any_selected = any(r.is_selected() for r in radios)
                            if any_selected:
                                continue
                            answer = find_answer(q_text, is_numeric=is_numeric)
                            fill_radio_group(driver, parent, answer)
                            continue
                    except Exception:
                        pass
                    # If single checkbox, we can click it if answer is Yes
                    answer = find_answer(q_text, is_numeric=is_numeric)
                    if "yes" in str(answer).lower() and not field.is_selected():
                        safe_click(driver, field)
                    continue

                # Get answer for general fields
                answer = find_answer(q_text, options=options if options else None, is_numeric=is_numeric)

                # Fill the field
                if tag == "button":
                    # Click to open dropdown trigger
                    if safe_click(driver, field):
                        sleep(0.5, 1.0)
                        suggestions = driver.find_elements(
                            By.CSS_SELECTOR,
                            "div[role='option'], li[role='option'], .artdeco-dropdown__item, .basic-typeahead__selectable"
                        )
                        if suggestions:
                            suggestion_texts = [s.text.strip() for s in suggestions if s.text.strip()]
                            if suggestion_texts:
                                best = best_match_option(answer, suggestion_texts)
                                clicked_opt = False
                                for s in suggestions:
                                    if s.text.strip() == best:
                                        safe_click(driver, s)
                                        clicked_opt = True
                                        log.info(f"📥 Generic Custom Dropdown: '{q_text[:40]}' → selected '{best}'")
                                        break
                                if not clicked_opt:
                                    safe_click(driver, suggestions[0])
                                sleep(0.3)
                else:
                    fill_field(driver, field, answer, q_text=q_text)
                    sleep(0.2)

            except Exception as e:
                log.debug(f"Generic field fill error: {e}")

    except Exception as e:
        log.debug(f"Form fill error: {e}")


# ─── Wait for Loaders ─────────────────────────────────────────
def wait_for_loader(driver, timeout=5):
    """Wait for LinkedIn loading spinners to disappear."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, ".jobs-loader, .artdeco-loader"))
        )
    except TimeoutException:
        pass


# ─── Dismiss any open modal/overlay ───────────────────────────
def dismiss_modal(driver):
    """Force-close any lingering Easy Apply modal and discard confirmation."""
    try:
        close_btn = driver.find_element(
            By.CSS_SELECTOR,
            "button[aria-label='Dismiss'], button[aria-label='Cancel'], button[data-test-modal-close-btn]"
        )
        driver.execute_script("arguments[0].click();", close_btn)
        sleep(1, 1.5)
    except NoSuchElementException:
        return
    except Exception:
        return

    # Handle the "Discard application?" confirmation dialog
    try:
        discard_btn = driver.find_element(
            By.CSS_SELECTOR,
            "button[data-control-name='discard_application_confirm_btn'], "
            "button[data-test-dialog-primary-btn]"
        )
        driver.execute_script("arguments[0].click();", discard_btn)
        sleep(1)
    except Exception:
        pass


# ─── Handle Easy Apply Modal ──────────────────────────────────
def handle_easy_apply_modal(driver, job_title):
    """
    Steps through the Easy Apply modal, filling fields using LLM.
    Returns True if successfully applied, False otherwise.
    """
    wait = WebDriverWait(driver, 10)
    max_steps = 15  # Increased for complex multi-page forms
    step = 0

    while step < max_steps:
        step += 1
        sleep(1.5, 3)
        wait_for_loader(driver)

        # ── Resume Upload Check ────────────────────────────
        try:
            upload = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
            resume_path = Path(config.PERSONAL["resume_path"]).resolve()
            if resume_path.exists():
                upload.send_keys(str(resume_path))
                sleep(2)
                log.info("📄 Resume uploaded")
            else:
                log.warning(f"Resume file not found: {resume_path}")
        except NoSuchElementException:
            pass

        # ── Fill All Visible Fields (with LLM + option extraction) ──
        fill_form_fields(driver)

        # ── Wait for loaders before clicking buttons ───────
        wait_for_loader(driver)

        # ── Submit application button ──────────────────────
        try:
            submit_btn = driver.find_element(
                By.CSS_SELECTOR,
                "button[aria-label='Submit application']"
            )
            driver.execute_script("arguments[0].click();", submit_btn)
            sleep(2, 3)
            log.info(f"✅ APPLIED: {job_title}")
            return True
        except NoSuchElementException:
            pass

        # ── Next / Review button (with validation retry) ───
        try:
            next_btn = driver.find_element(
                By.CSS_SELECTOR,
                "button[aria-label='Continue to next step'], "
                "button[aria-label='Review your application']"
            )
            driver.execute_script("arguments[0].click();", next_btn)
            sleep(1.5, 2.5)

            # Check for validation errors after clicking Next
            validation_errors = driver.find_elements(
                By.CSS_SELECTOR,
                ".artdeco-inline-feedback--error .artdeco-inline-feedback__message, "
                ".fb-dash-form-element__error-field, "
                "div[data-test-form-element-error-message]"
            )
            # Filter to only real error messages (short text, not dropdown content)
            error_texts = []
            for e in validation_errors:
                txt = e.text.strip()
                if txt and len(txt) < 200 and '\n' not in txt:
                    error_texts.append(txt)
            if error_texts:
                log.warning(f"⚠️ Validation errors: {error_texts}. Retrying fill...")
                # Re-fill the form fields — the retry will fix unfilled required fields
                fill_form_fields(driver)
                sleep(0.5, 1)
                # Try clicking Next again
                try:
                    next_btn = driver.find_element(
                        By.CSS_SELECTOR,
                        "button[aria-label='Continue to next step'], "
                        "button[aria-label='Review your application']"
                    )
                    driver.execute_script("arguments[0].click();", next_btn)
                    sleep(1.5, 2.5)
                except NoSuchElementException:
                    pass
            continue
        except NoSuchElementException:
            pass

        # Generic Review/Submit button
        try:
            review_btn = driver.find_element(
                By.XPATH,
                "//button[contains(., 'Review') or contains(., 'Submit')]"
            )
            driver.execute_script("arguments[0].click();", review_btn)
            sleep(1.5, 2.5)
            continue
        except NoSuchElementException:
            pass

        # ── Dismiss/Close (no matching button found) ───────
        dismiss_modal(driver)
        log.warning(f"⚠️  Modal closed without applying: {job_title}")
        return False

    # Max steps reached — force close modal
    dismiss_modal(driver)
    log.warning(f"❌ Max steps reached: {job_title}")
    return False


# ─── Apply to a Single Job ────────────────────────────────────
def apply_to_job(driver, job_card, applied_titles):
    try:
        # Click the job card — handle intercepted clicks
        try:
            job_card.click()
        except Exception:
            dismiss_modal(driver)
            try:
                driver.execute_script("arguments[0].click();", job_card)
            except Exception:
                log.debug("Could not click job card even with JS")
                return False
        sleep(2, 3)

        wait = WebDriverWait(driver, 10)

        # Get job title
        try:
            title_el = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".job-details-jobs-unified-top-card__job-title, h1")
            ))
            job_title = title_el.text.strip()
        except Exception:
            job_title = "Unknown Role"

        # Get company name
        try:
            company_el = driver.find_element(
                By.CSS_SELECTOR,
                ".job-details-jobs-unified-top-card__company-name, "
                ".jobs-unified-top-card__company-name"
            )
            company = company_el.text.strip()
        except Exception:
            company = "Unknown Company"

        full_title = f"{job_title} @ {company}"

        # Duplicate check
        if full_title in applied_titles:
            log.info(f"⏭️  Already applied: {full_title}")
            return False

        log.info(f"📋 Job: {full_title}")

        # Find Easy Apply button
        try:
            apply_btn = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR,
                 "button.jobs-apply-button[aria-label*='Easy Apply'], "
                 ".jobs-s-apply button")
            ))

            if "Easy Apply" not in apply_btn.text:
                log.info(f"⏭️  Not Easy Apply: {full_title}")
                return False

            driver.execute_script("arguments[0].click();", apply_btn)
            sleep(2, 3)

        except TimeoutException:
            log.info(f"⏭️  Apply button not found: {full_title}")
            return False

        # Handle the modal
        success = handle_easy_apply_modal(driver, full_title)
        if success:
            applied_titles.add(full_title)
            return True

    except StaleElementReferenceException:
        log.debug("Stale element in apply_to_job — skipping")
    except Exception as e:
        log.error(f"Error on job card: {e}")

    return False


# ─── Save Applied Log ─────────────────────────────────────────
def save_log(applied_titles):
    log_path = f"applied_jobs_{datetime.now().strftime('%Y%m%d')}.txt"
    # Specify utf-8 encoding to prevent UnicodeEncodeError on Windows due to emojis/symbols
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"Applied Jobs — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write("=" * 60 + "\n")
        for title in sorted(applied_titles):
            f.write(f"✅ {title}\n")
    log.info(f"📊 Log saved: {log_path} ({len(applied_titles)} applications)")


# ─── Main Bot Loop ────────────────────────────────────────────
def run_linkedin_bot():
    log.info("=" * 60)
    log.info("   LinkedIn Job Apply Bot — Rayees Yousuf")
    log.info("=" * 60)

    driver = get_driver()
    applied_titles = set()
    total_applied = 0
    max_apps = config.SEARCH["max_applications"]

    try:
        # Login
        if not linkedin_login(driver):
            log.error("Login failed. Ruk ke manually login karo phir restart karo.")
            input("Press Enter after manual login...")

        # Har keyword ke liye jobs search karo
        for keyword in config.SEARCH["keywords"]:
            search_jobs(driver, keyword)

            # Continuous Pagination
            page = 1
            while True:
                log.info(f"📄 Page {page} — Keyword: '{keyword}'")

                # Scroll to load all cards with anti-detection human scroll
                try:
                    container_el = driver.find_element(By.CSS_SELECTOR, ".jobs-search-results-list")
                    for _ in range(5):
                        human_scroll(driver, container_el)
                except Exception:
                    # Fallback in case container selector is not active
                    for _ in range(5):
                        driver.execute_script(
                            "document.querySelector('.jobs-search-results-list')?.scrollBy(0, 500)"
                        )
                        sleep(0.5, 1.0)

                cards = get_job_cards(driver)
                log.info(f"   {len(cards)} jobs mile")

                if len(cards) == 0:
                    log.info("No more jobs on this page. Moving to next keyword.")
                    break

                for i in range(len(cards)):
                    try:
                        # Re-fetch cards each iteration to avoid stale elements
                        fresh_cards = get_job_cards(driver)
                        if i >= len(fresh_cards):
                            break
                        success = apply_to_job(driver, fresh_cards[i], applied_titles)
                        if success:
                            total_applied += 1
                            log.info(f"   [Total Applied: {total_applied}]")
                        if total_applied >= max_apps:
                            log.info(f"🎯 Reached max applications ({max_apps})!")
                            return
                        sleep(2, 5)
                    except StaleElementReferenceException:
                        log.debug(f"Card {i} went stale — skipping")
                        continue
                    except Exception as e:
                        log.error(f"Card {i} error: {e}")
                        continue

                # Next page
                try:
                    next_btn = driver.find_element(
                        By.CSS_SELECTOR,
                        "button[aria-label='View next page']"
                    )
                    next_btn.click()
                    sleep(3, 5)
                    page += 1
                except Exception:
                    log.info("Reached end of pagination for this keyword.")
                    break

            # Keyword ke beech delay
            sleep(5, 10)

    except KeyboardInterrupt:
        log.info("⛔ Bot manually stopped.")

    finally:
        save_log(applied_titles)
        log.info(f"🏁 Session complete — Total applied: {total_applied}")
        driver.quit()


if __name__ == "__main__":
    run_linkedin_bot()
