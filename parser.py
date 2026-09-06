import os
import re
import json
import requests
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

# কনফিগারেশন
REPO_API_URL = "https://api.github.com/repos/fmhy/FMHYEdit/contents"
RAW_BASE_URL = "https://raw.githubusercontent.com/fmhy/FMHYEdit/main/"
OUTPUT_FILE = "fmhy_clean_data.json"
CHECK_BROKEN_LINKS = False

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def load_previous_urls():
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                old_data = json.load(f)
                return {item.get("url") for item in old_data if item.get("url")}
        except Exception:
            return set()
    return set()

def extract_domain(url):
    try:
        host = urlparse(url).netloc
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""

def check_link_status(url):
    try:
        res = requests.head(url, headers=HEADERS, timeout=4, allow_redirects=True)
        return res.status_code >= 400
    except Exception:
        return True

def clean_markdown_text(text):
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'[*_`#]', '', text)
    return text.strip()

def parse_markdown_content(md_text, category_name, old_urls):
    items = []
    current_subcategory = "General"
    lines = md_text.splitlines()

    for line in lines:
        line_strip = line.strip()

        if line_strip.startswith("## ") or line_strip.startswith("### "):
            header_title = line_strip.lstrip("#").strip()
            if header_title.lower() not in ["table of contents", "back to top"]:
                current_subcategory = header_title
            continue

        if "💡" in line_strip or line_strip.startswith("> **Note**") or line_strip.startswith("> 💡"):
            tip_content = clean_markdown_text(line_strip.lstrip(">").strip())
            if len(tip_content) > 10:
                items.append({
                    "title": "💡 Tip & Notice",
                    "url": "",
                    "description": tip_content,
                    "category": category_name,
                    "subcategory": current_subcategory,
                    "domain": "",
                    "is_new": False,
                    "is_broken": False,
                    "is_tip": True
                })
            continue

        link_pattern = r'^\s*[\*\-]\s*\[([^\]]+)\]\((https?://[^\)]+)\)(?:\s*-\s*(.*))?$'
        match = re.match(link_pattern, line_strip)

        if match:
            title = match.group(1).strip()
            url = match.group(2).strip()
            desc = match.group(3).strip() if match.group(3) else ""

            desc = clean_markdown_text(desc)
            is_new = url not in old_urls if old_urls else False

            items.append({
                "title": title,
                "url": url,
                "description": desc,
                "category": category_name,
                "subcategory": current_subcategory,
                "domain": extract_domain(url),
                "is_new": is_new,
                "is_broken": False,
                "is_tip": False
            })

    return items

def fetch_category_files():
    excluded_files = {"README.md", "index.md", "base.md"}
    categories = []

    res = requests.get(REPO_API_URL, headers=HEADERS)
    if res.status_code == 200:
        files = res.json()
        for f in files:
            name = f.get("name", "")
            if name.endswith(".md") and name not in excluded_files:
                cat_name = name.replace(".md", "").replace("Guide", "").replace("Piracy", "").strip()
                categories.append((cat_name, f.get("download_url", RAW_BASE_URL + name)))
    return categories

def main():
    old_urls = load_previous_urls()
    categories = fetch_category_files()
    all_extracted_data = []

    print(f"Total categories found: {len(categories)}")

    for cat_name, raw_url in categories:
        print(f"Scraping: {cat_name}...")
        res = requests.get(raw_url, headers=HEADERS)
        if res.status_code == 200:
            parsed_items = parse_markdown_content(res.text, cat_name, old_urls)
            all_extracted_data.extend(parsed_items)

    if CHECK_BROKEN_LINKS and all_extracted_data:
        print("Checking for dead links...")
        with ThreadPoolExecutor(max_workers=20) as executor:
            urls = [item["url"] for item in all_extracted_data if item["url"]]
            results = list(executor.map(check_link_status, urls))
            url_status_map = dict(zip(urls, results))

            for item in all_extracted_data:
                if item["url"] in url_status_map:
                    item["is_broken"] = url_status_map[item["url"]]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_extracted_data, f, ensure_ascii=False, indent=2)

    print(f"Complete! Total {len(all_extracted_data)} items saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
