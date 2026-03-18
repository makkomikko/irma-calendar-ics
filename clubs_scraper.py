import os
import json
import time
from playwright.sync_api import sync_playwright

URL = "https://irma.suunnistusliitto.fi/public/club/list"
BASE_URL = "https://irma.suunnistusliitto.fi"
OUTPUT_DIR = "ics_files"

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 1. LOAD EXISTING CACHE
    clubs_data = {}
    clubs_file = os.path.join(OUTPUT_DIR, 'clubs.json')
    if os.path.exists(clubs_file):
        try:
            with open(clubs_file, 'r', encoding='utf-8') as f:
                clubs_data = json.load(f)
            print(f"Loaded {len(clubs_data)} clubs from cache.")
        except Exception:
            print("Failed to load cache. Starting fresh.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        
        print("Loading clubs list...")
        page.goto(URL, wait_until="networkidle")
        page.wait_for_selector("vaadin-grid", timeout=30000)

        # SCROLLING LOOP: Ensure all clubs in the Vaadin Grid are loaded
        print("Scrolling through grid to capture all clubs...")
        club_links = {}
        last_count = 0
        for _ in range(15):
            new_links = page.evaluate("""
                () => {
                    const found = {};
                    document.querySelectorAll('vaadin-grid a').forEach(a => {
                        const name = a.innerText.trim();
                        const href = a.getAttribute('href');
                        if (name && href) found[name] = href;
                    });
                    return found;
                }
            """)
            club_links.update(new_links)
            
            if len(club_links) == last_count: break 
            last_count = len(club_links)
            
            page.evaluate("document.querySelector('vaadin-grid').scrollBy(0, 1000)")
            time.sleep(0.5)

        print(f"Found {len(club_links)} clubs in the grid. Checking against cache...")
        
        # 2. DETAIL PAGE EXTRACTION (WITH CACHE BYPASS)
        new_clubs_processed = 0
        for name, href in club_links.items():
            # If we already have this club's area cached, skip it!
            if name in clubs_data and clubs_data[name]:
                continue
                
            new_clubs_processed += 1
            try:
                full_link = f"{BASE_URL}{href}" if href.startswith("/") else href
                page.goto(full_link, wait_until="networkidle", timeout=15000)
                
                page.wait_for_selector("#detail-wrapper", timeout=5000)
                
                area = page.evaluate("""
                    () => {
                        const labels = ["Alue", "District", "Region"];
                        const spans = Array.from(document.querySelectorAll('#detail-wrapper span.font-bold'));
                        
                        for (let span of spans) {
                            const text = span.innerText.trim();
                            if (labels.some(l => text.includes(l))) {
                                const nextSpan = span.nextElementSibling;
                                return nextSpan ? nextSpan.innerText.trim() : null;
                            }
                        }
                        return null;
                    }
                """)

                if area:
                    clubs_data[name] = area
                    print(f"  Added new club: {name} -> {area}")
                
                time.sleep(0.2)
            except Exception:
                continue
                
        browser.close()

    # 3. SAVE THE UPDATED CACHE
    with open(clubs_file, 'w', encoding='utf-8') as f:
        json.dump(clubs_data, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully mapped {len(clubs_data)} total clubs. (Scraped {new_clubs_processed} new pages this run)")

if __name__ == "__main__":
    main()
