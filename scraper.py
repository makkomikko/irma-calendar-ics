import os
import re
import json
import datetime
import shutil
import holidays
from playwright.sync_api import sync_playwright
from icalendar import Calendar, Event

URL = "https://irma.suunnistusliitto.fi/public/competitioncalendar/list?year=upcoming&area=all&competition=ALL&previous=undefined&tab=competition"
BASE_URL = "https://irma.suunnistusliitto.fi"
OUTPUT_DIR = "ics_files"

def parse_fi_date(date_str):
    nums = [int(x) for x in re.findall(r'\d+', date_str)]
    try:
        if len(nums) == 3:
            return datetime.date(nums[2], nums[1], nums[0]), datetime.date(nums[2], nums[1], nums[0])
        elif len(nums) == 4:
            return datetime.date(nums[3], nums[2], nums[0]), datetime.date(nums[3], nums[2], nums[1])
        elif len(nums) == 5:
            return datetime.date(nums[4], nums[1], nums[0]), datetime.date(nums[4], nums[3], nums[2])
    except: return None, None
    return None, None

def clean_filename(name):
    cleaned = re.sub(r'[^\w\s-]', '', name).strip()
    return cleaned.replace(' ', '_') + '.ics'

def extract_categories(name):
    cat = []
    nl = name.lower()
    if "keskimatka" in nl: cat.append("Keskimatka")
    if "pitkä" in nl and "erikoispitkä" not in nl: cat.append("Pitkä")
    if "yö" in nl: cat.append("Yö")
    if "erikoispitkä" in nl: cat.append("Erikoispitkä")
    if "viesti" in nl and "viestiliiga" not in nl: cat.append("Viesti")
    if "viestiliiga" in nl: cat.append("Viestiliiga")
    if "sprintti" in nl: cat.append("Sprintti")
    if "sm-" in nl: cat.append("SM")
    if "am-" in nl or "fsom" in nl: cat.append("AM/FSOM")
    return cat

def main():
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    events_json = []
    today = datetime.date.today()
    
    # Load Finnish holidays for the current and next year
    fi_holidays = holidays.Finland(years=[today.year, today.year + 1])

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Loading main calendar...")
        page.goto(URL, wait_until="networkidle")
        page.wait_for_selector("table tr td", timeout=15000)
        
        rows = page.query_selector_all("table tr")
        scraped_events = []

        for row in rows:
            cols = row.query_selector_all("td")
            if len(cols) >= 4:
                date_text = cols[0].inner_text().strip()
                name = cols[1].inner_text().strip()
                organizer = cols[2].inner_text().strip()
                discipline = cols[3].inner_text().strip()

                if not any(char.isdigit() for char in date_text) or "S" not in discipline.split():
                    continue

                start_date, end_date = parse_fi_date(date_text)
                if not start_date or end_date < today: 
                    continue
                
                a_tag = cols[1].query_selector("a")
                link = f"{BASE_URL}{a_tag.get_attribute('href')}" if a_tag and a_tag.get_attribute("href").startswith("/") else (a_tag.get_attribute("href") if a_tag else "")

                scraped_events.append({
                    "name": name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "organizer": organizer,
                    "link": link
                })

        print(f"Found {len(scraped_events)} upcoming events. Fetching details...")
        
        for idx, evt in enumerate(scraped_events, 1):
            deadline_str, maps_url = "", ""
            
            if evt["link"]:
                print(f"[{idx}/{len(scraped_events)}] Checking {evt['name']}...")
                try:
                    page.goto(evt["link"], wait_until="networkidle", timeout=15000)
                    tier1_row = page.locator("tr", has_text="Ilmoittautumisporras #1")
                    if tier1_row.count() > 0:
                        match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})', tier1_row.first.inner_text())
                        if match: deadline_str = match.group(1)
                    
                    html_content = page.content()
                    coord_match = re.search(r'[([]\s*(59\.\d+|6\d\.\d+|70\.\d+)\s*,\s*(19\.\d+|2\d\.\d+|3[0-2]\.\d+)\s*[)\]]', html_content)
                    if coord_match:
                        lat, lng = coord_match.groups()
                        maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
                except Exception:
                    pass

            # Holiday Detection
            is_holiday = False
            holiday_name = ""
            if evt["start_date"] in fi_holidays:
                is_holiday, holiday_name = True, fi_holidays.get(evt["start_date"])
            elif evt["end_date"] in fi_holidays:
                is_holiday, holiday_name = True, fi_holidays.get(evt["end_date"])

            # Categories Extraction
            event_categories = extract_categories(evt["name"])

            # Build ICS
            cal = Calendar()
            cal.add('prodid', '-//IRMA Scraper//')
            cal.add('version', '2.0')
            event = Event()
            event.add('summary', evt["name"])
            event.add('dtstart', evt["start_date"])
            event.add('dtend', evt["end_date"] + datetime.timedelta(days=1))
            
            desc = f"Organizer: {evt['organizer']}"
            if event_categories: desc += f"\nCategories: {', '.join(event_categories)}"
            if is_holiday: desc += f"\nHoliday: {holiday_name}"
            if deadline_str: desc += f"\nSign-up Deadline: {deadline_str}"
            if evt["link"]: desc += f"\nIRMA Link: {evt['link']}"
            if maps_url: desc += f"\nGoogle Maps: {maps_url}"
                
            event.add('description', desc)
            event.add('location', maps_url if maps_url else evt['organizer'])
            event.add('dtstamp', datetime.datetime.now())
            if evt["link"]: event.add('url', evt["link"])
            
            # Optionally add native categories to ICS
            if event_categories: event.add('categories', event_categories)
            cal.add_component(event)

            filename = clean_filename(f"{evt['start_date'].strftime('%Y%m%d')}_{evt['name']}")
            with open(os.path.join(OUTPUT_DIR, filename), 'wb') as f:
                f.write(cal.to_ical())

            events_json.append({
                "date": evt["start_date"].strftime('%Y-%m-%d'),
                "name": evt["name"],
                "location": evt["organizer"],
                "filename": filename,
                "link": evt["link"],
                "deadline": deadline_str,
                "cancelled": "peruttu" in evt["name"].lower(),
                "maps_url": maps_url,
                "categories": event_categories,
                "is_holiday": is_holiday,
                "holiday_name": holiday_name
            })
            
        browser.close()

    with open(os.path.join(OUTPUT_DIR, 'events.json'), 'w', encoding='utf-8') as f:
        json.dump(events_json, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
