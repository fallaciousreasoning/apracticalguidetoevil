#!/usr/bin/zsh

if [ -z "$1" ]; then
  echo "Usage: ./compile_epub.sh <First x Practical Guide to Evil Books> <First x Pale Lights Books>"
fi

if [ $1 -ge 0 ]; then
  for f in `seq 1 $1`; do
    echo "compiling Practical Guide to Evil - Book $f"
    pandoc -o "output/A Practical Guide to Evil - Book $f.epub" "output/A Practical Guide to Evil - Book $f.md"
  done
fi

if [ $2 -ge 0 ]; then
  for f in `seq 1 $2`; do
    echo "compiling Pale Lights - Book $f"
    pandoc -o "output/Pale Lights - Book $f.epub" "output/Pale Lights - Book $f.md"
  done

  # Really hacky but don't know how else to 'automate' this
  if [ $2 -ge 1 ]; then
    mv "output/Pale Lights - Book 1.epub" "output/Pale Lights - Book I: Lost Things.epub"
  fi
  if [ $2 -ge 2 ]; then
    mv "output/Pale Lights - Book 2.epub" "output/Pale Lights - Book 2: Good Treasons.epub"
  fi
fi