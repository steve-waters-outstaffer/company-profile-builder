#!/usr/bin/env python3
"""
Standalone script to test Firecrawl extract API using raw API calls and polling.
Usage: python test_firecrawl.py <url>
"""

import sys
import json
import os
import requests  # We will use 'requests' for raw API calls
import time
import traceback

def test_extract(url):
    """
    Submits an extract job, then polls for the 'completed' status.
    """

    api_key = "fc-fead785e824749e296a6e1aeca02ba34"
    if not api_key:
        print("ERROR: FIRECRAWL_API_KEY environment variable not set")
        print("Please set it: export FIRECRAWL_API_KEY='fc-...'")
        sys.exit(1)

    print(f"\n🔥 Starting raw Firecrawl extract for: {url}\n")

    # This is the schema from your successful curl command
    schema = {
        "type": "object",
        "properties": {
            "jobs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "location": {"type": "string"},
                        "url": {"type": "string"}
                    },
                    "required": ["title", "location"]
                }
            }
        },
        "required": ["jobs"]
    }

    # The prompt from your curl command
    prompt = "Extract all job postings with title, location, and URL"

    # --- STEP 1: POST to start the job ---
    post_url = "https://api.firecrawl.dev/v2/extract"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "urls": [url],
        "prompt": prompt,
        "schema": schema
    }

    job_id = None
    try:
        print(f"⏳ Submitting job to {post_url}...")
        response = requests.post(post_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # Raise an error for bad status codes

        post_data = response.json()
        job_id = post_data.get('id')

        if not job_id:
            print("❌ Error: API did not return a 'id' in the response.")
            print(json.dumps(post_data, indent=2))
            sys.exit(1)

        print(f"✅ Job submitted successfully! Job ID: {job_id}")

    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error submitting job: {e}")
        if e.response:
            print(f"Response Body: {e.response.text}")
        traceback.print_exc()
        sys.exit(1)

    # --- STEP 2: GET to poll for results ---
    get_url = f"https://api.firecrawl.dev/v2/extract/{job_id}"
    get_headers = {"Authorization": f"Bearer {api_key}"}

    max_retries = 20  # 20 * 5s = 100s timeout
    for attempt in range(max_retries):
        print(f"\nPolling attempt {attempt + 1}/{max_retries}...")
        try:
            response = requests.get(get_url, headers=get_headers)
            response.raise_for_status()

            status_data = response.json()
            status = status_data.get('status')

            print(f"Current status: {status}")

            if status == 'completed':
                print("\n🎉 Job completed!")
                print("=" * 80)
                print("Final Data:")
                print(json.dumps(status_data.get('data'), indent=2))
                print("=" * 80)

                # Final check on the actual jobs
                if status_data.get('data') and status_data['data'].get('jobs'):
                    print(f"📊 Successfully found {len(status_data['data']['jobs'])} jobs.")
                else:
                    print("⚠️  Job completed but 'jobs' array was empty or missing in the data.")

                sys.exit(0) # Success

            elif status == 'failed' or status == 'cancelled':
                print(f"\n❌ Job {status}. Halting.")
                print(json.dumps(status_data, indent=2))
                sys.exit(1)

            # If status is 'processing' or anything else, wait and retry
            time.sleep(5)

        except requests.exceptions.RequestException as e:
            print(f"\n❌ Error polling job status: {e}")
            if e.response:
                print(f"Response Body: {e.response.text}")
            time.sleep(5) # Wait before retrying on error

    print("\n❌ Job timed out after 100s. Exiting.")
    sys.exit(1)


if __name__ == '__main__':
    # Make sure you set the env var first:
    # export FIRECRAWL_API_KEY='fc-...'

    if len(sys.argv) != 2:
        print("Usage: python test_firecrawl.py <url>")
        print("Example: python test_firecrawl.py https://jobs.outstaffer.com/")
        sys.exit(1)

    test_extract(sys.argv[1])