# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from agent_flow import get_research_graph
import config
import datetime
import os
import json

from google.cloud import firestore, tasks_v2
from google.protobuf import timestamp_pb2

app = Flask(__name__)

# --- Configuration ---
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
QUEUE_LOCATION = "us-central1"  # Or your task queue location
QUEUE_ID = "research-jobs-queue" # Name your queue in Cloud Tasks
RESEARCH_SERVICE_URL = os.environ.get("CLOUD_RUN_SERVICE_URL") # URL of this service
FIRESTORE_COLLECTION = "research_jobs"

# --- Clients ---
# Initialize clients once
db = firestore.Client()
task_client = tasks_v2.CloudTasksClient()
graph = get_research_graph()

# --- CORS ---
CORS(app, resources={
    r"/start-research": {"origins": [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://gen-lang-client-0048564118.web.app"
    ]},
    # This internal endpoint doesn't need external CORS
    r"/run-research-job": {"origins": "*"}
})

# --- Endpoint 1: Start the Job (Called by Frontend) ---
@app.route('/start-research', methods=['POST'])
def start_research():
    try:
        data = request.json
        user_input = data.get('input')
        url_input = data.get('url')

        if not user_input:
            return jsonify({"error": "No company name provided"}), 400

        # 1. Create a job document in Firestore
        job_ref = db.collection(FIRESTORE_COLLECTION).document()
        job_id = job_ref.id
        job_data = {
            "id": job_id,
            "status": "pending",
            "input": user_input,
            "url": url_input,
            "steps_complete": [],
            "linkedin_data": None,
            "job_openings": None,
            "recent_news_summary": None,
            "error": None,
            "created_at": firestore.SERVER_TIMESTAMP
        }
        job_ref.set(job_data)

        # 2. Create a Cloud Task to run the job
        parent = task_client.queue_path(PROJECT_ID, QUEUE_LOCATION, QUEUE_ID)

        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{RESEARCH_SERVICE_URL}/run-research-job", # This service calls itself
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"job_id": job_id}).encode('utf-8'),
                "oidc_token": {
                    "service_account_email": os.environ.get("SERVICE_ACCOUNT_EMAIL"), # e.g., 373126702591-compute@...
                    "audience": RESEARCH_SERVICE_URL
                }
            },
            # Set a long timeout for the task
            "dispatch_deadline": {"seconds": 1800} # 30 min
        }

        task_client.create_task(parent=parent, task=task)

        # 3. Return the job ID immediately
        return jsonify({"job_id": job_id}), 202 # 202 Accepted

    except Exception as e:
        print(f"[TRACE] Error in /start-research: {e}")
        return jsonify({"error": str(e)}), 500


# --- Endpoint 2: Run the Job (Called by Cloud Tasks) ---
@app.route('/run-research-job', methods=['POST'])
def run_research_job():
    try:
        data = request.json
        job_id = data.get('job_id')

        if not job_id:
            return "No job_id provided", 400

        print(f"[TRACE] Running job: {job_id}")

        job_ref = db.collection(FIRESTORE_COLLECTION).document(job_id)
        job_snapshot = job_ref.get()

        if not job_snapshot.exists:
            print(f"Job {job_id} not found.")
            return "Job not found", 404

        job_data = job_snapshot.to_dict()

        inputs = {
            "initial_input": job_data.get("input"),
            "provided_url": job_data.get("url")
        }

        # Use .stream() instead of .invoke()
        steps_complete = []
        final_state = None

        for step in graph.stream(inputs):
            # The key is the name of the node that just ran
            step_name = list(step.keys())[0]
            steps_complete.append(step_name)

            # Update Firestore with the completed step
            job_ref.update({
                "status": "running",
                "steps_complete": steps_complete
            })

            # Capture the final state
            final_state = step[step_name]

        # 3. Mark job as complete with the new structure
        # Save LinkedIn data as-is, and LLM-generated fields separately
        update_data = {
            "status": "complete",
            "completed_at": firestore.SERVER_TIMESTAMP
        }
        
        # Save main data
        if final_state:
            if 'linkedin_data' in final_state:
                update_data['linkedin_data'] = final_state['linkedin_data']
            if 'job_openings' in final_state:
                update_data['job_openings'] = final_state['job_openings']
            if 'recent_news_summary' in final_state:
                update_data['recent_news_summary'] = final_state['recent_news_summary']
            
            # Optional: Save raw debug data
            if 'careers_page_content' in final_state:
                update_data['raw_careers_markdown'] = final_state['careers_page_content']
            if 'recent_news' in final_state:
                update_data['raw_news_data'] = final_state['recent_news']
        
        job_ref.update(update_data)

        print(f"[TRACE] Job complete: {job_id}")
        return "Job completed successfully", 200

    except Exception as e:
        # Handle errors by updating Firestore
        job_id = request.json.get('job_id')
        if job_id:
            db.collection(FIRESTORE_COLLECTION).document(job_id).update({
                "status": "error",
                "error": str(e)
            })
        print(f"[TRACE] Job failed: {job_id}. Error: {e}")
        return "Job failed", 200 # Return 200 so Cloud Tasks doesn't retry


if __name__ == '__main__':
    # Use the port from config
    app.run(port=config.FLASK_PORT, debug=True)
