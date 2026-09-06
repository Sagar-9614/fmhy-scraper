import os
import re
import sys
import json
import time
import requests
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

# কনফিগারেশন
REPO_API_URL = "https://api.github.com/repos/fmhy/FMHYEdit/contents"
RAW_BASE_URL = "https://raw.githubusercontent.com/fmhy/FMHYEdit/main/"
OUTPUT_FILE = "fmhy_clean_data.json"
CHECK_BROKEN_LINKS = False  # দ্রুত ডেটা পাওয়ার জন্য False রাখা ভালো
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/vnd.github+json",
}
if GITHUB_TOKEN:
    # GitHub Actions-এ GITHUB_TOKEN দিলে রেট-লিমিট অনেক বেড়ে যায় (60 -> 5000/ঘণ্টা)
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


def load_previous_urls():
    """আগের ডেটা থেকে লিংক লোড করে নতুন টুল সনাক্ত করার জন্য"""
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                old_data = json.load(f)
                return {item.get("url") for item in old_data if item.get("url")}
        except Exception as e:
            print(f"⚠️ আগের ফাইল পড়তে সমস্যা হয়েছে: {e}")
            return set()
    return set()


def extract_domain(url):
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def request_with_retry(method, url, **kwargs):
    """নেটওয়ার্ক এরর বা রেট-লিমিটে স্বয়ংক্রিয়ভাবে রিট্রাই করে"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            res = requests.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
            if res.status_code == 403 and "rate limit" in res.text.lower():
                wait = int(res.headers.get("Retry-After", 5))
                print(f"⏳ রেট লিমিট হিট হয়েছে, {wait} সেকেন্ড অপেক্ষা করা হচ্ছে...")
                time.sleep(wait)
                continue
            return res
        except requests.RequestException as e:
            print(f"⚠️ ({attempt}/{MAX_RETRIES}) রিকোয়েস্ট ব্যর্থ হয়েছে {url}: {e}")
            time.sleep(2 * attempt)
    return None


def check_link_status(url):
    """অনেক সার্ভার HEAD সাপোর্ট করে না, তাই ব্যর্থ হলে GET দিয়ে আবার চেষ্টা করে"""
    try:
        res = requests.head(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if res.status_code >= 400 or res.status_code == 405:
            res = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, stream=True, allow_redirects=True)
        return res.status_code >= 400
    except Exception:
        return True


def clean_markdown_text(text):
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'[*_`#]', '', text)
    return text.strip()


# GitHub-এর নতুন অ্যালার্ট সিনট্যাক্স (> [!TIP], > [!NOTE], > [!WARNING] ইত্যাদি) সনাক্তকরণ
ALERT_PATTERN = re.compile(r'^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]', re.IGNORECASE)

# চেকবক্স লিস্ট ("- [ ] [Title](url)") এবং সাধারণ বুলেট লিস্ট দুটোই সাপোর্ট করে
LINK_PATTERN = re.compile(
    r'^\s*[\*\-]\s*(?:\[[ xX]?\]\s*)?\[([^\]]+)\]\((https?://[^\)\s]+)\)(?:\s*-\s*(.*))?$'
)


def parse_markdown_content(md_text, category_name, old_urls):
    items = []
    current_subcategory = "General"
    lines = md_text.splitlines()

    for raw_line in lines:
        line_strip = raw_line.strip()

        # সাব-ক্যাটাগরি হেডার সনাক্তকরণ (## বা ###)
        if line_strip.startswith("## ") or line_strip.startswith("### "):
            header_title = line_strip.lstrip("#").strip()
            if header_title.lower() not in ["table of contents", "back to top"]:
                current_subcategory = header_title
            continue

        # টিপস ও গাইডলাইন সনাক্তকরণ (পুরাতন স্টাইল + GitHub-এর নতুন অ্যালার্ট সিনট্যাক্স)
        is_alert = bool(ALERT_PATTERN.match(line_strip))
        if "💡" in line_strip or line_strip.startswith("> **Note**") or line_strip.startswith("> 💡") or is_alert:
            tip_raw = ALERT_PATTERN.sub("", line_strip) if is_alert else line_strip
            tip_content = clean_markdown_text(tip_raw.lstrip(">").strip())
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

        # লিংক এক্সট্র্যাক্ট করা (* [Title](URL) - Description)
        match = LINK_PATTERN.match(line_strip)

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

    res = request_with_retry("GET", REPO_API_URL, headers=HEADERS)
    if res is None:
        print("❌ ক্যাটাগরি তালিকা আনা যায়নি (নেটওয়ার্ক সমস্যা)।")
        return categories

    if res.status_code != 200:
        print(f"❌ GitHub API এরর (status {res.status_code}): {res.text[:200]}")
        return categories

    files = res.json()
    if not isinstance(files, list):
        print("❌ অপ্রত্যাশিত API রেসপন্স পাওয়া গেছে, তালিকা তৈরি করা যায়নি।")
        return categories

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

    print(f"মোট ক্যাটাগরি পাওয়া গেছে: {len(categories)}")

    for cat_name, raw_url in categories:
        print(f"স্ক্র্যাপ করা হচ্ছে: {cat_name}...")
        res = request_with_retry("GET", raw_url, headers=HEADERS)
        if res is not None and res.status_code == 200:
            parsed_items = parse_markdown_content(res.text, cat_name, old_urls)
            all_extracted_data.extend(parsed_items)
        else:
            status = res.status_code if res is not None else "N/A"
            print(f"⚠️ '{cat_name}' আনতে ব্যর্থ (status: {status}), স্কিপ করা হলো।")

    if CHECK_BROKEN_LINKS and all_extracted_data:
        print("ডেড লিংক চেক করা হচ্ছে...")
        with ThreadPoolExecutor(max_workers=20) as executor:
            urls = [item["url"] for item in all_extracted_data if item["url"]]
            results = list(executor.map(check_link_status, urls))
            url_status_map = dict(zip(urls, results))

            for item in all_extracted_data:
                if item["url"] in url_status_map:
                    item["is_broken"] = url_status_map[item["url"]]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_extracted_data, f, ensure_ascii=False, indent=2)

    print(f"সম্পন্ন! মোট {len(all_extracted_data)}টি আইটেম {OUTPUT_FILE}-এ সংরক্ষিত হলো।")

    if not all_extracted_data:
        # কোনো ডেটা না পেলে workflow-কে ব্যর্থ হিসেবে চিহ্নিত করার জন্য
        print("⚠️ কোনো ডেটা পাওয়া যায়নি।")
        sys.exit(1)


if __name__ == "__main__":
    main()
