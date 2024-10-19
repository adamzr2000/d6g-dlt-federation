#!/bin/bash

# Remove all directories named "nodeX"
for dir in node*; do
  if [ -d "$dir" ]; then
    echo "Removing directory: $dir"
    rm -rf "$dir"
  fi
done

# Remove the "bootnode" directory if it exists
if [ -d "bootnode" ]; then
  echo "Removing directory: bootnode"
  rm -rf "bootnode"
fi

# Remove the "logs" directory if it exists
if [ -d "logs" ]; then
  echo "Removing directory: logs"
  rm -rf "logs"
fi

# Remove ".json" files
file=./*.json
for f in $file; do
  rm -f "$f"
done

# Remove the ".env" files
for file in node*.env; do
  if [ -f "$file" ]; then
    echo "Removing file: $file"
    rm -f "$file"
  fi
done

# Remove "bootnode.env" file
file=bootnode.env
if [ -f "$file" ]; then
  echo "Removing file: $file"
  rm -f "$file"
fi

echo "Cleanup complete."

