import multiprocessing
import requests
import re
from bs4 import BeautifulSoup
import html
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm.auto import tqdm


configs = [{
    'base_url': 'https://palelights.com',
    'title': 'Pale Lights',
    'author': 'erraticerrata',
}, {
    'base_url': 'https://practicalguidetoevil.wordpress.com',
    'title': 'A Practical Guide to Evil',
    'author': 'erraticerrata'
}]

BASE_URL = 'https://palelights.com'

class Chapter:
    def __init__(self, title, text):
        self.title = title
        self.text = text

def download_chapter(url):
    text = requests.get(url).text
    soup = BeautifulSoup(text, "html.parser")

    content = ""

    title_node = soup.find("h1", { "class": "entry-title" })
    title = title_node.text

    entry_content = soup.find("div", { "class" : "entry-content" })
    for child in entry_content.findChildren():
        if child.name != "p": continue

        content += html.unescape(child.text) + "\n\n"

    return Chapter(title, content)
    

def download_contents(config, book: str):
    TABLE_OF_CONTENTS_URL = f"{config['base_url']}/table-of-contents/"
    LINK_REGEX = f"\<li\><a href=\"({config['base_url']}/[0-9]+/[0-9]+/[0-9]+/.*/)\"\>(.*)\</a\>\</li\>"
    response = requests.get(TABLE_OF_CONTENTS_URL)
    response_text = response.text

    matches = re.findall(LINK_REGEX, response_text)

    for match in matches:
        # Hacky system for determining the book we want        
        if book != "all" and "prologue" in match[0]:
            book -= 1

        if book != 0 and book != "all": continue

        yield match[0]

def write_book(config, book="all"):
    with ProcessPoolExecutor() as pool:
        book_name = "all books" if book == "all" else f"book {book}"

        links = list(download_contents(config, book))
        futures = {}
        for link in links:
            future = pool.submit(download_chapter, link)
            futures[future] = link
        
        chapters = {}
        for future in tqdm(as_completed(futures), total=len(futures)):
            chapters[futures[future]] = future.result()


    with open(f"{config['title']}.md", "w", encoding='utf-8') as f:
        f.write(f"% {config['title']} ({book_name})\n")
        f.write(f"% {config['author']}\n\n")

        for link in links:
            chapter = chapters[link]
        
            f.write(f"# {chapter.title}\n\n")
            f.write(chapter.text)

if __name__ == '__main__':
    multiprocessing.set_start_method('spawn', force=True)

    for config in configs:
        print('Downloading', config['title'])
        write_book(config)
