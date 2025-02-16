import os
import logging
import time
from typing import List, Dict
import pandas as pd
import requests
import json
from tenacity import retry, stop_after_attempt, wait_exponential
from bs4 import BeautifulSoup, Comment
from dotenv import load_dotenv
from openai import OpenAI
import random
import uuid
from datetime import datetime

# Configure logging
logging.basicConfig(
    filename='medium_scraper_debug.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

class MediumTagScraper:
    def __init__(self, tags_file='tags/medium_tags.txt', output_file=None, max_articles_per_tag=10):
        """
        Initialize the Medium Tag Scraper.
        
        :param tags_file: Path to the file containing Medium tags
        :param output_file: Optional custom output CSV file. If None, generates a unique filename
        :param max_articles_per_tag: Maximum number of articles to scrape per tag
        """
        load_dotenv()
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        # Generate a unique filename if not provided
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            output_file = f'medium_articles_{timestamp}_{unique_id}.csv'
        
        # Ensure the output is in the current directory
        self.output_file = os.path.basename(output_file)
        
        self.tags = self._load_tags(tags_file)
        self.max_articles_per_tag = max_articles_per_tag
        self.all_articles = []  # Consolidated list of articles
        
        # Validate OpenAI API key
        if not self.client.api_key:
            logger.error("OpenAI API key not found. Set OPENAI_API_KEY in .env file.")
            raise ValueError("Missing OpenAI API key")

        # Validate and warn about Oxylabs credentials
        self.oxylabs_username = os.getenv('OXYLABS_USERNAME')
        self.oxylabs_password = os.getenv('OXYLABS_PASSWORD')
        
        if not self.oxylabs_username or not self.oxylabs_password:
            logger.warning(
                "Oxylabs proxy credentials not found. "
                "Please set OXYLABS_USERNAME and OXYLABS_PASSWORD environment variables. "
                "Scraping may fail without a valid proxy."
            )

        logger.info(f"Initialized scraper. Output will be saved to: {self.output_file}")

    def _load_tags(self, tags_file):
        """
        Load tags from a text file, removing comments and empty lines
        
        :param tags_file: Path to tags file
        :return: List of cleaned tags
        """
        try:
            with open(tags_file, 'r') as f:
                # Read lines, strip whitespace, remove comments and empty lines
                tags = [
                    line.strip() 
                    for line in f 
                    if line.strip() and not line.strip().startswith('#')
                ]
            
            # Remove duplicates while preserving order
            tags = list(dict.fromkeys(tags))
            
            logger.info(f"Loaded {len(tags)} unique tags")
            return tags
        
        except Exception as e:
            logger.error(f"Error loading tags: {e}")
            return []

    def clean_html(self, html_content: str):
        """
        Return raw HTML content without any cleaning.
        
        Args:
            html_content (str): Raw HTML content
        
        Returns:
            str: Unmodified HTML content
        """
        # Log the full HTML content for debugging
        logger.info(f"Raw HTML content (length: {len(html_content)} chars)")
        
        return html_content

    @retry(stop=stop_after_attempt(3), 
           wait=wait_exponential(multiplier=1, min=4, max=10))
    def process_html_with_chatgpt(self, html_content: str, tag: str) -> List[Dict[str, str]]:
        """
        Process HTML content using ChatGPT to extract article information.
        
        :param html_content: Raw HTML content
        :param tag: Current tag being processed
        :return: List of extracted article dictionaries
        """
        try:
            # Clean the HTML content
            cleaned_html = self.clean_html(html_content)
            
            # Ensure cleaned HTML is not empty
            if not cleaned_html or len(cleaned_html) < 100:
                logger.warning(f"Insufficient HTML content for tag {tag}")
                return []
            
            # Detailed prompt for ChatGPT to extract structured data
            messages = [
                {
                    "role": "system", 
                    "content": '''You are a web scraping assistant for Medium. 
                    Extract article information STRICTLY following these rules:
                    1. Return a valid JSON object with a key "articles"
                    2. "articles" must be an array of article objects
                    3. Each article object must have exactly these 4 keys and make sure extract the right Title , url and claps: 
                       - "title": Article title (string, non-empty)
                       - "link": Full Medium article URL (string, valid URL)
                       - "claps": Number of claps (string, e.g. "1.2K")
                       - "tag": Tag of the article (string)
                    4. Extract all articles
                    5. If no articles found, return an empty articles array
                    
                    Example output:
                    {
                        "articles": [
                            {
                                "title": "AI makes you smarter, not lazier",
                                "link": "https://medium.com/darius-foroux/ai-makes-you-smarter-not-lazier-75eb46976123",
                                "claps": "351",
                                "tag": "ai"
                            }
                        ]
                    }'''
                },
                {
                    "role": "user", 
                    "content": f"Extract articles from this HTML:\n{cleaned_html}"
                }
            ]

            # Send request to ChatGPT
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Use the latest stable model
                messages=messages,
                max_tokens=16383,  # Adjust based on model limits
                temperature=0.6,
                response_format={"type": "json_object"}
            )

            # Parse response
            try:
                # Attempt to parse the response, with error handling
                raw_response = response.choices[0].message.content.strip()
                
                # Log the raw response for debugging
                logger.debug(f"Raw ChatGPT response for tag {tag}: {raw_response}")
                
                # Attempt JSON parsing with multiple strategies
                try:
                    parsed_response = json.loads(raw_response)
                    
                    # Extract articles, ensuring the structure matches our expectation
                    articles = parsed_response.get('articles', [])
                except json.JSONDecodeError:
                    # Try removing any leading/trailing non-JSON characters
                    import re
                    json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
                    if json_match:
                        parsed_response = json.loads(json_match.group(0))
                        articles = parsed_response.get('articles', [])
                    else:
                        logger.error(f"Failed to parse JSON for tag {tag}")
                        return []
                
                # Validate and clean articles
                valid_articles = []
                for article in articles:
                    # Ensure all required keys exist and are non-empty
                    if (all(key in article for key in ['title', 'link', 'claps']) and 
                        article.get('title') and article.get('link')):
                        article['tag'] = tag
                        valid_articles.append(article)
                
                # Log the number of valid articles found
                logger.info(f"Found {len(valid_articles)} valid articles for tag {tag}")
                
                return valid_articles
            
            except Exception as parse_error:
                logger.error(f"Article parsing error for tag {tag}: {parse_error}")
                return []

        except Exception as e:
            logger.error(f"ChatGPT processing error for tag {tag}: {e}")
            return []

    def _fetch_tag_page(self, tag: str) -> str:
        """
        Fetch the recommended page for a given Medium tag using a proxy.
        
        :param tag: Medium tag to fetch
        :return: Raw HTML content
        """
        try:
            # Load proxy credentials from environment variables
            proxies = {
                'http': f'http://{self.oxylabs_username}:{self.oxylabs_password}@unblock.oxylabs.io:60000',
                'https': f'https://{self.oxylabs_username}:{self.oxylabs_password}@unblock.oxylabs.io:60000'
            }
            
            url = f"https://medium.com/tag/{tag}/recommended"
            logger.info(f"Fetching tag page: {url}")
            
            # Perform request with proxy and additional headers to mimic browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
            
            response = requests.get(
                url, 
                headers=headers,
                proxies=proxies,
                timeout=15,
                verify=False  # Disable SSL verification when using proxy
            )
            response.raise_for_status()
            
            return response.text
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Proxy request error for tag {tag}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching tag page: {e}")
            raise

    def scrape_all_tags(self):
        """
        Scrape articles for all specified tags and return a list of articles.
        
        :return: List of all scraped articles
        """
        # Reset the all_articles list to ensure clean start
        self.all_articles = []
        
        # Shuffle tags to distribute API calls
        random.shuffle(self.tags)
        
        # Iterate through tags
        for tag in self.tags:
            try:
                # Fetch and process articles for the current tag
                tag_articles = self.scrape_tag(tag)
                
                # Add articles to the consolidated list
                if tag_articles:
                    self.all_articles.extend(tag_articles)
                    
                    # Save articles to CSV after processing each tag
                    tag_articles_df = pd.DataFrame(tag_articles)
                    self.save_articles(tag_articles)
                    
                    logger.info(f"Processed {len(tag_articles)} articles for tag {tag}")
                
                # Optional: Add a delay between tags to avoid rate limiting
                time.sleep(random.uniform(1, 3))
                
            except Exception as e:
                logger.error(f"Error scraping tag {tag}: {e}")
                continue
        
        logger.info(f"Total articles scraped: {len(self.all_articles)}")
        return self.all_articles

    def scrape_tag(self, tag, max_articles=None):
        """
        Scrape articles for a specific tag.
        
        :param tag: Tag to scrape articles for
        :param max_articles: Maximum number of articles to scrape (defaults to self.max_articles_per_tag)
        :return: List of articles for the tag
        """
        if max_articles is None:
            max_articles = self.max_articles_per_tag
        
        logger.info(f"Fetching tag page: https://medium.com/tag/{tag}/recommended")
        
        try:
            # Fetch and save raw HTML
            raw_html = self._fetch_tag_page(tag)
            raw_html_filename = f"{tag}_raw_page.html"
            with open(raw_html_filename, 'w', encoding='utf-8') as f:
                f.write(raw_html)
            logger.info(f"Saved raw HTML to {raw_html_filename}")
            
            # Process HTML with ChatGPT
            logger.info(f"Sending HTML for tag {tag} to ChatGPT for processing")
            logger.info(f"Raw HTML content (length: {len(raw_html)} chars)")
            
            # Use existing method to process HTML
            tag_articles = self.process_html_with_chatgpt(raw_html, tag)
            
            # Limit articles if necessary
            tag_articles = tag_articles[:max_articles]
            
            logger.info(f"Found {len(tag_articles)} valid articles for tag {tag}")
            
            return tag_articles
        
        except Exception as e:
            logger.error(f"Error scraping tag {tag}: {e}")
            return []

    def save_articles(self, articles):
        """
        Save articles to a CSV file with unique naming.
        
        :param articles: List of scraped articles
        """
        try:
            # Ensure no existing file is overwritten
            articles_df = pd.DataFrame(articles)
            articles_df.to_csv(self.output_file, mode='a', header=False, index=False)
            logger.info(f"Articles saved to {self.output_file}")
            return self.output_file
        except Exception as e:
            logger.error(f"Error saving articles: {e}")
            raise

def main():
    """
    Main function to run the Medium Tag Scraper.
    Supports up to 10 tags.
    """
    # Define a list of up to 10 tags to scrape
    tags_file = 'tags/medium_tags.txt'
    
    # Initialize and run the scraper
    scraper = MediumTagScraper(tags_file)
    scraper.scrape_all_tags()

if __name__ == "__main__":
    main()
