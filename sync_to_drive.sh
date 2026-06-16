#!/bin/bash
# Sync local changes back to Google Drive
rsync -av --delete --exclude="chrome-profile" --exclude=".git" "/Users/gregchew/pokernow/" "/Users/gregchew/Library/CloudStorage/GoogleDrive-gregchew@gmail.com/My Drive/pokernow/"
echo "Sync to Google Drive completed successfully."
