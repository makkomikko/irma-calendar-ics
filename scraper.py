import os
import re
import json
import datetime
import holidays
from playwright.sync_api import sync_playwright
from icalendar import Calendar, Event

URL = "https://irma.suunnistusliitto.fi/public/competitioncalendar/list?year=upcoming&area=all&competition=ALL&previous=undefined&tab=competition"
BASE_URL = "https://irma.suunnistusliitto.fi"
OUTPUT_DIR = "ics_files"

def parse_fi_date(date_str):
    nums = [int(x) for x in re.findall(r'\d+', date_str)]
    try:
        if len(nums) == 3: return datetime.date(nums[2], nums[1], nums[0]), datetime.date(nums[2], nums[1], nums[0])
        elif len(nums) == 4: return datetime.date(nums[3], nums[2], nums[0]), datetime.date(nums[3], nums[2], nums[1])
        elif len(nums) == 5: return datetime.date(nums[4], nums[1], nums[0]), datetime.date(nums[4], nums[3], nums[2])
    except: return None, None
    return None, None

def clean_filename(name):
    return re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_') + '.ics'

def clean_text(text):
    if not text: return ""
    text = text.replace('\u00a0', ' ')
    text = text.replace('\n', ' ').replace('\r', '')
    return re.sub(r'\s+', ' ', text).strip()

