#!/usr/bin/env python3
"""
Script to clean up service account's Google Drive storage
"""

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import os

def cleanup_service_account_drive():
    """Clean up files from service account's Drive"""
    load_dotenv()
    
    credentials_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'google_credentials.json')
    
    # Setup credentials
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    
    creds = Credentials.from_service_account_file(credentials_file, scopes=scope)
    gc = gspread.authorize(creds)
    
    print("Listing files in service account's Drive...")
    
    # List all files
    try:
        files = gc.list_permissions()  # This will show files the service account can access
        print(f"Found {len(files)} accessible files")
        
        # You can also use the Drive API directly for more control
        from googleapiclient.discovery import build
        
        drive_service = build('drive', 'v3', credentials=creds)
        results = drive_service.files().list(
            pageSize=100,
            fields="nextPageToken, files(id, name, size, createdTime)"
        ).execute()
        
        items = results.get('files', [])
        print(f"\nFiles in service account's Drive:")
        total_size = 0
        
        for item in items:
            size = int(item.get('size', 0)) if item.get('size') else 0
            total_size += size
            print(f"- {item['name']} (ID: {item['id']}) - {size} bytes")
        
        print(f"\nTotal storage used: {total_size / (1024*1024):.2f} MB")
        
        # Optionally delete files (uncomment to enable)
        # for item in items:
        #     if input(f"Delete '{item['name']}'? (y/N): ").lower() == 'y':
        #         drive_service.files().delete(fileId=item['id']).execute()
        #         print(f"Deleted: {item['name']}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    cleanup_service_account_drive()