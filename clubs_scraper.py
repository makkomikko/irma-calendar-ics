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
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        
        print("Loading clubs list...")
        page.goto(URL, wait_until="networkidle")
        page.wait_for_selector("vaadin-grid", timeout=30000)

        # 1. SCROLLING LOOP: Ensure all clubs in the Vaadin Grid are loaded
        print("Scrolling through grid to capture all clubs...")
        club_links = {}
        last_count = 0
        for _ in range(15):  # Adjust range if the list is extremely long
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
            
            if len(club_links) == last_count: break # Stop if no new clubs found
            last_count = len(club_links)
            
            # Scroll down the grid container
            page.evaluate("document.querySelector('vaadin-grid').scrollBy(0, 1000)")
            time.sleep(0.5)

        print(f"Found {len(club_links)} clubs. Fetching areas from detail pages...")
        
        # 2. DETAIL PAGE EXTRACTION: Using the new div-based structure
        for idx, (name, href) in enumerate(club_links.items(), 1):
            try:
                full_link = f"{BASE_URL}{href}" if href.startswith("/") else href
                page.goto(full_link, wait_until="networkidle", timeout=15000)
                
                # Wait for the detail wrapper to appear
                page.wait_for_selector("#detail-wrapper", timeout=5000)
                
                area = page.evaluate("""
                    () => {
                        const labels = ["Alue", "District", "Region"];
                        const spans = Array.from(document.querySelectorAll('#detail-wrapper span.font-bold'));
                        
                        for (let span of spans) {
                            const text = span.innerText.trim();
                            if (labels.some(l => text.includes(l))) {
                                // The value is in the next span sibling
                                const nextSpan = span.nextElementSibling;
                                return nextSpan ? nextSpan.innerText.trim() : null;
                            }
                        }
                        return null;
                    }
                """)

                if area:
                    clubs_data[name] = area
                
                if idx % 20 == 0:
                    print(f"  Processed {idx}/{len(club_links)}...")
                
                time.sleep(0.2) # Small delay to avoid hammering the server
            except Exception as e:
                # print(f"Error at {name}: {e}")
                continue
                
        browser.close()

    with open(os.path.join(OUTPUT_DIR, 'clubs.json'), 'w', encoding='utf-8') as f:
        json.dump(clubs_data, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully mapped {len(clubs_data)} clubs.")

if __name__ == "__main__":
    main()
