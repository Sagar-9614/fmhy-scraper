name: Auto Update FMHY Data

on:
  schedule:
    # প্রতিদিন রাত ১২টায় স্বয়ংক্রিয়ভাবে রান হবে (Cron Job)
    - cron: '0 0 * * *'
  workflow_dispatch: # ম্যানুয়ালি এক ক্লিকে রান করার বাটন

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.x'

      - name: Run Scraper
        run: python parser.py

      - name: Commit and Push Clean Data
        run: |
          git config --global user.name 'GitHub Action Bot'
          git config --global user.email 'action@github.com'
          git add fmhy_clean_data.json
          git commit -m "Auto-updated clean FMHY data" || exit 0
          git push
