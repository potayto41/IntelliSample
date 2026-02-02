"""
Test script for add-site (single) and upload-csv (bulk) endpoints.
Tests the Sample Dispenser API with PostgreSQL backend.
"""

import requests
import json
import csv
import io
import time

BASE_URL = "http://127.0.0.1:8080"

print("=" * 60)
print("SAMPLE DISPENSER API TESTS (PostgreSQL Backend)")
print("=" * 60)

# Test 1: Add single site
print("\n[TEST 1] Adding single site...")
single_site = {
    "website_url": "https://www.figma.com"
}

response = requests.post(f"{BASE_URL}/add-site", data=single_site)
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")

# Test 2: Add another single site
print("\n[TEST 2] Adding second site...")
single_site_2 = {
    "website_url": "https://www.webflow.com"
}

response = requests.post(f"{BASE_URL}/add-site", data=single_site_2)
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")

# Test 3: Bulk CSV upload
print("\n[TEST 3] Bulk CSV upload (5 sites)...")

# Create a CSV file in memory
csv_content = """website_url
https://www.notion.so
https://www.framer.com
https://www.bubble.io
https://www.wix.com
https://www.squarespace.com
"""

files = {
    "file": ("sites.csv", csv_content, "text/csv")
}

response = requests.post(f"{BASE_URL}/upload-csv", files=files)
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")

# Test 4: Search to see enriched data
print("\n[TEST 4] Searching for sites...")
response = requests.get(f"{BASE_URL}/search", params={"q": "webflow"})
if response.status_code == 200:
    print(f"Status: {response.status_code}")
    print(f"✓ Search working (page returned)")
else:
    print(f"Status: {response.status_code}")

# Test 5: Get suggestions
print("\n[TEST 5] Getting autocomplete suggestions...")
response = requests.get(f"{BASE_URL}/api/suggestions", params={"q": "web"})
print(f"Status: {response.status_code}")
if response.status_code == 200:
    print(f"Suggestions: {json.dumps(response.json(), indent=2)}")

print("\n" + "=" * 60)
print("TESTS COMPLETE - Check responses above")
print("=" * 60)
