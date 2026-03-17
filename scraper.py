import requests
from bs4 import BeautifulSoup
from datetime import datetime
from ics import Calendar, Event
import os
import json

class CompetitionScraper:
    def __init__(self):
        self.url = "https://irma.suunnistusliitto.fi/public/competitioncalendar/list?year=upcoming&area=all&competition=ALL&previous=undefined&tab=competition"
        self.events = []
    
    def scrape(self):
        """Scrape the competition calendar"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(self.url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all competition rows (adjust selectors based on actual HTML structure)
            # You may need to inspect the page to find correct selectors
            competition_rows = soup.find_all('tr', class_='competition-row')
            
            if not competition_rows:
                # Fallback: try finding divs with competition data
                competition_rows = soup.find_all('div', class_='competition')
            
            for row in competition_rows:
                event_data = self.extract_event_data(row)
                if event_data:
                    self.events.append(event_data)
            
            print(f"✓ Scraped {len(self.events)} competitions")
            return self.events
        
        except Exception as e:
            print(f"✗ Error scraping: {e}")
            return []
    
    def extract_event_data(self, element):
        """Extract event details from HTML element"""
        try:
            # Adjust these selectors based on the actual HTML structure
            name_elem = element.find(class_='competition-name')
            date_elem = element.find(class_='competition-date')
            location_elem = element.find(class_='competition-location')
            
            if not name_elem or not date_elem:
                return None
            
            name = name_elem.get_text(strip=True)
            date_str = date_elem.get_text(strip=True)
            location = location_elem.get_text(strip=True) if location_elem else "TBA"
            
            # Parse date - adjust format based on actual format
            try:
                event_date = datetime.strptime(date_str, "%d.%m.%Y")
            except:
                event_date = datetime.strptime(date_str, "%Y-%m-%d")
            
            return {
                'name': name,
                'date': event_date,
                'location': location
            }
        except Exception as e:
            print(f"Error extracting event: {e}")
            return None
    
    def generate_ics_files(self, output_dir='./ics_files'):
        """Generate ICS files for each event"""
        if not self.events:
            print("No events to process")
            return []
        
        os.makedirs(output_dir, exist_ok=True)
        generated_files = []
        
        for event_data in self.events:
            try:
                cal = Calendar()
                event = Event()
                event.name = event_data['name']
                event.begin = event_data['date']
                event.location = event_data['location']
                event.description = f"Location: {event_data['location']}"
                
                cal.events.add(event)
                
                # Create filename
                filename = self.sanitize_filename(event_data['name'])
                filepath = os.path.join(output_dir, f"{filename}.ics")
                
                # Write to file
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.writelines(cal)
                
                generated_files.append({
                    'name': event_data['name'],
                    'date': event_data['date'].strftime('%Y-%m-%d'),
                    'location': event_data['location'],
                    'filename': f"{filename}.ics"
                })
                
                print(f"✓ Created: {filename}.ics")
            
            except Exception as e:
                print(f"✗ Error creating ICS for {event_data['name']}: {e}")
        
        # Save metadata as JSON
        metadata_path = os.path.join(output_dir, 'events.json')
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(generated_files, f, ensure_ascii=False, indent=2)
        
        return generated_files
    
    @staticmethod
    def sanitize_filename(filename):
        """Convert filename to safe format"""
        invalid_chars = ['<', '>', ':', '"', '/', '\', '|', '?', '*']
        safe_name = filename
        for char in invalid_chars:
            safe_name = safe_name.replace(char, '_')
        return safe_name[:50]  # Limit length

if __name__ == '__main__':
    scraper = CompetitionScraper()
    scraper.scrape()
    scraper.generate_ics_files()