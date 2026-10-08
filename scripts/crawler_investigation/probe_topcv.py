import json
import re
import time
from bs4 import BeautifulSoup
import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
}

def probe_topcv():
    listing_url = "https://www.topcv.vn/tim-viec-lam-software-engineering-cr257cb258"
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15.0) as client:
        print(f"Fetching listing: {listing_url}")
        resp = client.get(listing_url)
        print(f"Listing status: {resp.status_code}")
        soup = BeautifulSoup(resp.text, "html.parser")
        
        cards = soup.select(".job-item-search-result")
        print(f"Total .job-item-search-result cards found: {len(cards)}")
        
        extracted_jobs = []
        for card in cards:
            title_el = card.select_one("h3.title a, .title a")
            comp_el = card.select_one("a.company, a[href*='/cong-ty/']")
            sal_el = card.select_one(".title-salary")
            loc_el = card.select_one(".address")
            exp_el = card.select_one(".exp")
            
            if not title_el or not title_el.get("href"):
                continue
                
            href = title_el.get("href").strip()
            # Clean URL: strip query parameters
            clean_url = href.split("?")[0]
            m = re.search(r"/(\d+)\.html", clean_url)
            job_id = m.group(1) if m else None
            
            if not job_id:
                continue
                
            job_item = {
                "job_id": job_id,
                "title": title_el.get_text(strip=True),
                "company": comp_el.get_text(strip=True) if comp_el else "Unknown",
                "salary": sal_el.get_text(strip=True) if sal_el else "Thỏa thuận",
                "location": loc_el.get_text(strip=True) if loc_el else "",
                "experience": exp_el.get_text(strip=True) if exp_el else "",
                "detail_url": clean_url,
            }
            extracted_jobs.append(job_item)
            
        print(f"Extracted {len(extracted_jobs)} valid jobs from listing cards.")
        
        # Test first 10 jobs on detail page
        test_sample = extracted_jobs[:10]
        verified_results = []
        
        for idx, job in enumerate(test_sample, 1):
            detail_url = job["detail_url"]
            print(f"\n--- [{idx}/10] Testing Detail: {job['title'][:40]} (ID: {job['job_id']}) ---")
            print(f"URL: {detail_url}")
            try:
                time.sleep(0.3)
                det_resp = client.get(detail_url)
                if det_resp.status_code != 200:
                    print(f"FAILED: HTTP {det_resp.status_code}")
                    continue
                    
                det_soup = BeautifulSoup(det_resp.text, "html.parser")
                
                # Title
                h1 = det_soup.find("h1")
                det_title = h1.get_text(strip=True) if h1 else ""
                
                # Company
                comp_a = det_soup.find("a", href=lambda h: h and "/cong-ty/" in h)
                det_company = comp_a.get_text(strip=True) if comp_a else ""
                
                # Salary
                sal = det_soup.find(class_=lambda c: c and "salary" in c)
                det_salary = sal.get_text(strip=True) if sal else ""
                
                # Sections: Mo ta, Yeu cau, Quyen loi
                sections = {}
                for item in det_soup.find_all(class_=lambda c: c and "box-job-information-detail-item" in c):
                    title_elem = item.find(class_=lambda c: c and "title" in c)
                    text_elem = item.find(class_=lambda c: c and "text" in c)
                    if title_elem and text_elem:
                        heading = title_elem.get_text(strip=True)
                        content = text_elem.get_text("\n", strip=True)
                        sections[heading] = content
                        
                # Alternative selector if box-job-information-detail-item not found
                if not sections:
                    for section in det_soup.select(".job-description__item"):
                        stitle = section.select_one("h3, .job-description__item--title")
                        sbody = section.select_one(".job-description__item--content")
                        if stitle and sbody:
                            sections[stitle.get_text(strip=True)] = sbody.get_text("\n", strip=True)
                
                total_jd_len = sum(len(v) for v in sections.values())
                
                # Deadline / expiration
                deadline_elem = det_soup.find(class_=lambda c: c and "deadline" in c)
                deadline = deadline_elem.get_text(strip=True) if deadline_elem else "Chưa xác định"
                
                is_valid = bool(det_title and total_jd_len > 200)
                verified_results.append({
                    "job_id": job["job_id"],
                    "url": detail_url,
                    "title": det_title,
                    "company": det_company,
                    "salary": det_salary,
                    "deadline": deadline,
                    "sections_found": list(sections.keys()),
                    "total_jd_len": total_jd_len,
                    "status": "VERIFIED" if is_valid else "PARTIAL",
                })
                print(f"Title matched: {'YES' if job['title'] in det_title or det_title in job['title'] else 'CLOSE'}")
                print(f"Company: {det_company}")
                print(f"JD Length: {total_jd_len} chars across {len(sections)} sections")
                print(f"Status: {'VERIFIED' if is_valid else 'PARTIAL'}")
            except Exception as e:
                print(f"ERROR: {e}")
                
        print("\n================ TOPCV VERIFICATION SUMMARY ================")
        print(f"Tested: {len(test_sample)} jobs")
        success_count = sum(1 for r in verified_results if r["status"] == "VERIFIED")
        print(f"Verified successfully: {success_count}/{len(test_sample)} ({success_count/len(test_sample)*100:.1f}%)")
        with open("Interview_Coach_SRC_CODE/BE/scripts/crawler_investigation/topcv_verified.json", "w", encoding="utf-8") as f:
            json.dump(verified_results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    probe_topcv()
