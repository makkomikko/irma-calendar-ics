import os
import re
import json
import datetime
from playwright.sync_api import sync_playwright
from icalendar import Calendar, Event

URL = "https://irma.suunnistusliitto.fi/public/competitioncalendar/list?year=upcoming&area=all&competition=ALL&previous=undefined&tab=competition"
BASE_URL = "https://irma.suunnistusliitto.fi"
OUTPUT_DIR = "ics_files"

def parse_fi_date(date_str):
    nums = [int(x) for x in re.findall(r'\d+', date_str)]
    try:
        if len(nums) == 3:
            d = datetime.date(nums[2], nums[1], nums[0])
            return d, d
        elif len(nums) == 4:
            return datetime.date(nums[3], nums[2], nums[0]), datetime.date(nums[3], nums[2], nums[1])
        elif len(nums) == 5:
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
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Loading main calendar...")
        page.goto(URL, wait_until="networkidle")
        page.wait_for_selector("table tr td", timeout=15000)
        
        rows = page.query_selector_all("table tr")
        scraped_events = []

        # PHASE 1: Collect base data and URLs
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
                if not start_date: continue
                
                # Grab the direct link from the event name column
                a_tag = cols[1].query_selector("a")
                link = ""
                if a_tag:
                    href = a_tag.get_attribute("href")
                    # Make sure it's a full URL
                    link = f"{BASE_URL}{href}" if href.startswith("/") else href

                scraped_events.append({
                    "name": name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "organizer": organizer,
                    "link": link
                })

        print(f"Found {len(scraped_events)} events. Fetching deadlines...")
        
        # PHASE 2: Visit each page for the deadline
        for idx, evt in enumerate(scraped_events, 1):
            deadline_str = ""
            if evt["link"]:
                print(f"[{idx}/{len(scraped_events)}] Checking {evt['name']}...")
                try:
                    # Timeout set to 15s so one broken page doesn't crash the whole script
                    page.goto(evt["link"], wait_until="networkidle", timeout=15000)
                    
                    # Look specifically for the row containing tier 1
                    tier1_row = page.locator("tr", has_text="Ilmoittautumisporras #1")
                    if tier1_row.count() > 0:
                        row_text = tier1_row.first.inner_text()
                        # Extract the date format DD.MM.YYYY
                        match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})', row_text)
                        if match:
                            deadline_str = match.group(1)
                except Exception as e:
                    print(f"  -> Timeout/Error loading details for {evt['name']}")

            # PHASE 3: Build ICS with the new data
            cal = Calendar()
            cal.add('prodid', '-//IRMA Scraper//')
            cal.add('version', '2.0')
            event = Event()
            event.add('summary', evt["name"])
            event.add('dtstart', evt["start_date"])
            event.add('dtend', evt["end_date"] + datetime.timedelta(days=1))
            
            # Format the description nicely
            desc = f"Organizer: {evt['organizer']}"
            if deadline_str:
                desc += f"\nSign-up Deadline (Porras 1): {deadline_str}"
            if evt["link"]:
                desc += f"\nEvent Link: {evt['link']}"
                event.add('url', evt["link"]) # Also adds it as a clickable URL field in the calendar
                
            event.add('description', desc)
            event.add('location', '') 
            event.add('dtstamp', datetime.datetime.now())
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
                "deadline": deadline_str
            })
            
        browser.close()

    # Save final JSON
    with open(os.path.join(OUTPUT_DIR, 'events.json'), 'w', encoding='utf-8') as f:
        json.dump(events_json, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
