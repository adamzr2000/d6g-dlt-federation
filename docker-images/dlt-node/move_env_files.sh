#!/bin/bash

# Define the source directory (current directory)
SOURCE_DIR=$(pwd)

# Define the target directory
TARGET_DIR="../../config/dlt/"

# Ensure the target directory exists
mkdir -p $TARGET_DIR

# Move bootnode.env
if [ -f "$SOURCE_DIR/bootnode.env" ]; then
  mv "$SOURCE_DIR/bootnode.env" "$TARGET_DIR"
  echo "Moved bootnode.env to $TARGET_DIR"
else
  echo "bootnode.env not found in $SOURCE_DIR"
fi

# Move all nodeX.env files
for file in $SOURCE_DIR/node*.env
do
  if [ -f "$file" ]; then
    mv "$file" "$TARGET_DIR"
    echo "Moved $(basename $file) to $TARGET_DIR"
  else
    echo "No nodeX.env files found in $SOURCE_DIR"
  fi
done

echo "All environment files have been moved."

