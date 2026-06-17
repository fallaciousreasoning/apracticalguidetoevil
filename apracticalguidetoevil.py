import multiprocessing
import requests
import re
import json
import html
import time
from bs4 import BeautifulSoup
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm.auto import tqdm
import sys


# Royal Road sits behind Cloudflare and rejects requests that don't look like a
# real browser, so every request to it must carry a browser User-Agent.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Pale Lights moved from palelights.com (WordPress) to Royal Road partway
# through its run; the WordPress site is frozen at Book 2 and is no longer the
# source of truth. A Practical Guide to Evil is still hosted on WordPress.
configs = [{
    'source': 'royalroad',
    'fiction_url': 'https://www.royalroad.com/fiction/65058/pale-lights',
    'title': 'Pale Lights',
    'author': 'erraticerrata'
}, {
    'source': 'wordpress',
    'base_url': 'https://practicalguidetoevil.wordpress.com',
    'title': 'A Practical Guide to Evil',
    'author': 'erraticerrata'
}]


class Chapter:
    def __init__(self, title, text):
        self.title = title
        self.text = text


def _to_markdown_inline(text):
    """Replaces inline HTML emphasis tags with their Markdown equivalents.

    This is the same hacky pre-parse substitution the project has always used:
    the markers survive as literal characters in the extracted paragraph text.
    """
    text = text.replace("<b>", "**").replace("</b>", "**")
    text = text.replace("<strong>", "**").replace("</strong>", "**")
    text = text.replace("<i>", "_").replace("</i>", "_")
    text = text.replace("<em>", "_").replace("</em>", "_")

    # Normalise the various scene-break separators to a literal "***".
    text = re.sub(r"<hr\s*/?>", "<p>***</p>", text)
    text = text.replace("<p>—</p>", "<p>***</p>")
    return text


# ----- WordPress source (A Practical Guide to Evil) -----

def download_chapter(url):
    text = _to_markdown_inline(requests.get(url).text)

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
        if book != "all" and "prologue" in match[0] and config['title'] == "A Practical Guide to Evil":
            book -= 1

        elif book != "all" and ("chapter-1/" in match[0] or "chapter-1-" in match[0]) and config['title'] == "Pale Lights":
            book -= 1

        if book != 0 and book != "all": continue

        yield match[0]


# ----- Royal Road source (Pale Lights) -----

def royalroad_chapter_list(config):
    """Returns the ordered list of (url, title) for every published chapter.

    Royal Road embeds the full chapter index as a `window.chapters = [...]`
    JSON array on the fiction page, which is far more reliable to parse than the
    rendered HTML table.

    Args:
      config: A Royal Road config entry containing `fiction_url`.

    Returns:
      A list of (chapter_url, chapter_title) tuples in reading order.
    """
    response = requests.get(config['fiction_url'], headers={'User-Agent': USER_AGENT})
    response.raise_for_status()

    match = re.search(r'window\.chapters\s*=\s*(\[.*?\]);', response.text, re.S)
    if match is None:
        raise RuntimeError(f"Could not find chapter list on {config['fiction_url']}")

    chapters = json.loads(match.group(1))
    chapters.sort(key=lambda chapter: chapter['order'])

    return [
        (f"{config['fiction_url']}/chapter/{chapter['id']}/{chapter['slug']}", chapter['title'])
        for chapter in chapters
    ]


def _royalroad_hidden_classes(soup):
    """Returns CSS class names Royal Road hides via a `display: none` rule.

    Royal Road's anti-piracy measure injects a paragraph carrying a per-chapter,
    randomly-named class that is hidden through an inline <style> block. Parsing
    those class names lets us strip the injected text before it pollutes the
    extracted chapter.
    """
    hidden = set()
    for style in soup.find_all("style"):
        css = style.string or ""
        for rule in re.finditer(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", css):
            body = rule.group(2)
            if re.search(r"display\s*:\s*none", body):
                hidden.add(rule.group(1))
    return hidden


def download_royalroad_chapter(session, url, title):
    """Downloads and cleans a single Royal Road chapter.

    Args:
      session: A `requests.Session` reused across chapters.
      url: The full chapter URL.
      title: The chapter title (taken from the fiction index).

    Returns:
      A `Chapter` with the cleaned, Markdown-flavoured body.
    """
    response = None
    for attempt in range(3):
        response = session.get(url, headers={'User-Agent': USER_AGENT})
        if response.status_code == 200:
            break
        time.sleep(2 ** attempt)  # back off if Cloudflare throttles us
    response.raise_for_status()

    soup = BeautifulSoup(_to_markdown_inline(response.text), "html.parser")

    content_node = soup.find("div", { "class": "chapter-content" })
    if content_node is None:
        raise RuntimeError(f"No chapter content found at {url}")

    # Strip Royal Road's hidden anti-piracy text (both class- and inline-hidden).
    for class_name in _royalroad_hidden_classes(soup):
        for node in content_node.find_all(class_=class_name):
            node.decompose()
    for node in content_node.find_all(style=re.compile(r"display\s*:\s*none")):
        node.decompose()

    content = ""
    for child in content_node.find_all("p"):
        content += html.unescape(child.text) + "\n\n"

    return Chapter(title, content)


def download_royalroad_book(config):
    """Downloads every Pale Lights chapter from Royal Road, in order.

    Royal Road is fetched sequentially with a shared session and a short delay
    to stay polite and avoid Cloudflare rate limiting (unlike the parallel
    WordPress path).
    """
    chapter_list = royalroad_chapter_list(config)
    session = requests.Session()

    chapters = []
    for url, title in tqdm(chapter_list, total=len(chapter_list)):
        chapters.append(download_royalroad_chapter(session, url, title))
        time.sleep(0.5)

    return chapters


# ----- Output -----

def _write_markdown(config, book_name, chapters, split):
    """Writes an ordered list of chapters to a pandoc-ready Markdown file."""
    if split:
        book_title = f"output/{config['title']} - {book_name}.md"
    else:
        book_title = f"{config['title']}.md"

    with open(book_title, "w", encoding='utf-8') as f:
        f.write(f"% {config['title']} ({book_name})\n")
        f.write(f"% {config['author']}\n\n")

        for chapter in chapters:
            f.write(f"# {chapter.title}\n\n")
            f.write(chapter.text)


def write_book(config, book="all", split=False):
    book_name = "all books" if book == "all" else f"Book {book}"

    if config['source'] == 'royalroad':
        # Royal Road has no per-book download granularity here; always fetch the
        # full work (the splitting feature is WordPress-only).
        chapters = download_royalroad_book(config)
        _write_markdown(config, "all books", chapters, split)
        return

    with ProcessPoolExecutor() as pool:
        links = list(download_contents(config, book))
        futures = {}
        for link in links:
            future = pool.submit(download_chapter, link)
            futures[future] = link

        downloaded = {}
        for future in tqdm(as_completed(futures), total=len(futures)):
            downloaded[futures[future]] = future.result()

    chapters = [downloaded[link] for link in links]
    _write_markdown(config, book_name, chapters, split)


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
            # The per-book split feature only applies to WordPress-sourced books;
            # Royal Road books are written as a single combined file.
            if config['source'] != 'wordpress':
                print('Downloading', config['title'])
                write_book(config, split=True)
                continue

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
