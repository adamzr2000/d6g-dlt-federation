#!/bin/bash

# Check if commit message is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <commit_message>"
  exit 1
fi

# Commit message
COMMIT_MESSAGE="$1"

git checkout main

# Add all changes
git add --all

# Commit with the provided message
git commit -m "$COMMIT_MESSAGE"

# Push to the origin
git push origin main

echo "Changes have been pushed to the repository."

