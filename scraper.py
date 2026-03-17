import os
import re
import json
import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
import datetime

URL = "https://irma.suunnistusliitto.fi/public/competitioncalendar/list?year=upcoming&area=all&competition=ALL&previous=undefined&tab=competition"
OUTPUT_DIR = "ics_files"

def parse_fi_date(date_str):
    """
    Extracts start and end dates from Finnish date strings.
    Handles:
    - 15.5.2024 (Single day)
    - 15.-16.5.2024 (Range, same month)
    - 31.5.-1.6.2024 (Range, different months)
    """
    nums = [int(x) for x in re.findall(r'\d+', date_str)]
    start_date = end_date = None
    
    try:
        if len(nums) == 3: # DD.MM.YYYY
            start_date = datetime.date(nums[2], nums[1], nums[0])
            end_date = start_date
        elif len(nums) == 4: # DD1.-DD2.MM.YYYY
            start_date = datetime.date(nums[3], nums[2], nums[0])
            end_date = datetime.date(nums[3], nums[2], nums[1])
        elif len(nums) == 5: # DD1.MM1.-DD2.MM2.YYYY
            start_date = datetime.date(nums[4], nums[1], nums[0])
            end_date = datetime.date(nums[4], nums[3], nums[2])
        elif len(nums) == 6: # DD1.MM1.YYYY-DD2.MM2.YYYY
            start_date = datetime.date(nums[2], nums[1], nums[0])
            end_date = datetime.date(nums[5], nums[4], nums[3])
    except ValueError:
        # Catch invalid dates (e.g., February 30th) if they ever occur
        pass
        
    return start_date, end_date

def clean_filename(name):
    """Removes invalid characters to create a safe filename."""
    # Keep alphanumeric, spaces, and dashes
    cleaned = re.sub(r'[^\w\s-]', '', name).strip()
    return cleaned.replace(' ', '_') + '.ics'

def main():
    # 1. Setup output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 2. Fetch the HTML
    print("Fetching calendar data...")
    response = requests.get(URL)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')
    
    events_json = []
    
    # 3. Parse rows across all tables (resilient to minor layout changes)
    print("Parsing events...")
    for row in soup.find_all('tr'):
        cols = row.find_all(['td', 'th'])
        
        # We need at least 4 columns: Date, Name, Organizer, Discipline
        if len(cols) >= 4:
            date_str = cols[0].get_text(strip=True)
            name = cols[1].get_text(strip=True)
            organizer = cols[2].get_text(strip=True)
            discipline = cols[3].get_text(strip=True)
            
            # Quick check to skip header rows (does the date column have numbers?)
            if not any(char.isdigit() for char in date_str):
                continue
            
            # 4. Filter for "S" (Normal Orienteering)
            # Use regex \bS\b to ensure we match the exact letter "S", 
            # avoiding false positives if "S" is part of another word.
            if not re.search(r'\bS\b', discipline):
                continue
                
            # 5. Parse the date
            start_date, end_date = parse_fi_date(date_str)
            if not start_date:
                continue
                
            # For ICS all-day events, the end date must be strictly *exclusive* (+1 day)
            ics_end_date = end_date + datetime.timedelta(days=1)
            
            # 6. Build the ICS File
            cal = Calendar()
            cal.add('prodid', '-//IRMA Orienteering Calendar Scraper//')
            cal.add('version', '2.0')
            
            event = Event()
            event.add('summary', name)
            event.add('dtstart', start_date)
            event.add('dtend', ics_end_date)
            event.add('location', organizer)
            event.add('dtstamp', datetime.datetime.now())
            
            # Create a unique ID for the calendar event
            uid_string = f"{start_date.strftime('%Y%m%d')}-{clean_filename(name)}@irma-scraper"
            event.add('uid', uid_string)
            
            cal.add_component(event)
            
            # 7. Save the ICS File
            filename = clean_filename(f"{start_date.strftime('%Y%m%d')}_{name}")
            filepath = os.path.join(OUTPUT_DIR, filename)
            
            with open(filepath, 'wb') as f:
                f.write(cal.to_ical())
                
            # 8. Add to JSON tracking list
            events_json.append({
                "date": start_date.strftime('%Y-%m-%d'),
                "name": name,
                "location": organizer,
                "filename": filename
            })

    # 9. Save the events.json file for the HTML frontend
    json_path = os.path.join(OUTPUT_DIR, 'events.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(events_json, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully scraped and generated {len(events_json)} normal orienteering events.")

if __name__ == '__main__':
    main()
