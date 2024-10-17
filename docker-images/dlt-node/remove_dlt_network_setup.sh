#!/bin/bash

# Remove all directories named "nodeX"
for dir in node*; do
  if [ -d "$dir" ]; then
    echo "Removing directory: $dir"
    rm -rf "$dir"
  fi
done

# Remove all nodeX_start.sh files
for file in scripts/node*_start.sh; do
  if [ -f "$file" ]; then
    echo "Removing file: $file"
    rm -f "$file"
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

# Remove "bootnode_start.sh" file
file=scripts/bootnode_start.sh
if [ -f "$file" ]; then
  echo "Removing file: $file"
  rm -f "$file"
fi

# Remove ".json" files
file=scripts/*.json
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

