import os
import time
import random
import argparse
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Load environment variables
load_dotenv()

# Setup Timezone
BKK_TZ = pytz.timezone('Asia/Bangkok')

# Configuration
URL = "https://timesheet.ntplc.co.th/"
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timesheet_logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Fixed Thai Public Holidays (Month, Day)
FIXED_HOLIDAYS = [
    (1, 1),   # วันขึ้นปีใหม่
    (4, 6),   # วันจักรี
    (4, 13),  # วันสงกรานต์
    (4, 14),  # วันสงกรานต์
    (4, 15),  # วันสงกรานต์
    (5, 1),   # วันแรงงาน
    (5, 5),   # วันฉัตรมงคล
    (7, 28),  # วันเฉลิมพระชนมพรรษา ร.10
    (8, 12),  # วันแม่แห่งชาติ
    (10, 23), # วันปิยมหาราช
    (12, 5),  # วันพ่อแห่งชาติ
    (12, 10), # วันรัฐธรรมนูญ
    (12, 31)  # วันสิ้นปี
]

# Variable Holidays for 2025-2026 (Year, Month, Day)
VARIABLE_HOLIDAYS = [
    (2026, 1, 31),
    (2026, 3, 3),
    (2026, 6, 3),
    (2026, 6, 1),
    (2026, 5, 31),
    (2026, 7, 28),
    (2026, 8, 1)
]

def is_holiday(dt: datetime) -> bool:
    if dt.weekday() >= 5: # 5=Saturday, 6=Sunday
        print(f"Skipping: Today is Weekend ({dt.strftime('%A')}).")
        return True
    
    # Check fixed
    if (dt.month, dt.day) in FIXED_HOLIDAYS:
        print(f"Skipping: Today is a fixed public holiday.")
        return True
        
    # Check variable
    if (dt.year, dt.month, dt.day) in VARIABLE_HOLIDAYS:
        print(f"Skipping: Today is a variable public holiday.")
        return True
        
    return False

def get_random_target_time(mode: str, now: datetime) -> datetime:
    """Returns a randomized datetime object for the target checkin/checkout time."""
    if mode == "CHECKIN":
        # 07:45 - 08:15
        hour = random.choice([7, 8])
        if hour == 7:
            minute = random.randint(45, 59)
        else:
            minute = random.randint(0, 15)
        second = random.randint(0, 59)
    else: # CHECKOUT
        # 17:00 - 17:30
        hour = 17
        minute = random.randint(0, 30)
        second = random.randint(0, 59)
        
    return now.replace(hour=hour, minute=minute, second=second, microsecond=0)

def take_screenshot(page, name: str):
    timestamp = datetime.now(BKK_TZ).strftime("%Y%m%d_%H%M%S")
    filename = f"{name}_{timestamp}.png"
    filepath = os.path.join(LOG_DIR, filename)
    page.screenshot(path=filepath)
    print(f"📸 Saved screenshot: {filename}")

