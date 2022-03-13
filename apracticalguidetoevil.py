import multiprocessing
import requests
import re
from bs4 import BeautifulSoup
import html
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm.auto import tqdm

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
    

def download_contents(book="all"):
    TABLE_OF_CONTENTS_URL = "https://practicalguidetoevil.wordpress.com/table-of-contents/"
    LINK_REGEX = "\<li\><a href=\"(https://practicalguidetoevil.wordpress.com/[0-9]+/[0-9]+/[0-9]+/.*/)\"\>(.*)\</a\>\</li\>"
    response = requests.get(TABLE_OF_CONTENTS_URL)
    response_text = response.text

    matches = re.findall(LINK_REGEX, response_text)

    for match in matches:
        # Hacky system for determining the book we want        
        if book != "all" and "prologue" in match[0]:
            book -= 1

        if book != 0 and book != "all": continue

        yield match[0]

def write_book(book="all", output_file="A Practical Guide to Evil.md"):
    with open(output_file, "w", encoding='utf-8') as f, ProcessPoolExecutor() as pool:
        book_name = "all books" if book == "all" else f"book {book}"
        f.write(f"% A Practical Guide to Evil ({book_name})\n")
        f.write("% erraticerrata\n\n")

        futures = {}
        for link in list(download_contents(book)):
            future = pool.submit(download_chapter, link)
            futures[future] = link
        
        for future in tqdm(as_completed(futures), total=len(futures)):
            chapter = future.result()

            f.write(f"# {chapter.title}\n\n")
            f.write(chapter.text)

if __name__ == '__main__':
    multiprocessing.set_start_method('spawn', force=True)
    write_book()