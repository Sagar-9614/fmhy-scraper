import urllib.request
import json
import re

# FMHY-এর অফিশিয়াল রিপোজিটরি ফোল্ডারের GitHub API
API_URL = "https://api.github.com/repos/fmhy/FMHYEdit/contents/docs"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/vnd.github.v3+json"
}

regex = re.compile(r'\[([^\]]+)\]\((https?://[^\s\)]+)\)(?:\s*[-–—:]?\s*(.*))?')

def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

def clean_category_name(filename):
    # ফাইলের নামকে সুন্দর ক্যাটাগরির নামে রূপান্তর (যেমন: video-tools.md -> Video Tools)
    name = filename.replace(".md", "").replace("-", " ").replace("_", " ")
    return name.title()

def main():
    print("Fetching file list from FMHY repository...")
    try:
        files_data = fetch_json(API_URL)
    except Exception as e:
        print(f"Failed to fetch repository contents: {e}")
        return

    output = []
    
    # docs ফোল্ডারের প্রতিটি ফাইলে এক এক করে ঢোকা
    for item in files_data:
        # শুধুমাত্র .md ফাইলগুলো রিড করবে
        if item.get("type") == "file" and item.get("name", "").endswith(".md"):
            file_name = item["name"]
            raw_url = item.get("download_url")
            
            # অপ্রয়োজনীয় সাধারণ ফাইল বাদ দেওয়া
            if file_name.lower() in ["readme.md", "index.md", "snippets.md"]:
                continue

            category_name = clean_category_name(file_name)
            print(f"Scanning category: {category_name} ({file_name})...")

            try:
                req = urllib.request.Request(raw_url, headers=HEADERS)
                with urllib.request.urlopen(req) as resp:
                    lines = resp.read().decode('utf-8').splitlines()

                    current_subcategory = category_name
                    for line in lines:
                        trimmed = line.strip()

                        # সেকশন বা সাব-হেডিং ট্র্যাক করা (# Heading)
                        if trimmed.startswith("#"):
                            sub = trimmed.replace("#", "").strip()
                            if sub and "table of contents" not in sub.lower():
                                current_subcategory = sub
                            continue

                        # লিংক এবং ডেসক্রিপশন এক্সট্রাক্ট করা
                        match = regex.search(trimmed)
                        if match:
                            title = match.group(1).strip()
                            link = match.group(2).strip()
                            desc = match.group(3) or ""
                            desc = desc.strip().replace("*", "")

                            # অপ্রয়োজনীয় নেভিগেশন লিংক ফিল্টার করা
                            if "reddit.com" not in link and "github.com/fmhy" not in link and "Back to" not in title:
                                output.append({
                                    "title": title,
                                    "url": link,
                                    "description": desc,
                                    "category": category_name,
                                    "subcategory": current_subcategory
                                })
            except Exception as e:
                print(f"Error reading file {file_name}: {e}")

    # সম্পূর্ণ ডেটা সেভ করা
    with open("fmhy_clean_data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDone! Successfully gathered {len(output)} links across all categories.")

if __name__ == "__main__":
    main()
