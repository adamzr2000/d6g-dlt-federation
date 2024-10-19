#!/bin/bash

# Define the source directory (current directory)
SOURCE_DIR=$(pwd)

# Define the target directory
TARGET_ENV_DIR="../../config/dlt/"
TARGET_GENESIS_DIR="../../config/dlt/genesis/"

# Ensure the target directory exists
mkdir -p $TARGET_ENV_DIR
mkdir -p $TARGET_GENESIS_DIR

# Move bootnode.env
if [ -f "$SOURCE_DIR/bootnode.env" ]; then
  mv "$SOURCE_DIR/bootnode.env" "$TARGET_ENV_DIR"
  echo "Moved bootnode.env to $TARGET_ENV_DIR"
else
  echo "bootnode.env not found in $SOURCE_DIR"
fi

# Move all nodeX.env files
for file in $SOURCE_DIR/node*.env
do
  if [ -f "$file" ]; then
    mv "$file" "$TARGET_ENV_DIR"
    echo "Moved $(basename $file) to $TARGET_ENV_DIR"
  else
    echo "No nodeX.env files found in $SOURCE_DIR"
  fi
done

echo "All environment files have been moved."

# Move all .json files
for file in $SOURCE_DIR/*.json
do
  if [ -f "$file" ]; then
    mv "$file" "$TARGET_GENESIS_DIR"
    echo "Moved $(basename $file) to $TARGET_GENESIS_DIR"
  else
    echo "No .json files found in $SOURCE_DIR"
  fi
done

echo "All genesis_X_validators.json files have been moved."





 

