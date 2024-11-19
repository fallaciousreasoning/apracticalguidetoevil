import multiprocessing
import requests
import re
from bs4 import BeautifulSoup
import html
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm.auto import tqdm
import sys


configs = [{
    'base_url': 'https://palelights.com',
    'title': 'Pale Lights',
    'author': 'erraticerrata'
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

    # Hacky way to properly parse bold and italics text
    text = text.replace("<b>", "**")
    text = text.replace("</b>", "**")
    text = text.replace("<i>", "_")
    text = text.replace("</i>", "_")

    # Hacky way to properly parse the horizontal lines e.g. Book One Chapter 4
    text = text.replace("<hr />", "<p>***</p>")
    text = text.replace("<p>—</p>", "<p>***</p>")

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
    LINK_REGEX = f"<li><a href=\"({config['base_url']}/[0-9]+/[0-9]+/[0-9]+/.*/)\">(.*)</a></li>"
    response = requests.get(TABLE_OF_CONTENTS_URL)
    response_text = response.text

    matches = re.findall(LINK_REGEX, response_text)

    for match in matches:
        # Hacky system for determining the book we want        
        if book != "all" and "prologue" in match[0]:
            book -= 1

        if book != 0 and book != "all": continue

        yield match[0]

def write_book(config, book="all", split=False):
    with ProcessPoolExecutor() as pool:
        book_name = "all books" if book == "all" else f"Book {book}"

        links = list(download_contents(config, book))
        futures = {}
        for link in links:
            future = pool.submit(download_chapter, link)
            futures[future] = link
        
        chapters = {}
        for future in tqdm(as_completed(futures), total=len(futures)):
            chapters[futures[future]] = future.result()

    book_title = ""

    if split:
        book_title = f"{config['title']} - {book_name}.md"
    else:
        book_title = f"{config['title']}.md"

    with open(book_title, "w", encoding='utf-8') as f:
        f.write(f"% {config['title']} ({book_name})\n")
        f.write(f"% {config['author']}\n\n")

        for link in links:
            chapter = chapters[link]
        
            f.write(f"# {chapter.title}\n\n")
            f.write(chapter.text)


def process_args(args):
    split = False

    for i in range(len(args)):
        if args[i] == "-s" or args[i] == "--split":
            split = True
        if args[i] == "-h" or args[i] == "--help":
            print("usage: pyton3 apracticalguidetoevil [args]\n")
            print("-s or --split: Creates seperate .md file for each Book")
            print("-h or --help: Prints this help message")
            exit()

    return [split]

if __name__ == '__main__':
    multiprocessing.set_start_method('spawn', force=True)

    processed_args = process_args(sys.argv[1:])

    if processed_args[0]:
        for config in configs:
            # Finding out how many Books for each series until now
            # (Should be future proof unless they change the formatting again)
            TABLE_OF_CONTENTS_URL = f"{config['base_url']}/table-of-contents/"
            LINK_REGEX = f"<h2.*>Book ([0-9]+|I).*</h2>"
            response = requests.get(TABLE_OF_CONTENTS_URL)
            response_text = response.text
            matches = re.findall(LINK_REGEX, response_text)

            for i in range(1, len(matches)+1):
                print(f"Downloading Book {i} of {config['title']}")
                write_book(config, book=i, split=True)

    else:
        for config in configs:
            print('Downloading', config['title'])
            write_book(config)
