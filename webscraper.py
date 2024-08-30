import aiohttp
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import os
import time

class FileOperation:
    """
    Handles file operations such as reading/writing files and saving content to files.
    """
    def __init__(self, data_folder, status_file):
        """
        Initializes the FileOperation class with the provided data folder and status file.
        Creates the data folder if it doesn't exist and loads the status of visited links.
        """
        self.data_folder = data_folder
        self.status_file = status_file
        if not os.path.exists(self.data_folder):
            os.makedirs(self.data_folder)
        self.visitedlinks = self.load_status()

    def load_status(self):
        """
        Loads the status of visited links from a JSON file.
        Returns a dictionary with the visited links and their status.
        """
        if os.path.exists(self.status_file):
            with open(self.status_file, 'r', encoding='utf-8') as file:
                return json.load(file)
        return {}

    def save_status(self):
        """
        Saves the current status of visited links to a JSON file.
        """
        with open(self.status_file, 'w', encoding='utf-8') as file:
            json.dump(self.visitedlinks, file, indent=4)

    def create_file(self, url):
        """
        Generates a filename based on the URL by converting the URL path to a valid filename.
        Returns the full path to the file where the content will be saved.
        """
        parsed_url = urlparse(url)
        path = parsed_url.path.strip("/").replace("/", "_")
        if not path:
            path = "index"
        return os.path.join(self.data_folder, f"{parsed_url.netloc}_{path}.txt")

    def write_pdf(self, url, content):
        """
        Writes PDF content to a file named based on the URL.
        """
        filename = self.create_file(url).replace(".txt", ".pdf")
        with open(filename, 'wb') as pdf_file:
            pdf_file.write(content)

    def write_text(self, url, content):
        """
        Writes text content to a file named based on the URL.
        """
        filename = self.create_file(url)
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(content)

    def add_to_extralinks(self, url):
        """
        Appends non-domain links to an external links file for further analysis.
        """
        with open("extralinks.txt", "a") as f:
            f.write(url + "\n")


class URLcheck:
    """
    Handles URL validation and extraction of links from HTML content.
    """
    def __init__(self, domain):
        """
        Initializes the URLcheck class with the domain to validate links against.
        """
        self.domain = domain

    def check_link(self, url):
        """
        Checks if a given URL belongs to the domain being scraped.
        Returns True if the URL is within the domain, otherwise False.
        """
        parsed_url = urlparse(url)
        return parsed_url.netloc == self.domain

    def extract_links(self, soup, base_url):
        """
        Extracts and validates all links from the given BeautifulSoup object.
        Only adds links that belong to the same domain as the base URL.
        """
        links = set()
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            full_url = urljoin(base_url, href)
            if self.check_link(full_url):
                links.add(full_url)
            else:
                file_op.add_to_extralinks(full_url)
        return links


class Scraper:
    """
    Asynchronously scrapes web pages, processes content, and handles linked resources.
    """
    def __init__(self, file_op, crawler, lock, request_delay):
        """
        Initializes the Scraper class with the necessary components for scraping.
        """
        self.file_op = file_op
        self.crawler = crawler
        self.lock = lock
        self.request_delay = request_delay

    async def fetch(self, session, url):
        """
        Asynchronously fetches the content of a given URL using aiohttp.
        Returns the content of the page if successful, otherwise None.
        """
        async with session.get(url) as response:
            if response.status == 200:
                return await response.text()
            else:
                return None

    async def process_page(self, soup, url):
        """
        Processes the HTML content of a page, extracts main text, and saves it.
        """
        for script in soup(["script", "style", "nav", "header", "footer", "img"]):
            script.extract()
        main_text = soup.get_text(strip=True)
        main_content = soup.find("main")
        if main_content:
            main_text = main_content.get_text("\n", strip=True)
        self.file_op.write_text(url, main_text)

    async def scrape(self, session, url):
        """
        Scrapes a given URL, processes its content, and recursively scrapes linked pages.
        """
        async with self.lock:
            if url in self.file_op.visitedlinks:
                return
            self.file_op.visitedlinks[url] = "pending"
        print(f"Visiting: {url}")

        content = await self.fetch(session, url)
        if content is None:
            async with self.lock:
                self.file_op.visitedlinks[url] = "failed"
            return

        async with self.lock:
            self.file_op.visitedlinks[url] = "success"

        try:
            soup = BeautifulSoup(content, 'html.parser')
            links = self.crawler.extract_links(soup, url)
            await self.process_page(soup, url)
            tasks = []
            for link in links:
                if any(substring in link.lower() for substring in ["lxml"]):
                    continue
                if link.lower().endswith(".pdf"):
                    tasks.append(self.download_pdf(session, link))
                else:
                    tasks.append(self.scrape(session, link))
            await asyncio.gather(*tasks)
            await asyncio.sleep(self.request_delay)
        except Exception as e:
            print(f"An error occurred while processing {url}: {e}")

        self.file_op.save_status()

    async def download_pdf(self, session, url):
        """
        Asynchronously downloads and saves a PDF from a given URL.
        """
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    self.file_op.write_pdf(url, await response.read())
                    async with self.lock:
                        self.file_op.visitedlinks[url] = "success"
                else:
                    async with self.lock:
                        self.file_op.visitedlinks[url] = "failed"
        except Exception as e:
            print(f"Failed to download PDF {url}: {e}")
            async with self.lock:
                self.file_op.visitedlinks[url] = "failed"


# Setup
mainurl = "https://www.wscacademy.org/"
domain = urlparse(mainurl).netloc
data_folder = "wscadata"
status_file = os.path.join(data_folder, "linkscraped.json")

file_op = FileOperation(data_folder, status_file)
urlcheck = URLcheck(domain)
lock = asyncio.Lock()
request_delay = 1  # Delay in seconds between requests

scraper = Scraper(file_op, urlcheck, lock, request_delay)

# Measure the time taken for the entire scraping process
start_time = time.time()

async def main():
    """
    Main entry point for the asynchronous scraping operation.
    Initializes an aiohttp session and starts scraping from the main URL.
    """
    async with aiohttp.ClientSession() as session:
        await scraper.scrape(session, mainurl)

# Start scraping the main URL
asyncio.run(main())

end_time = time.time()
overall_time = end_time - start_time

print(f"Done! Check Data")
print(f"Total time taken: {overall_time} seconds")