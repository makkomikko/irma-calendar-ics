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
        
        print("Loading clubs list (Vaadin Grid)...")
        page.goto(URL, wait_until="networkidle")
        
        # 1. Wait for the vaadin-grid element to be present
        try:
            page.wait_for_selector("vaadin-grid", timeout=30000)
            # Give it a moment to initialize the internal rows
            time.sleep(2)
        except Exception:
            print("Failed to find vaadin-grid.")
            browser.close()
            return

        # 2. Extract links using JS that pierces Shadow DOM
        # Vaadin grids often store data in 'vaadin-grid-cell-content' elements
        print("Extracting club links...")
        club_links = page.evaluate("""
            () => {
                const links = [];
                // Query all anchor tags inside the grid's light DOM or shadow DOM slots
                const anchors = document.querySelectorAll('vaadin-grid a');
                anchors.forEach(a => {
                    const name = a.innerText.trim();
                    const href = a.getAttribute('href');
                    if (name && href) {
                        links.push({ name, href });
                    }
                });
                return links;
            }
        """)

        if not club_links:
            print("No clubs found in the grid. Checking for lazy loading...")
            # If empty, we might need to scroll or check a different selector
            # Note: For some Vaadin versions, the links are in 'vaadin-grid-cell-content'
            club_links = page.evaluate("""
                () => {
                    const links = [];
                    const cells = document.querySelectorAll('vaadin-grid-cell-content');
                    cells.forEach(cell => {
                        const a = cell.querySelector('a');
                        if (a) {
                            links.push({ name: a.innerText.trim(), href: a.getAttribute('href') });
                        }
                    });
                    return links;
                }
            """)

        print(f"Found {len(club_links)} clubs. Fetching areas...")
        
        # 3. Visit each club page (these are usually standard HTML, not Vaadin grids)
        for idx, club in enumerate(club_links, 1):
            try:
                full_link = f"{BASE_URL}{club['href']}" if club['href'].startswith("/") else club['href']
                page.goto(full_link, wait_until="networkidle", timeout=20000)
                
                # Use the 'piercing' logic to find the Area
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
                    clubs_data[club['name']] = area
                
                if idx % 20 == 0:
                    print(f"  Processed {idx}/{len(club_links)}...")
                
                time.sleep(0.3)
            except Exception:
                continue
                
        browser.close()

    with open(os.path.join(OUTPUT_DIR, 'clubs.json'), 'w', encoding='utf-8') as f:
        json.dump(clubs_data, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully mapped {len(clubs_data)} clubs.")

if __name__ == "__main__":
    main()
