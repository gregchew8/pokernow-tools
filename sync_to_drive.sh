#!/bin/bash
# Sync local changes back to Google Drive

# Load .env variables to get GOOGLE_DRIVE_PATH
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

if [ -z "$GOOGLE_DRIVE_PATH" ]; then
  echo "GOOGLE_DRIVE_PATH is not set in .env. Skipping backup."
  exit 0
fi

rsync -av --delete --exclude="chrome-profile" --exclude=".git" "./" "$GOOGLE_DRIVE_PATH/"
echo "Sync to Google Drive completed successfully."