def extract_categories(text):
    cat = []
    if not text: return cat
    nl = text.lower()
    if "keskimatka" in nl: cat.append("Keskimatka")
    if "pitkä" in nl and "erikoispitkä" not in nl: cat.append("Pitkä")
    if "yö" in nl: cat.append("Yö")
    if "erikoispitkä" in nl: cat.append("Erikoispitkä")
    
    # FIX: Every Viestiliiga is now also a Viesti
    if "viesti" in nl: cat.append("Viesti")
    if "viestiliiga" in nl: cat.append("Viestiliiga")
    
    if "sprintti" in nl: cat.append("Sprintti")
    if "sm-" in nl: cat.append("SM")
    if "am-" in nl or "fsom" in nl: cat.append("AM/FSOM")
    return cat

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    clubs_data = {}
    clubs_file = os.path.join(OUTPUT_DIR, 'clubs.json')
    if os.path.exists(clubs_file):
        with open(clubs_file, 'r', encoding='utf-8') as f:
            clubs_data = json.load(f)

    # UPGRADED CACHE: Now stores 'matka' to prevent unnecessary page visits
    events_cache = {}
    events_file = os.path.join(OUTPUT_DIR, 'events.json')
    if os.path.exists(events_file):
        try:
            with open(events_file, 'r', encoding='utf-8') as f:
                old_events = json.load(f)
                for e in old_events:
                    if e.get("link"):
                        events_cache[e["link"]] = {
                            "deadline": e.get("deadline", ""),
                            "matka": e.get("matka", "")
                        }
        except Exception: pass

    events_json = []
    today = datetime.date.today()
    fi_holidays = holidays.Finland(years=[today.year, today.year + 1])
    generated_files = set(['events.json', 'clubs.json'])

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle")
        page.wait_for_selector("table tr td", timeout=15000)
        
        rows = page.query_selector_all("table tr")
        scraped_events = []

        for row in rows:
            cols = row.query_selector_all("td")
            if len(cols) >= 4:
                date_text = clean_text(cols[0].inner_text())
                name = clean_text(cols[1].inner_text())
                organizer = clean_text(cols[2].inner_text())
                discipline = clean_text(cols[3].inner_text())

                if not any(char.isdigit() for char in date_text) or "S" not in discipline.split():
                    continue

                start_date, end_date = parse_fi_date(date_text)
                if not start_date or end_date < today: continue
                
                a_tag = cols[1].query_selector("a")
                link = f"{BASE_URL}{a_tag.get_attribute('href')}" if a_tag and a_tag.get_attribute("href").startswith("/") else (a_tag.get_attribute("href") if a_tag else "")

                primary_club = organizer.split(',')[0].split('/')[0].strip()
                area = clean_text(clubs_data.get(primary_club, "Tuntematon Alue"))

                scraped_events.append({
                    "name": name, "start_date": start_date, "end_date": end_date,
                    "organizer": organizer, "link": link, "area": area
                })

        for evt in scraped_events:
            deadline_str = ""
            matka_str = ""
            
            # 1. Primary Category Extraction (from Title)
            event_categories = extract_categories(evt["name"])
            has_distance = any(c in event_categories for c in ["Keskimatka", "Pitkä", "Sprintti", "Yö", "Erikoispitkä", "Viesti"])

            if evt["link"]:
                cache_hit = events_cache.get(evt["link"], {})
                cached_deadline = cache_hit.get("deadline", "")
                cached_matka = cache_hit.get("matka", "")

                # If we have the deadline cached, and we either already have a distance OR we have 'matka' cached, skip page visit
                if cached_deadline and (has_distance or cached_matka):
                    deadline_str = cached_deadline
                    matka_str = cached_matka
                else:
                    try:
                        page.goto(evt["link"], wait_until="networkidle", timeout=15000)
                        page.wait_for_selector("span", timeout=5000) # Wait for Vaadin spans to load
                        
                        # Fetch both Deadline and Matka via JS
                        fetched_data = page.evaluate("""
                            () => {
                                const spans = Array.from(document.querySelectorAll('span'));
                                
                                let deadline = "";
                                const dlLabel = spans.find(s => s.innerText.includes('Ilmoittautumisporras #1'));
                                if (dlLabel && dlLabel.nextElementSibling) {
                                    const match = dlLabel.nextElementSibling.innerText.match(/(\d{1,2}\.\d{1,2}\.\d{4})/);
                                    if (match) deadline = match[1];
                                }
                                
                                let matka = "";
                                const matkaLabel = spans.find(s => s.innerText.trim() === 'Matka' || s.innerText.includes('Matka'));
                                if (matkaLabel && matkaLabel.nextElementSibling) {
                                    matka = matkaLabel.nextElementSibling.innerText.trim();
                                }
                                
                                return { deadline: deadline, matka: matka };
                            }
                        """)
                        if fetched_data:
                            deadline_str = fetched_data.get("deadline", "")
                            matka_str = fetched_data.get("matka", "")
                    except Exception: 
                        pass

            # 2. Secondary Category Extraction (Fallback to Matka)
            if matka_str and not has_distance:
                fallback_cats = extract_categories(matka_str)
                for c in fallback_cats:
                    if c not in event_categories:
                        event_categories.append(c)

            is_holiday = evt["start_date"] in fi_holidays or evt["end_date"] in fi_holidays
            holiday_name = fi_holidays.get(evt["start_date"]) or fi_holidays.get(evt["end_date"]) or ""

            cal = Calendar()
            cal.add('prodid', '-//makkomikko//IRMA Calendar//FI')
            cal.add('version', '2.0')
            event = Event()
            
            irma_id = evt["link"].split('/')[-1] if evt["link"] else clean_filename(evt["name"])
            event.add('uid', f"irma-{irma_id}-{evt['start_date'].strftime('%Y%m%d')}@suunnistusliitto.fi")
            
            event.add('summary', evt["name"])
            event.add('dtstart', evt["start_date"])
            event.add('dtend', evt["end_date"] + datetime.timedelta(days=1))
            event.add('description', f"Organizer: {evt['organizer']}")
            
            safe_location = f"{evt['area']} ({evt['organizer']})".replace(',', ' ')
            event.add('location', safe_location)
            
            event.add('dtstamp', datetime.datetime.now(datetime.timezone.utc))
            if evt["link"]: event.add('url', evt["link"])
            
            cal.add_component(event)
            filename = clean_filename(f"{evt['start_date'].strftime('%Y%m%d')}_{evt['name']}")
            generated_files.add(filename)
            
            with open(os.path.join(OUTPUT_DIR, filename), 'wb') as f:
                f.write(cal.to_ical())

            events_json.append({
                "date": evt["start_date"].strftime('%Y-%m-%d'),
                "name": evt["name"], "location": evt["organizer"], "area": evt["area"],
                "filename": filename, "link": evt["link"], "deadline": deadline_str,
                "matka": matka_str, # Save to JSON to maintain cache
                "cancelled": "peruttu" in evt["name"].lower(), "categories": event_categories,
                "is_holiday": is_holiday, "holiday_name": holiday_name
            })
            
        browser.close()

    with open(events_file, 'w', encoding='utf-8') as f:
        json.dump(events_json, f, ensure_ascii=False, indent=2)

    for filename in os.listdir(OUTPUT_DIR):
        if filename not in generated_files and filename.endswith('.ics'):
            try: os.remove(os.path.join(OUTPUT_DIR, filename))
            except Exception: pass

if __name__ == "__main__":
    main()
