import os
import re
import json
import datetime
from playwright.sync_api import sync_playwright
from icalendar import Calendar, Event

URL = "https://irma.suunnistusliitto.fi/public/competitioncalendar/list?year=upcoming&area=all&competition=ALL&previous=undefined&tab=competition"
OUTPUT_DIR = "ics_files"

def parse_fi_date(date_str):
    """Parses Finnish dates like 15.5.2026 or 15.-16.5.2026"""
    nums = [int(x) for x in re.findall(r'\d+', date_str)]
    try:
        if len(nums) == 3: # Single day
            d = datetime.date(nums[2], nums[1], nums[0])
            return d, d
        elif len(nums) == 4: # Range same month
            return datetime.date(nums[3], nums[2], nums[0]), datetime.date(nums[3], nums[2], nums[1])
        elif len(nums) == 5: # Range diff month
            return datetime.date(nums[4], nums[1], nums[0]), datetime.date(nums[4], nums[3], nums[2])
    except: return None, None
    return None, None

def clean_filename(name):
    cleaned = re.sub(r'[^\w\s-]', '', name).strip()
    return cleaned.replace(' ', '_') + '.ics'

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    events_json = []

    with sync_playwright() as p:
        # Launch browser to handle dynamic JS loading
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("Navigating to IRMA...")
        page.goto(URL, wait_until="networkidle")
        
        # Wait for the table rows to actually appear
        page.wait_for_selector("table tr td", timeout=15000)
        
        rows = page.query_selector_all("table tr")
        print(f"Analyzing {len(rows)} table rows...")

        for row in rows:
            cols = row.query_selector_all("td")
            if len(cols) >= 4:
                date_text = cols[0].inner_text().strip()
                name = cols[1].inner_text().strip()
                organizer = cols[2].inner_text().strip()
                discipline = cols[3].inner_text().strip()

                # Filter: Must be Foot-O ("S") and have a date
                if not any(char.isdigit() for char in date_text) or "S" not in discipline.split():
                    continue

                start_date, end_date = parse_fi_date(date_text)
                if not start_date: continue

                # Generate ICS content
                cal = Calendar()
                cal.add('prodid', '-//IRMA Orienteering Scraper//')
                cal.add('version', '2.0')
                event = Event()
                event.add('summary', name)
                event.add('dtstart', start_date)
                event.add('dtend', end_date + datetime.timedelta(days=1))
                event.add('location', organizer)
                event.add('dtstamp', datetime.datetime.now())
                cal.add_component(event)

                filename = clean_filename(f"{start_date.strftime('%Y%m%d')}_{name}")
                with open(os.path.join(OUTPUT_DIR, filename), 'wb') as f:
                    f.write(cal.to_ical())

                events_json.append({
                    "date": start_date.strftime('%Y-%m-%d'),
                    "name": name,
                    "location": organizer,
                    "filename": filename
                })
        browser.close()

    # Save the master list for the website
    with open(os.path.join(OUTPUT_DIR, 'events.json'), 'w', encoding='utf-8') as f:
        json.dump(events_json, f, ensure_ascii=False, indent=2)
    
    print(f"Successfully processed {len(events_json)} events.")

if __name__ == "__main__":
    main()
