# Medium Tag Scraper

## Overview
This script scrapes recommended articles from Medium tag pages, extracting:
- Article Title
- Article Link
- Number of Claps

## Setup
1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the script:
```bash
python medium_tag_scraper.py
```

## Customization
- Modify the `tags` list in `main()` to scrape different Medium tags
- Adjust `num_articles` to control the number of articles scraped

## Proxy Configuration

This scraper supports using Oxylabs Web Unblocker to bypass website restrictions.

### Setting Up Proxy Credentials

1. Sign up for an Oxylabs account and obtain your credentials
2. Set the following environment variables:
   ```bash
   export OXYLABS_USERNAME='your_username'
   export OXYLABS_PASSWORD='your_password'
   ```

   On Windows, use:
   ```powershell
   $env:OXYLABS_USERNAME='your_username'
   $env:OXYLABS_PASSWORD='your_password'
   ```

3. Alternatively, you can create a `.env` file in the project root with:
   ```
   OXYLABS_USERNAME=your_username
   OXYLABS_PASSWORD=your_password
   ```

**Note**: Without valid Oxylabs credentials, the scraper may fail to retrieve content from websites with strict access controls.

## API Configuration

### OpenAI API Key Setup

1. Obtain an OpenAI API key from [OpenAI's platform](https://platform.openai.com/account/api-keys)
2. Set the API key as an environment variable:
   ```bash
   export OPENAI_API_KEY='your_openai_api_key'
   ```

   On Windows, use:
   ```powershell
   $env:OPENAI_API_KEY='your_openai_api_key'
   ```

3. Alternatively, create a `.env` file in the project root with:
   ```
   OPENAI_API_KEY=your_openai_api_key
   ```

**Note**: 
- Keep your API key confidential
- Monitor your API usage to manage costs
- The script uses `gpt-3.5-turbo-0125` model by default

## Web Application

### Running the Application

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up environment variables:
   - OpenAI API Key
   - Oxylabs Proxy Credentials (optional)

3. Start the Flask application:
   ```bash
   python app.py
   ```

4. Open your browser and navigate to `http://localhost:5000`

### Features
- Live scraping status updates
- Real-time row count tracking
- Downloadable CSV
- Responsive design

### Scraping Workflow
1. Click "Start Scraping" button
2. Watch progress in real-time
3. Download CSV when scraping is complete

**Note**: 
- Scraping may take several minutes
- Ensure stable internet connection
- Monitor API usage costs

## Notes
- Respects Medium's robots.txt and uses a user agent
- Saves articles to individual CSV files per tag
- Handles potential scraping errors gracefully

## Gemini Integration

### Setup
1. Obtain a Google AI Gemini API key
2. Set the API key as an environment variable:
```bash
export GOOGLE_AI_API_KEY='your_api_key_here'
```

### Running Gemini Analysis
```bash
python gemini_article_analyzer.py
```

### Features
- Analyzes Medium articles using Gemini
- Generates summaries, key topics, and audience insights
- Saves analysis to CSV files

### Requirements
- Google Generative AI library
- Pandas

## Dependencies
- requests
- beautifulsoup4
