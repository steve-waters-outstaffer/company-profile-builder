# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from agent_flow import get_research_graph
from logging_config import get_logger
import config
import datetime
import os
import json
import time

from google.cloud import firestore, tasks_v2
from google.protobuf import timestamp_pb2

logger = get_logger(__name__)

app = Flask(__name__)

# --- Configuration ---
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
QUEUE_LOCATION = "us-central1"
QUEUE_ID = "research-jobs-queue"
RESEARCH_SERVICE_URL = os.environ.get("CLOUD_RUN_SERVICE_URL")
FIRESTORE_COLLECTION = "research_jobs"
RESEARCH_TIMEOUT_SECONDS = 300  # 5 minutes hard timeout

# --- Clients ---
db = firestore.Client()
task_client = tasks_v2.CloudTasksClient()
graph = get_research_graph()

logger.info(f"[STARTUP] Initialized - Project: {PROJECT_ID}, Service URL: {RESEARCH_SERVICE_URL}, Timeout: {RESEARCH_TIMEOUT_SECONDS}s")

# --- CORS ---
CORS(app, resources={
    r"/start-research": {"origins": [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://gen-lang-client-0048564118.web.app"
    ]},
    r"/run-research-job": {"origins": "*"}
})

# --- Endpoint 1: Start the Job (Called by Frontend) ---
@app.route('/start-research', methods=['POST'])
def start_research():
    try:
        data = request.json
        company_name = data.get('company_name')
        url = data.get('url')
        url_type = data.get('url_type')  # 'website' or 'linkedin' or None
        
        logger.info(f"[START_RESEARCH] Request received | company: '{company_name}' | url: '{url}' | url_type: '{url_type}'")

        if not company_name:
            logger.error("[START_RESEARCH] FAILED - No company name provided")
            return jsonify({"error": "No company name provided"}), 400

        job_ref = db.collection(FIRESTORE_COLLECTION).document()
        job_id = job_ref.id
        
        logger.info(f"[START_RESEARCH] Created job | job_id: {job_id}")
        
        job_data = {
            "id": job_id,
            "status": "pending",
            "company_name": company_name,
            "url": url,
            "url_type": url_type,
            "steps_complete": [],
            "step_status": {},  # Track detailed step status
            "linkedin_data": None,
            "job_openings": None,
            "recent_news_summary": None,
            "client_brief": None,
            "error": None,
            "created_at": firestore.SERVER_TIMESTAMP
        }
        job_ref.set(job_data)
        logger.info(f"[START_RESEARCH] Job document saved | job_id: {job_id}")

        parent = task_client.queue_path(PROJECT_ID, QUEUE_LOCATION, QUEUE_ID)
        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{RESEARCH_SERVICE_URL}/run-research-job",
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"job_id": job_id}).encode('utf-8'),
                "oidc_token": {
                    "service_account_email": os.environ.get("SERVICE_ACCOUNT_EMAIL"),
                    "audience": RESEARCH_SERVICE_URL
                }
            },
            "dispatch_deadline": {"seconds": 1800}
        }
        task_client.create_task(parent=parent, task=task)
        logger.info(f"[START_RESEARCH] Cloud Task created | job_id: {job_id} | queue: {QUEUE_ID}")

        return jsonify({"job_id": job_id}), 202

    except Exception as e:
        logger.error(f"[START_RESEARCH] ERROR | exception: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/run-research-job', methods=['POST'])
def run_research_job():
    job_id = None
    start_time = time.time()
    
    try:
        data = request.json
        job_id = data.get('job_id')

        if not job_id:
            logger.error("[RUN_JOB] FAILED - No job_id provided")
            return "No job_id provided", 400

        logger.info(f"[RUN_JOB] Starting job | job_id: {job_id}")

        job_ref = db.collection(FIRESTORE_COLLECTION).document(job_id)
        job_snapshot = job_ref.get()

        if not job_snapshot.exists:
            logger.error(f"[RUN_JOB] FAILED - Job not found | job_id: {job_id}")
            return "Job not found", 404

        job_data = job_snapshot.to_dict()
        logger.info(f"[RUN_JOB] Job data loaded | job_id: {job_id} | company: '{job_data.get('company_name')}'")

        inputs = {
            "company_name": job_data.get("company_name"),
            "url": job_data.get("url"),
            "url_type": job_data.get("url_type"),
            "step_status": {}  # Initialize step status
        }

        steps_complete = []
        step_status = {}
        final_state = None
        timeout_hit = False

        logger.info(f"[RUN_JOB] Starting graph execution | job_id: {job_id}")

        # Stream through graph with timeout check
        for step in graph.stream(inputs):
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > RESEARCH_TIMEOUT_SECONDS:
                logger.warning(f"[RUN_JOB] TIMEOUT | job_id: {job_id} | elapsed: {elapsed:.1f}s | steps: {steps_complete}")
                timeout_hit = True
                break

            step_name = list(step.keys())[0]
            steps_complete.append(step_name)
            final_state = step[step_name]
            
            # Extract step status from final_state if available
            if final_state and 'step_status' in final_state:
                step_status = final_state['step_status']
            
            logger.info(f"[RUN_JOB] Step completed | job_id: {job_id} | step: {step_name} | elapsed: {elapsed:.1f}s | total_steps: {len(steps_complete)}")
            job_ref.update({
                "status": "running", 
                "steps_complete": steps_complete,
                "step_status": step_status
            })

        logger.info(f"[RUN_JOB] Graph execution complete/timeout | job_id: {job_id} | steps: {steps_complete} | elapsed: {time.time() - start_time:.1f}s")

        update_data = {
            "status": "complete" if not timeout_hit else "complete_timeout",
            "completed_at": firestore.SERVER_TIMESTAMP,
            "step_status": step_status,
            "elapsed_seconds": time.time() - start_time
        }
        
        if final_state:
            if 'linkedin_data' in final_state:
                update_data['linkedin_data'] = final_state['linkedin_data']
                logger.info(f"[RUN_JOB] Saving linkedin_data | job_id: {job_id}")
            if 'job_openings' in final_state:
                update_data['job_openings'] = final_state['job_openings']
                job_count = len(final_state['job_openings']) if isinstance(final_state['job_openings'], list) else 0
                logger.info(f"[RUN_JOB] Saving job_openings | job_id: {job_id} | count: {job_count}")
            if 'recent_news_summary' in final_state:
                update_data['recent_news_summary'] = final_state['recent_news_summary']
                logger.info(f"[RUN_JOB] Saving recent_news_summary | job_id: {job_id}")
            if 'client_brief' in final_state:
                update_data['client_brief'] = final_state['client_brief']
                logger.info(f"[RUN_JOB] Saving client_brief | job_id: {job_id}")
            if 'data_source' in final_state:
                update_data['data_source'] = final_state['data_source']
                logger.info(f"[RUN_JOB] Data source | job_id: {job_id} | source: {final_state['data_source']}")
        
        if timeout_hit:
            update_data['error'] = f"Research timed out after {RESEARCH_TIMEOUT_SECONDS}s with {len(steps_complete)} steps completed"
            logger.warning(f"[RUN_JOB] Timeout error saved | job_id: {job_id}")
        
        job_ref.update(update_data)

        logger.info(f"[RUN_JOB] SUCCESS - Job complete | job_id: {job_id} | timeout: {timeout_hit}")
        return "Job completed successfully", 200

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[RUN_JOB] ERROR | job_id: {job_id} | exception: {str(e)} | elapsed: {elapsed:.1f}s", exc_info=True)
        if job_id:
            db.collection(FIRESTORE_COLLECTION).document(job_id).update({
                "status": "error",
                "error": str(e),
                "completed_at": firestore.SERVER_TIMESTAMP,
                "elapsed_seconds": elapsed
            })
            logger.info(f"[RUN_JOB] Error status saved to Firestore | job_id: {job_id}")
        return "Job failed", 200


if __name__ == '__main__':
    app.run(port=config.FLASK_PORT, debug=True)
