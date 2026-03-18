import os
import re
import json
import datetime
import shutil
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
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    events_json = []
    today = datetime.date.today()

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
                link = ""
                if a_tag:
                    href = a_tag.get_attribute("href")
                    link = f"{BASE_URL}{href}" if href.startswith("/") else href

                scraped_events.append({
                    "name": name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "organizer": organizer,
                    "link": link
                })

        print(f"Found {len(scraped_events)} upcoming events. Fetching details...")
        
        for idx, evt in enumerate(scraped_events, 1):
            deadline_str = ""
            maps_url = ""
            
            if evt["link"]:
                print(f"[{idx}/{len(scraped_events)}] Checking {evt['name']}...")
                try:
                    page.goto(evt["link"], wait_until="networkidle", timeout=15000)
                    
                    # 1. FIND DEADLINE
                    tier1_row = page.locator("tr", has_text="Ilmoittautumisporras #1")
                    if tier1_row.count() > 0:
                        row_text = tier1_row.first.inner_text()
                        match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})', row_text)
                        if match: deadline_str = match.group(1)
                    
                    # 2. FIND COORDINATES (HEURISTIC)
                    # Looks for Leaflet arrays [lat, lng] or functions (lat, lng) within Finland's bounds
                    html_content = page.content()
                    coord_match = re.search(r'[([]\s*(59\.\d+|6\d\.\d+|70\.\d+)\s*,\s*(19\.\d+|2\d\.\d+|3[0-2]\.\d+)\s*[)\]]', html_content)
                    if coord_match:
                        lat, lng = coord_match.groups()
                        maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"

                except Exception:
                    print(f"  -> Timeout/Error loading details for {evt['name']}")

            # BUILD ICS
            cal = Calendar()
            cal.add('prodid', '-//IRMA Scraper//')
            cal.add('version', '2.0')
            event = Event()
            event.add('summary', evt["name"])
            event.add('dtstart', evt["start_date"])
            event.add('dtend', evt["end_date"] + datetime.timedelta(days=1))
            
            desc = f"Organizer: {evt['organizer']}"
            if deadline_str:
                desc += f"\nSign-up Deadline: {deadline_str}"
            if evt["link"]:
                desc += f"\nIRMA Link: {evt['link']}"
            if maps_url:
                desc += f"\nGoogle Maps: {maps_url}"
                # If we found coordinates, set the actual ICS location to the Google Maps link!
                event.add('location', maps_url)
            else:
                event.add('location', evt['organizer'])
                
            event.add('description', desc)
            event.add('dtstamp', datetime.datetime.now())
            if evt["link"]: event.add('url', evt["link"])
            
            cal.add_component(event)

            filename = clean_filename(f"{evt['start_date'].strftime('%Y%m%d')}_{evt['name']}")
            with open(os.path.join(OUTPUT_DIR, filename), 'wb') as f:
                f.write(cal.to_ical())

            is_cancelled = "peruttu" in evt["name"].lower()

            events_json.append({
                "date": evt["start_date"].strftime('%Y-%m-%d'),
                "name": evt["name"],
                "location": evt["organizer"],
                "filename": filename,
                "link": evt["link"],
                "deadline": deadline_str,
                "cancelled": is_cancelled,
                "maps_url": maps_url  # Add the new maps link to JSON
            })
            
        browser.close()

    with open(os.path.join(OUTPUT_DIR, 'events.json'), 'w', encoding='utf-8') as f:
        json.dump(events_json, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
