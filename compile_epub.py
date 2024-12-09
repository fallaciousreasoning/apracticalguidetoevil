import re
import pypandoc
from os import listdir


# just compile every .md file into .epub
FILENAME_REGEX = ".*.md"

try:
    files = listdir("output/")
except FileNotFoundError:
    print("No output directory")
    exit(-1)


md_files = []
for filename in files:
    if re.search(FILENAME_REGEX, filename):
        md_files.append(filename)

if len(md_files) == 0:
    print("No .md files found in output directory")

for filename in md_files:
    print(f"Converting '{filename}' to '{filename[:-3]}.epub'")
    output = pypandoc.convert_file("output/" + filename, "epub", outputfile="output/" + filename[:-3] + ".epub")

