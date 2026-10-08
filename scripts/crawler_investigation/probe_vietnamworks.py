import json
import re
import time
from bs4 import BeautifulSoup
import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
}

def probe_vietnamworks():
    print("Fetching listing from VietnamWorks search API: https://ms.vietnamworks.com/job-search/v1.0/search")
    payload = {
        "userId": 0,
        "query": "Software Engineer",
        "filter": [],
        "ranges": [],
        "order": [],
        "hitsPerPage": 15,
        "page": 0
    }
    
    with httpx.Client(timeout=15.0) as client:
        resp = client.post("https://ms.vietnamworks.com/job-search/v1.0/search", headers=API_HEADERS, json=payload)
        if resp.status_code != 200:
            print(f"Failed to fetch search API: {resp.status_code}")
            return
            
        data = resp.json()
        jobs = data.get("data", [])
        print(f"Discovered {len(jobs)} jobs from VietnamWorks search endpoint.")
        
        test_sample = jobs[:10]
        verified_results = []
        
        for idx, job in enumerate(test_sample, 1):
            job_id = job.get("jobId")
            job_title = job.get("jobTitle")
            company_name = job.get("companyName")
            detail_url = job.get("jobUrl")
            logo_url = job.get("companyLogo")
            salary = job.get("prettySalary")
            
            print(f"\n--- [{idx}/10] Testing Detail: {job_title[:40]} (ID: {job_id}) ---")
            print(f"URL: {detail_url}")
            
            try:
                time.sleep(0.3)
                det_resp = client.get(detail_url, headers=HEADERS)
                if det_resp.status_code != 200:
                    print(f"FAILED HTTP {det_resp.status_code}")
                    continue
                    
                html_content = det_resp.text
                
                # Extract Description
                desc = ""
                m_desc = re.search(r'jobDescription\\":\\"((?:(?!\\",\\").)*)\\"', html_content)
                if m_desc:
                    raw = m_desc.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")
                    desc = BeautifulSoup(raw, "html.parser").get_text("\n", strip=True)
                    
                # Extract Requirements
                req = ""
                m_req_ptr = re.search(r'jobRequirement\\":\\"\$([a-zA-Z0-9]+)\\"', html_content)
                if m_req_ptr:
                    ptr_id = m_req_ptr.group(1)
                    m_ptr_content = re.search(rf'{ptr_id}:T[0-9a-f]+,(.*?)(?:\\\\n|\",\[|$)', html_content)
                    if m_ptr_content:
                        raw_req = m_ptr_content.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")
                        req = BeautifulSoup(raw_req, "html.parser").get_text("\n", strip=True)
                if not req:
                    m_req = re.search(r'jobRequirement\\":\\"((?:(?!\\",\\").)*)\\"', html_content)
                    if m_req and not m_req.group(1).startswith("$"):
                        raw = m_req.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")
                        req = BeautifulSoup(raw, "html.parser").get_text("\n", strip=True)
                        
                total_jd_len = len(desc) + len(req)
                is_valid = bool(job_title and total_jd_len > 150)
                
                verified_results.append({
                    "job_id": job_id,
                    "url": detail_url,
                    "title": job_title,
                    "company": company_name,
                    "logo_url": logo_url,
                    "salary": salary,
                    "jd_len": total_jd_len,
                    "desc_len": len(desc),
                    "req_len": len(req),
                    "status": "VERIFIED" if is_valid else "PARTIAL",
                })
                print(f"Title: {job_title[:40]}")
                print(f"Company: {company_name}")
                print(f"JD Total Len: {total_jd_len} (Desc: {len(desc)}, Req: {len(req)})")
                print(f"Status: {'VERIFIED' if is_valid else 'PARTIAL'}")
            except Exception as e:
                print(f"ERROR: {e}")
                
        print("\n================ VIETNAMWORKS VERIFICATION SUMMARY ================")
        print(f"Tested: {len(test_sample)} jobs")
        success_count = sum(1 for r in verified_results if r["status"] == "VERIFIED")
        print(f"Verified successfully: {success_count}/{len(test_sample)} ({success_count/len(test_sample)*100:.1f}%)")
        with open("Interview_Coach_SRC_CODE/BE/scripts/crawler_investigation/vietnamworks_verified.json", "w", encoding="utf-8") as f:
            json.dump(verified_results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    probe_vietnamworks()
