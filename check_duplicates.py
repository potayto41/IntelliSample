import csv

urls = set()
duplicates = 0
with open('data_tools/sites_enriched.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        url = row.get('website_url', '').strip()
        if url in urls:
            duplicates += 1
        else:
            urls.add(url)
print(f'Total unique URLs: {len(urls)}, Duplicates: {duplicates}')
