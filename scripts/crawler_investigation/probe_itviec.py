import json
import re
import time
from bs4 import BeautifulSoup
import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def probe_itviec():
    listing_url = "https://itviec.com/it-jobs"
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15.0) as client:
        print(f"Fetching ITviec listing: {listing_url}")
        resp = client.get(listing_url)
        print(f"Listing status: {resp.status_code}")
        soup = BeautifulSoup(resp.text, "html.parser")
        
        cards = soup.select(".job-card")
        print(f"Total .job-card elements found: {len(cards)}")
        
        jobs = []
        for card in cards:
            job_key = card.get("data-job-key")
            slug = card.get("data-search--job-selection-job-slug-value")
            title_el = card.select_one("h3 a, .job-card__title a, a[href*='/it-jobs/']")
            
            if not slug and title_el and title_el.get("href"):
                m = re.search(r"/it-jobs/([^/?]+)", title_el.get("href"))
                if m:
                    slug = m.group(1)
            
            if not slug:
                continue
                
            title = title_el.get_text(strip=True) if title_el else slug.replace("-", " ").title()
            detail_url = f"https://itviec.com/it-jobs/{slug}"
            
            jobs.append({
                "job_key": job_key or slug,
                "slug": slug,
                "title": title,
                "detail_url": detail_url
            })
            
        print(f"Discovered {len(jobs)} jobs from listing.")
        
        test_sample = jobs[:10]
        verified_results = []
        
        for idx, job in enumerate(test_sample, 1):
            url = job["detail_url"]
            print(f"\n--- [{idx}/10] Testing Detail: {job['title'][:40]} ---")
            print(f"URL: {url}")
            try:
                time.sleep(0.4)
                det_resp = client.get(url)
                if det_resp.status_code != 200:
                    print(f"FAILED: HTTP {det_resp.status_code}")
                    continue
                    
                det_soup = BeautifulSoup(det_resp.text, "html.parser")
                
                h1 = det_soup.find("h1")
                det_title = h1.get_text(strip=True) if h1 else ""
                
                comp_el = det_soup.select_one(".employer-name, .company-name")
                company = comp_el.get_text(strip=True) if comp_el else "Unknown"
                
                paragraphs = det_soup.select(".job-details__paragraph, .paragraph")
                jd_text = "\n\n".join(p.get_text("\n", strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)
                
                is_valid = bool(det_title and len(jd_text) > 200)
                verified_results.append({
                    "job_id": job["slug"],
                    "url": url,
                    "title": det_title,
                    "company": company,
                    "jd_len": len(jd_text),
                    "status": "VERIFIED" if is_valid else "PARTIAL",
                })
                print(f"Verified Title: {det_title[:40]}")
                print(f"Company: {company}")
                print(f"JD Length: {len(jd_text)} chars")
                print(f"Status: {'VERIFIED' if is_valid else 'PARTIAL'}")
            except Exception as e:
                print(f"ERROR: {e}")
                
        print("\n================ ITVIEC VERIFICATION SUMMARY ================")
        print(f"Tested: {len(test_sample)} jobs")
        success_count = sum(1 for r in verified_results if r["status"] == "VERIFIED")
        print(f"Verified successfully: {success_count}/{len(test_sample)} ({success_count/len(test_sample)*100:.1f}%)")
        with open("Interview_Coach_SRC_CODE/BE/scripts/crawler_investigation/itviec_verified.json", "w", encoding="utf-8") as f:
            json.dump(verified_results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    probe_itviec()
