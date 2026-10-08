import json
import httpx
from bs4 import BeautifulSoup

def probe_greenhouse():
    # Test canonical and gitlab
    boards = ["canonical", "automattic"]
    all_jobs = []
    
    with httpx.Client(timeout=15.0) as client:
        for b in boards:
            url = f"https://boards-api.greenhouse.io/v1/boards/{b}/jobs?content=true"
            print(f"Fetching Greenhouse board: {b} -> {url}")
            r = client.get(url)
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                jobs = data.get("jobs", [])
                print(f"Discovered {len(jobs)} jobs for {b}")
                for j in jobs:
                    j["company"] = b.title()
                all_jobs.extend(jobs)
                
        test_sample = all_jobs[:10]
        verified_results = []
        
        for idx, job in enumerate(test_sample, 1):
            job_id = job.get("id")
            title = job.get("title")
            comp = job.get("company")
            loc = job.get("location", {}).get("name", "Remote")
            apply_url = job.get("absolute_url")
            raw_content = job.get("content", "")
            
            # Parse HTML content
            soup = BeautifulSoup(raw_content, "html.parser")
            clean_jd = soup.get_text("\n", strip=True)
            
            is_valid = bool(title and len(clean_jd) > 200)
            verified_results.append({
                "job_id": str(job_id),
                "url": apply_url,
                "title": title,
                "company": comp,
                "location": loc,
                "jd_len": len(clean_jd),
                "status": "VERIFIED" if is_valid else "PARTIAL",
            })
            print(f"--- [{idx}/10] Job ID: {job_id} ---")
            print(f"Title: {title}")
            print(f"Company: {comp} | Location: {loc}")
            print(f"JD Len: {len(clean_jd)} chars")
            print(f"Status: {'VERIFIED' if is_valid else 'PARTIAL'}")
            
        print("\n================ GREENHOUSE VERIFICATION SUMMARY ================")
        print(f"Tested: {len(test_sample)} jobs")
        success_count = sum(1 for r in verified_results if r["status"] == "VERIFIED")
        print(f"Verified successfully: {success_count}/{len(test_sample)} ({success_count/len(test_sample)*100:.1f}%)")
        with open("Interview_Coach_SRC_CODE/BE/scripts/crawler_investigation/greenhouse_verified.json", "w", encoding="utf-8") as f:
            json.dump(verified_results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    probe_greenhouse()
