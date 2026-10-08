import json
import re
import time
from bs4 import BeautifulSoup
import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def probe_linkedin():
    listing_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=Software%20Engineer&location=Vietnam&start=0"
    print(f"Fetching LinkedIn listing: {listing_url}")
    
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15.0) as client:
        resp = client.get(listing_url)
        print(f"Listing status: {resp.status_code}")
        soup = BeautifulSoup(resp.text, "html.parser")
        
        cards = soup.find_all("li")
        print(f"Discovered {len(cards)} job cards from LinkedIn listing.")
        
        jobs = []
        for c in cards:
            div_card = c.select_one("div[data-entity-urn]")
            link_el = c.select_one("a.base-card__full-link, a")
            title_el = c.select_one("h3.base-search-card__title, .job-search-card__title")
            comp_el = c.select_one("h4.base-search-card__subtitle, a.hidden-nested-link")
            loc_el = c.select_one(".job-search-card__location")
            
            job_id = None
            if div_card and div_card.get("data-entity-urn"):
                m = re.search(r"jobPosting:(\d+)", div_card["data-entity-urn"])
                if m:
                    job_id = m.group(1)
            if not job_id and link_el and link_el.get("href"):
                m = re.search(r"-(\d+)\?", link_el["href"]) or re.search(r"/(\d+)", link_el["href"])
                if m:
                    job_id = m.group(1)
                    
            if not job_id:
                continue
                
            jobs.append({
                "job_id": job_id,
                "title": title_el.get_text(strip=True) if title_el else "Software Engineer",
                "company": comp_el.get_text(strip=True) if comp_el else "Unknown",
                "location": loc_el.get_text(strip=True) if loc_el else "Vietnam",
                "original_link": link_el.get("href") if link_el else f"https://www.linkedin.com/jobs/view/{job_id}",
                "detail_api_url": f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}",
            })
            
        print(f"Valid parsed jobs: {len(jobs)}")
        test_sample = jobs[:10]
        verified_results = []
        
        for idx, job in enumerate(test_sample, 1):
            detail_url = job["detail_api_url"]
            print(f"\n--- [{idx}/10] Testing Detail: {job['title'][:40]} (ID: {job['job_id']}) ---")
            print(f"API URL: {detail_url}")
            try:
                time.sleep(0.5)
                det_resp = client.get(detail_url)
                if det_resp.status_code != 200:
                    print(f"FAILED: HTTP {det_resp.status_code}")
                    continue
                    
                det_soup = BeautifulSoup(det_resp.text, "html.parser")
                
                # Title
                h1 = det_soup.find("h1") or det_soup.find("h2")
                det_title = h1.get_text(strip=True) if h1 else job["title"]
                
                # Company
                comp = det_soup.select_one("a.topcard__org-name-link, .topcard__flavor, a[data-tracking-control-name*='company']")
                company = comp.get_text(strip=True) if comp else job["company"]
                
                # JD
                desc_el = det_soup.select_one(".show-more-less-html__markup, .description__text, .description")
                jd_text = desc_el.get_text("\n", strip=True) if desc_el else ""
                
                # Criteria list (Seniority, Employment type, Job function, Industries)
                criteria = {}
                for li in det_soup.select(".description__job-criteria-item"):
                    c_h = li.select_one(".description__job-criteria-subheader")
                    c_v = li.select_one(".description__job-criteria-text")
                    if c_h and c_v:
                        criteria[c_h.get_text(strip=True)] = c_v.get_text(strip=True)
                        
                is_valid = bool(det_title and len(jd_text) > 200)
                verified_results.append({
                    "job_id": job["job_id"],
                    "url": job["original_link"],
                    "detail_api_url": detail_url,
                    "title": det_title,
                    "company": company,
                    "criteria": criteria,
                    "jd_len": len(jd_text),
                    "status": "VERIFIED" if is_valid else "PARTIAL",
                })
                print(f"Verified Title: {det_title[:40]}")
                print(f"Company: {company}")
                print(f"Criteria: {criteria}")
                print(f"JD Len: {len(jd_text)} chars")
                print(f"Status: {'VERIFIED' if is_valid else 'PARTIAL'}")
            except Exception as e:
                print(f"ERROR: {e}")
                
        print("\n================ LINKEDIN VERIFICATION SUMMARY ================")
        print(f"Tested: {len(test_sample)} jobs")
        success_count = sum(1 for r in verified_results if r["status"] == "VERIFIED")
        print(f"Verified successfully: {success_count}/{len(test_sample)} ({success_count/len(test_sample)*100:.1f}%)")
        with open("Interview_Coach_SRC_CODE/BE/scripts/crawler_investigation/linkedin_verified.json", "w", encoding="utf-8") as f:
            json.dump(verified_results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    probe_linkedin()
