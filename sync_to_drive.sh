#!/bin/bash
# Sync local changes back to Google Drive

# Load .env variables line-by-line to safely handle spaces and quotes
if [ -f .env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    # Ignore comments and empty lines
    if [[ ! "$line" =~ ^# ]] && [[ "$line" =~ = ]]; then
      key=$(echo "$line" | cut -d= -f1 | xargs)
      val=$(echo "$line" | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
      export "$key"="$val"
    fi
  done < .env
fi

if [ -z "$GOOGLE_DRIVE_PATH" ]; then
  echo "GOOGLE_DRIVE_PATH is not set in .env. Skipping backup."
  exit 0
fi

rsync -av --delete --exclude="chrome-profile" --exclude=".git" "./" "$GOOGLE_DRIVE_PATH/"
echo "Sync to Google Drive completed successfully."
