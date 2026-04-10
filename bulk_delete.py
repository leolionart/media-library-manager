import json
import urllib.request
import urllib.error
import time

def call_api(path, method="GET", payload=None):
    url = f"http://localhost:9988{path}"
    headers = {"Content-Type": "application/json"}
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"Error calling {url}: {e.code} {e.read().decode()}")
        return None
    except Exception as e:
        print(f"Error calling {url}: {str(e)}")
        return None

def main():
    print("Fetching issues...")
    state = call_api("/api/state")
    if not state:
        return

    issues = state.get("path_repair_report", {}).get("issues", [])
    if not issues:
        print("No issues found.")
        return

    print(f"Found {len(issues)} issues. Starting bulk remove and block...")
    
    for issue in issues:
        provider = issue.get("provider")
        item_id = issue.get("item_id")
        title = issue.get("title")
        
        print(f"Processing: {title} ({provider} ID: {item_id})")
        
        result = call_api("/api/path-repair/delete", method="POST", payload={
            "provider": provider,
            "item_id": item_id,
            "add_import_exclusion": True
        })
        
        if result and result.get("status") == "success":
            print(f"  - Successfully removed and blocked.")
        else:
            print(f"  - Failed to process.")
        
        # Small delay to avoid overwhelming the server
        time.sleep(0.5)

    print("Bulk processing completed.")

if __name__ == "__main__":
    main()
