#!/usr/bin/zsh
for f in `seq 1 $1`; do
  echo "compiling Practical Guide to Evil - Book $f"
  pandoc -o "A Practical Guide to Evil - Book $f.epub" "A Practical Guide to Evil - Book $f.md"
done

for f in `seq 1 $2`; do
  echo "compiling Pale Lights - Book $f"
  pandoc -o "Pale Lights - Book $f.epub" "Pale Lights - Book $f.md"
done