# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from agent_flow import get_research_graph
import config

app = Flask(__name__)
# CRITICAL: Allow requests from your React app's origin
# Vite runs on 5173 by default, not 3000.
CORS(app, resources={r"/research": {"origins": ["http://localhost:5173", "http://127.0.0.1:5173"]}})

# Compile the agent graph once on startup
app.config['AGENT_GRAPH'] = get_research_graph()

@app.route('/research', methods=['POST'])
def research_company():
    try:
        data = request.json
        user_input = data.get('input')
        url_input = data.get('url')

        if not user_input:
            return jsonify({"error": "No company name provided"}), 400

        # Get the compiled graph
        graph = app.config['AGENT_GRAPH']
        
        # Pass both the name and optional URL
        inputs = {
            "initial_input": user_input,
            "provided_url": url_input  # New field for explicit URL
        }
        
        # Run the agent flow
        result = graph.invoke(inputs)
        
        # Return the final, structured report
        # We now get the report directly from the 'final_report' key
        final_report_data = result.get("final_report", {})
        
        # Check if the report is a Pydantic model and convert
        if hasattr(final_report_data, 'dict'):
             final_report_data = final_report_data.dict()
        
        return jsonify(final_report_data)

    except Exception as e:
        print(f"Error during research: {e}") # Added for debugging
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Use the port from config
    app.run(port=config.FLASK_PORT, debug=True)
