import urllib.request
import json
import re

API_URL = "https://api.github.com/repos/fmhy/FMHYEdit/contents/docs"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github.v3+json"}
LINK_REGEX = re.compile(r'\[([^\]]+)\]\((https?://[^\s\)]+)\)(?:\s*[-–—:]?\s*(.*))?')

def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

def clean_category_name(filename):
    return filename.replace(".md", "").replace("-", " ").replace("_", " ").title()

def clean_description(desc):
    if not desc:
        return ""
    cleaned = re.sub(r'[\{\[]([^\]\}]+)[\}\]]\([^\)]+\)', r'\1', desc)
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    cleaned = cleaned.replace("*", "").replace("`", "").strip()
    return re.sub(r'^[–—\-:\s]+', '', cleaned).strip()

def parse_lines(lines, category_name):
    items = []
    current_sub = category_name
    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue
        if trimmed.startswith("#"):
            sub = trimmed.replace("#", "").strip()
            if sub and "table of contents" not in sub.lower():
                current_sub = sub
            continue
        m = LINK_REGEX.search(trimmed)
        if m:
            title = m.group(1).strip()
            link = m.group(2).strip()
            desc = clean_description(m.group(3) or "")
            if "reddit.com" not in link and "github.com/fmhy" not in link and "Back to" not in title:
                items.append({
                    "title": title,
                    "url": link,
                    "description": desc,
                    "category": category_name,
                    "subcategory": current_sub
                })
    return items

def main():
    print("Fetching file list...")
    try:
        files_data = fetch_json(API_URL)
    except Exception as e:
        print(f"Error fetching repo: {e}")
        return

    output = []
    for item in files_data:
        name = item.get("name", "")
        raw_url = item.get("download_url")
        if item.get("type") != "file" or not name.endswith(".md"):
            continue
        if name.lower() in ["readme.md", "index.md", "snippets.md"]:
            continue

        category = clean_category_name(name)
        print(f"Scanning: {category}")
        try:
            req = urllib.request.Request(raw_url, headers=HEADERS)
            with urllib.request.urlopen(req) as resp:
                raw_text = resp.read().decode('utf-8')
            lines = raw_text.splitlines()
            output.extend(parse_lines(lines, category))
        except Exception as e:
            print(f"Error with {name}: {e}")

    with open("fmhy_clean_data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Completed! Total items: {len(output)}")

if __name__ == "__main__":
    main()
