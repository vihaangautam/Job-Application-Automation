import os
import sys
import logging
from concurrent.futures import ThreadPoolExecutor

# Reconfigure stdout/stderr to UTF-8 on Windows to prevent UnicodeEncodeError when printing emojis
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config

# Logging setup for orchestrator
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [MAIN] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

def print_banner():
    print("==============================================================")
    print("      MULTI-PLATFORM JOB APPLY BOT — Rayees Yousuf")
    print("==============================================================")
    print("1. LinkedIn Bot")
    print("2. Indeed Bot")
    print("3. Naukri Bot")
    print("4. Glassdoor Bot")
    print("5. Foundit (Monster) Bot")
    print("6. Run ALL Sequentially")
    print("==============================================================")

def run_linkedin():
    try:
        from linkedin_bot import run_linkedin_bot
        log.info("Starting LinkedIn Bot...")
        run_linkedin_bot()
    except ImportError as e:
        log.error(f"Failed to load LinkedIn Bot: {e}")

def run_indeed():
    try:
        from indeed_bot import run_indeed_bot
        log.info("Starting Indeed Bot...")
        run_indeed_bot()
    except ImportError as e:
        log.error(f"Failed to load Indeed Bot: {e}. Has it been implemented?")

def run_naukri():
    try:
        from naukri_bot import run_naukri_bot
        log.info("Starting Naukri Bot...")
        run_naukri_bot()
    except ImportError as e:
        log.error(f"Failed to load Naukri Bot: {e}. Has it been implemented?")

def run_glassdoor():
    try:
        from glassdoor_bot import run_glassdoor_bot
        log.info("Starting Glassdoor Bot...")
        run_glassdoor_bot()
    except ImportError as e:
        log.error(f"Failed to load Glassdoor Bot: {e}. Has it been implemented?")

def run_foundit():
    try:
        from foundit_bot import run_foundit_bot
        log.info("Starting Foundit Bot...")
        run_foundit_bot()
    except ImportError as e:
        log.error(f"Failed to load Foundit Bot: {e}. Has it been implemented?")

def pre_login_all():
    log.info("Opening all platforms for a one-time pre-login...")
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.chrome.options import Options
    
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    user_data_dir = os.path.join(os.getcwd(), "chrome_profile")
    options.add_argument(f"user-data-dir={user_data_dir}")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    urls = [
        "https://www.linkedin.com/login",
        "https://secure.indeed.com/auth",
        "https://login.naukri.com/nLogin/Login.php",
        "https://www.glassdoor.co.in/profile/login_input.htm",
        "https://www.foundit.in/rio/login"
    ]
    
    driver.get(urls[0])
    for url in urls[1:]:
        driver.execute_script(f"window.open('{url}', '_blank');")
        
    print("\n" + "="*60)
    print("🤖 [GYM MODE: PRE-LOGIN FOR ALL PLATFORMS] 🤖")
    print("I have opened tabs for all 5 platforms.")
    print("Please go to the Chrome window and log into ALL of them.")
    print("Once you are fully logged into all platforms, press ENTER below.")
    input("👉 Press ENTER here when ready to go to the gym... ")
    print("="*60 + "\n")
    
    driver.quit()

def run_all_sequentially():
    log.info("Starting ALL platforms sequentially to avoid browser conflicts...")
    pre_login_all()
    os.environ["SKIP_LOGIN_PROMPT"] = "1"
    
    bots = [run_linkedin, run_indeed, run_naukri, run_glassdoor, run_foundit]
    
    for bot in bots:
        bot()
        log.info("-" * 60)
        
    os.environ.pop("SKIP_LOGIN_PROMPT", None)

def main():
    print_banner()
    choice = input("Enter your choice (1-6): ").strip()
    
    if choice == "1":
        run_linkedin()
    elif choice == "2":
        run_indeed()
    elif choice == "3":
        run_naukri()
    elif choice == "4":
        run_glassdoor()
    elif choice == "5":
        run_foundit()
    elif choice == "6":
        run_all_sequentially()
    else:
        print("Invalid choice. Exiting.")

if __name__ == "__main__":
    main()
