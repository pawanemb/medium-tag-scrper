import os
import threading
import pandas as pd
from flask import Flask, render_template, send_file, jsonify, Response
from flask_socketio import SocketIO
from medium_tag_scraper import MediumTagScraper
import logging
import time
import csv
import io
import shutil
import uuid

# Configure logging
logging.basicConfig(
    filename='medium_scraper_debug.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global variables to track scraping state
SCRAPING_IN_PROGRESS = False
TOTAL_ROWS = 0
LAST_UPDATE_TIME = 0
UPDATE_INTERVAL = 2  # seconds between updates
CURRENT_CSV_DATA = []
DOWNLOAD_FOLDER = 'downloads'

# Ensure download folder exists
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')

@app.route('/download-current')
def download_current_csv():
    """Download the current state of the CSV during scraping."""
    try:
        # Generate a unique filename
        unique_filename = f'medium_articles_{uuid.uuid4().hex[:8]}.csv'
        download_path = os.path.join(DOWNLOAD_FOLDER, unique_filename)
        
        # Copy current CSV to downloads folder
        if os.path.exists('medium_articles.csv'):
            shutil.copy('medium_articles.csv', download_path)
        else:
            # Create an empty CSV if no data
            with open(download_path, 'w', newline='') as f:
                f.write('tag,title,url,author,description,published_date\n')
        
        # Return the file for download
        return send_file(
            download_path, 
            as_attachment=True, 
            download_name=unique_filename
        )
    except Exception as e:
        logger.error(f"Download error: {e}")
        return str(e), 500

@app.route('/download')
def download_csv():
    """Download the CSV file."""
    csv_path = 'medium_articles.csv'
    try:
        return send_file(csv_path, as_attachment=True, download_name='medium_articles.csv')
    except Exception as e:
        logger.error(f"Download error: {e}")
        return str(e), 500

@app.route('/stream-csv')
def stream_csv():
    """Stream CSV data in real-time."""
    def generate():
        global CURRENT_CSV_DATA
        
        # If no data, return empty CSV
        if not CURRENT_CSV_DATA:
            yield 'No data available'
            return
        
        # Use StringIO to create an in-memory CSV
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)
        
        # Write headers
        writer.writerow(CURRENT_CSV_DATA[0])
        output.seek(0)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        
        # Write data rows
        for row in CURRENT_CSV_DATA[1:]:
            writer.writerow(row)
            output.seek(0)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
    
    return Response(generate(), mimetype='text/csv')

@app.route('/status')
def get_status():
    """Get current scraping status."""
    return jsonify({
        'scraping_in_progress': SCRAPING_IN_PROGRESS,
        'total_rows': TOTAL_ROWS,
        'download_enabled': os.path.exists('medium_articles.csv') and os.path.getsize('medium_articles.csv') > 0
    })

def update_row_count(force=False):
    """Update total rows in the CSV with rate limiting."""
    global TOTAL_ROWS, LAST_UPDATE_TIME, CURRENT_CSV_DATA
    current_time = time.time()
    
    try:
        # Check if file exists and is not empty
        if not os.path.exists('medium_articles.csv') or os.path.getsize('medium_articles.csv') == 0:
            return
        
        # Rate limit updates
        if force or (current_time - LAST_UPDATE_TIME >= UPDATE_INTERVAL):
            # Read the entire CSV
            with open('medium_articles.csv', 'r', newline='', encoding='utf-8') as csvfile:
                csv_reader = csv.reader(csvfile)
                CURRENT_CSV_DATA = list(csv_reader)
            
            # Subtract 1 to exclude header row
            new_total_rows = max(0, len(CURRENT_CSV_DATA) - 1)
            
            # Only emit if rows have changed
            if new_total_rows != TOTAL_ROWS:
                TOTAL_ROWS = new_total_rows
                socketio.emit('row_update', {
                    'total_rows': TOTAL_ROWS, 
                    'latest_rows': CURRENT_CSV_DATA[-5:] if TOTAL_ROWS > 0 else [],
                    'download_enabled': True
                })
                LAST_UPDATE_TIME = current_time
    
    except Exception as e:
        logger.error(f"Error updating row count: {e}")

def periodic_row_update():
    """Periodically update row count during scraping."""
    global SCRAPING_IN_PROGRESS
    while SCRAPING_IN_PROGRESS:
        update_row_count()
        time.sleep(UPDATE_INTERVAL)

def scrape_medium_tags(max_articles_per_tag):
    """Background thread for scraping Medium tags."""
    global SCRAPING_IN_PROGRESS, TOTAL_ROWS, CURRENT_CSV_DATA
    
    try:
        # Ensure clean start
        if os.path.exists('medium_articles.csv'):
            os.remove('medium_articles.csv')
        
        SCRAPING_IN_PROGRESS = True
        TOTAL_ROWS = 0
        CURRENT_CSV_DATA = []
        socketio.emit('scrape_status', {'status': 'started'})
        
        # Start periodic row update
        update_thread = threading.Thread(target=periodic_row_update)
        update_thread.start()
        
        # Initialize and run the scraper
        scraper = MediumTagScraper('tags/medium_tags.txt', max_articles_per_tag=max_articles_per_tag)
        scraper.scrape_tags()
        
        # Final update
        update_row_count(force=True)
        socketio.emit('scrape_status', {'status': 'completed'})
    
    except Exception as e:
        logger.error(f"Scraping error: {e}")
        socketio.emit('scrape_status', {'status': 'error', 'message': str(e)})
    
    finally:
        SCRAPING_IN_PROGRESS = False

@socketio.on('start_scraping')
def handle_start_scraping(max_articles_per_tag):
    """Handle start scraping event from client."""
    global SCRAPING_IN_PROGRESS
    
    if not SCRAPING_IN_PROGRESS:
        # Start scraping in a background thread
        threading.Thread(target=scrape_medium_tags, args=(max_articles_per_tag,)).start()
    else:
        socketio.emit('scrape_status', {'status': 'already_running'})

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
