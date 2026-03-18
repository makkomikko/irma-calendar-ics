import os
import json
from playwright.sync_api import sync_playwright

URL = "https://irma.suunnistusliitto.fi/public/club/list"
BASE_URL = "https://irma.suunnistusliitto.fi"
OUTPUT_DIR = "ics_files"

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    clubs_data = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Loading clubs list...")
        page.goto(URL, wait_until="networkidle")
        
        # Grab all rows in the club table
        rows = page.query_selector_all("table tr")
        club_links = []
        
        for row in rows:
            a_tag = row.query_selector("a")
            if a_tag:
                name = a_tag.inner_text().strip()
                href = a_tag.get_attribute("href")
                link = f"{BASE_URL}{href}" if href.startswith("/") else href
                club_links.append({"name": name, "link": link})
                
        print(f"Found {len(club_links)} clubs. Fetching areas...")
        
        for idx, club in enumerate(club_links, 1):
            try:
                # To avoid spamming IRMA too hard, we use a timeout
                page.goto(club["link"], wait_until="networkidle", timeout=10000)
                
                # Look for the row containing the area (Alue)
                alue_row = page.locator("tr", has_text="Alue")
                if alue_row.count() > 0:
                    text = alue_row.first.inner_text()
                    # Clean up "Alue Uusimaa" -> "Uusimaa"
                    area = text.replace("Alue", "").strip()
                    clubs_data[club["name"]] = area
                    
            except Exception:
                print(f"  -> Timeout fetching area for {club['name']}")
                
        browser.close()

    with open(os.path.join(OUTPUT_DIR, 'clubs.json'), 'w', encoding='utf-8') as f:
        json.dump(clubs_data, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully mapped {len(clubs_data)} clubs.")

if __name__ == "__main__":
    main()
