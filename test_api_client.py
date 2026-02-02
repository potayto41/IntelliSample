from fastapi.testclient import TestClient
from app.main import app
import io

client = TestClient(app)

print("Running in-process API tests against app.main.app")

# Test 1: Add single site
print('\n[TEST 1] Add single site')
resp = client.post('/add-site', data={'website_url':'https://www.figma.com'})
print('Status:', resp.status_code)
try:
    print(resp.json())
except Exception:
    print(resp.text[:1000])

# Test 2: Add second site
print('\n[TEST 2] Add second site')
resp = client.post('/add-site', data={'website_url':'https://www.webflow.com'})
print('Status:', resp.status_code)
try:
    print(resp.json())
except Exception:
    print(resp.text[:1000])

# Test 3: Bulk CSV upload (5 sites)
print('\n[TEST 3] Bulk CSV upload')
csv_content = 'website_url\nhttps://www.notion.so\nhttps://www.framer.com\nhttps://www.bubble.io\nhttps://www.wix.com\nhttps://www.squarespace.com\n'
files = {'file': ('sites.csv', io.BytesIO(csv_content.encode('utf-8')), 'text/csv')}
resp = client.post('/upload-csv', files=files)
print('Status:', resp.status_code)
try:
    print(resp.json())
except Exception:
    print(resp.text[:1000])

# Test 4: Search
print('\n[TEST 4] Search for "webflow"')
resp = client.get('/search?q=webflow&page=1')
print('Status:', resp.status_code)
print('Length of response content:', len(resp.text))

# Test 5: Suggestions
print('\n[TEST 5] Suggestions for "web"')
resp = client.get('/api/suggestions?q=web')
print('Status:', resp.status_code)
try:
    print(resp.json())
except Exception:
    print(resp.text[:1000])

print('\nIn-process tests completed')
