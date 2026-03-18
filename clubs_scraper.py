import os
import json
import time
from playwright.sync_api import sync_playwright

URL = "https://irma.suunnistusliitto.fi/public/club/list"
BASE_URL = "https://irma.suunnistusliitto.fi"
OUTPUT_DIR = "ics_files"

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    clubs_data = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use a realistic user agent to avoid being blocked
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        
        print("Loading clubs list...")
        page.goto(URL, wait_until="networkidle")
        
        # CRITICAL: Wait for the table rows to actually appear
        try:
            page.wait_for_selector("table tr td a", timeout=30000)
        except Exception:
            print("Failed to load club list table.")
            browser.close()
            return

        rows = page.query_selector_all("table tr")
        club_links = []
        
        for row in rows:
            a_tag = row.query_selector("a")
            if a_tag:
                name = a_tag.inner_text().strip()
                href = a_tag.get_attribute("href")
                if href:
                    link = f"{BASE_URL}{href}" if href.startswith("/") else href
                    club_links.append({"name": name, "link": link})
                
        print(f"Found {len(club_links)} clubs. Fetching areas...")
        
        for idx, club in enumerate(club_links, 1):
            try:
                # Navigate and wait for the page to be steady
                page.goto(club["link"], wait_until="networkidle", timeout=20000)
                
                # Wait for the specific label "Alue" to appear in the table
                page.wait_for_selector("text=Alue", timeout=5000)
                
                # Logic: Find the row where the first cell is 'Alue', then get the second cell
                area = page.evaluate("""
                    () => {
                        const rows = Array.from(document.querySelectorAll('tr'));
                        const areaRow = rows.find(r => r.innerText.includes('Alue'));
                        if (areaRow) {
                            const cells = areaRow.querySelectorAll('td');
                            return cells.length > 1 ? cells[1].innerText.trim() : null;
                        }
                        return null;
                    }
                """)

                if area:
                    clubs_data[club["name"]] = area
                    if idx % 20 == 0:
                        print(f"  Processed {idx}/{len(club_links)}...")
                
                # Small human-like pause to prevent rate limiting and ensure load
                time.sleep(0.5)

            except Exception:
                continue
                
        browser.close()

    with open(os.path.join(OUTPUT_DIR, 'clubs.json'), 'w', encoding='utf-8') as f:
        json.dump(clubs_data, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully mapped {len(clubs_data)} clubs.")

if __name__ == "__main__":
    main()