def run_automation(mode: str, test_mode: bool):
    username = os.getenv("TIMESHEET_USERNAME")
    password = os.getenv("TIMESHEET_PASSWORD")
    
    if not username or not password:
        print("❌ Error: TIMESHEET_USERNAME or TIMESHEET_PASSWORD not found in environment.")
        return

    print(f"🚀 Starting {mode} automation (Test Mode: {test_mode})")
    
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=not test_mode)
        context = browser.new_context(
            locale='th-TH',
            timezone_id='Asia/Bangkok',
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()

        try:
            # 1. Login
            print("Navigating to login page...")
            page.goto(URL, timeout=30000)
            take_screenshot(page, "before_login")
            
            print("Entering credentials...")
            # Use placeholders or input types based on prompt
            # Try specific placeholders first, fallback to generic types if needed
            username_input = page.locator('input[placeholder*="Username"]').first
            if not username_input.is_visible():
                username_input = page.locator('input[type="text"]').first
                
            password_input = page.locator('input[placeholder*="Intranet"]').first
            if not password_input.is_visible():
                password_input = page.locator('input[type="password"]').first
                
            username_input.fill(username)
            password_input.fill(password)
            
            # Click Login button
            page.locator('button:has-text("Login")').click()
            
            # Wait for either dashboard or T&C modal
            try:
                page.wait_for_load_state('networkidle', timeout=10000)
            except PlaywrightTimeoutError:
                pass
                
            # Handle T&C Modal
            tc_button = page.locator('button:has-text("ยอมรับเงื่อนไข")')
            if tc_button.is_visible():
                print("T&C Modal detected. Accepting terms...")
                # Try to scroll modal down
                page.mouse.wheel(0, 1000)
                time.sleep(2)
                tc_button.click()
                time.sleep(5)
                
            # 2. Dashboard Check
            take_screenshot(page, "dashboard")
            
            # Check if attendance already exists
            # We assume if the green submit button is NOT visible, or if there is specific text, it might be recorded.
            submit_btn = page.locator('button:has-text("ลงเวลาเข้างาน")').first
            if not submit_btn.is_visible():
                print("Attendance already exists for today. (Submit button not found)")
                take_screenshot(page, "already_recorded")
                return
                
            # 3. Open Modal
            print("Opening attendance modal...")
            submit_btn.click()
            time.sleep(3)
            take_screenshot(page, "modal_opened")
            
            # 4. Fill Data
            print("Filling attendance data...")
            # Click NT Academy tag if available
            academy_tag = page.locator('button:has-text("NT Academy")')
            if academy_tag.is_visible():
                academy_tag.click()
            else:
                # Try to find input and fill
                loc_input = page.locator('input').nth(1) # educated guess for location input
                loc_input.fill("NT Academy")
                
            # Select WFH
            dropdown = page.locator('select')
            if dropdown.is_visible():
                # Attempt to select WFH or fallback to first option
                try:
                    dropdown.select_option(label="WFH")
                except:
                    pass
            
            # 5. Verify before submit
            take_screenshot(page, "before_submit")
            
            if test_mode:
                print("🛑 Test mode active. Skipping actual submit.")
                return
                
            # 6. Submit
            print("Submitting attendance...")
            # Click the submit inside modal (usually the green one)
            modal_submit = page.locator('.modal-content button.btn-success, .modal-dialog button.btn-success').first
            if modal_submit.is_visible():
                modal_submit.click()
            else:
                page.locator('button:has-text("ลงเวลาเข้างาน")').nth(1).click() # 2nd button is usually the modal one
                
            time.sleep(5)
            take_screenshot(page, "after_submit")
            print(f"✅ ลงเวลาสำเร็จ ประเภท: {mode}")
            
        except Exception as e:
            print(f"❌ Error during automation: {str(e)}")
            take_screenshot(page, "error_state")
            raise
        finally:
            browser.close()

def main():
    parser = argparse.ArgumentParser(description="Automated Timesheet Submission")
    parser.add_argument("--mode", type=str, choices=["CHECKIN", "CHECKOUT"], help="Mode of operation")
    parser.add_argument("--test", action="store_true", help="Run in dry-run mode (no submit, shows browser)")
    args = parser.parse_args()

    mode = args.mode or os.getenv("MODE")
    if not mode or mode not in ["CHECKIN", "CHECKOUT"]:
        print("❌ Error: MODE must be set to CHECKIN or CHECKOUT (via argument or .env).")
        return

    now = datetime.now(BKK_TZ)
    print(f"🕒 Current time: {now.strftime('%Y-%m-%d %H:%M:%S')} ({now.strftime('%A')})")
    
    if is_holiday(now):
        return

    target_time = get_random_target_time(mode, now)
    print(f"🎯 Target {mode} time chosen: {target_time.strftime('%H:%M:%S')}")
    
    if now < target_time:
        wait_seconds = (target_time - now).total_seconds()
        print(f"⏳ Waiting {int(wait_seconds)} seconds until target time...")
        time.sleep(wait_seconds)
    else:
        print("⚠️ Current time is past target time. Executing immediately.")

    run_automation(mode, args.test)

if __name__ == "__main__":
    main()
