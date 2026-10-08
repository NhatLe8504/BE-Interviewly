import json
import re
import time
from bs4 import BeautifulSoup
import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def probe_vng():
    listing_url = "https://career.vng.com.vn/vi/tim-kiem-viec-lam"
    print(f"Fetching VNG listing: {listing_url}")
    
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15.0) as client:
        resp = client.get(listing_url)
        print(f"Listing status: {resp.status_code}")
        
        soup = BeautifulSoup(resp.text, "html.parser")
        next_data = soup.find("script", id="__NEXT_DATA__")
        if not next_data or not next_data.string:
            print("No __NEXT_DATA__ found!")
            return
            
        data = json.loads(next_data.string)
        jobs = data.get("props", {}).get("pageProps", {}).get("jobs", [])
        print(f"Discovered {len(jobs)} live jobs from VNG search.")
        
        test_sample = jobs[:10]
        verified_results = []
        
        for idx, job in enumerate(test_sample, 1):
            slug = job.get("slug")
            listing_title = job.get("title")
            detail_url = f"https://career.vng.com.vn/tim-kiem-viec-lam/chi-tiet/{slug}"
            
            print(f"\n--- [{idx}/10] Testing Detail: {listing_title[:40]} ---")
            print(f"URL: {detail_url}")
            try:
                time.sleep(0.3)
                det_resp = client.get(detail_url)
                if det_resp.status_code != 200:
                    print(f"FAILED: HTTP {det_resp.status_code}")
                    continue
                    
                det_soup = BeautifulSoup(det_resp.text, "html.parser")
                det_next_data = det_soup.find("script", id="__NEXT_DATA__")
                if not det_next_data or not det_next_data.string:
                    print("Detail has no __NEXT_DATA__")
                    continue
                    
                det_data = json.loads(det_next_data.string)
                job_data = det_data.get("props", {}).get("pageProps", {}).get("job_data", {})
                
                det_title = job_data.get("title") or listing_title
                job_id = str(job_data.get("job_id") or job.get("job_id") or slug)
                code = job_data.get("code") or ""
                location = job_data.get("location") or job.get("location") or "Việt Nam"
                department = job_data.get("department") or ""
                
                desc_html = job_data.get("description", "")
                req_html = job_data.get("requirement", "")
                
                desc_text = BeautifulSoup(desc_html, "html.parser").get_text("\n", strip=True) if desc_html else ""
                req_text = BeautifulSoup(req_html, "html.parser").get_text("\n", strip=True) if req_html else ""
                
                total_jd_len = len(desc_text) + len(req_text)
                is_valid = bool(det_title and total_jd_len > 150)
                
                verified_results.append({
                    "job_id": job_id,
                    "code": code,
                    "url": detail_url,
                    "title": det_title,
                    "company": "VNG Corporation",
                    "location": location,
                    "department": department,
                    "total_jd_len": total_jd_len,
                    "desc_len": len(desc_text),
                    "req_len": len(req_text),
                    "status": "VERIFIED" if is_valid else "PARTIAL",
                })
                print(f"Verified Title: {det_title[:40]}")
                print(f"Location: {location} | Code: {code}")
                print(f"JD Total Len: {total_jd_len} (Desc: {len(desc_text)}, Req: {len(req_text)})")
                print(f"Status: {'VERIFIED' if is_valid else 'PARTIAL'}")
            except Exception as e:
                print(f"ERROR: {e}")
                
        print("\n================ VNG CAREERS VERIFICATION SUMMARY ================")
        print(f"Tested: {len(test_sample)} jobs")
        success_count = sum(1 for r in verified_results if r["status"] == "VERIFIED")
        print(f"Verified successfully: {success_count}/{len(test_sample)} ({success_count/len(test_sample)*100:.1f}%)")
        with open("Interview_Coach_SRC_CODE/BE/scripts/crawler_investigation/vng_verified.json", "w", encoding="utf-8") as f:
            json.dump(verified_results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    probe_vng()
