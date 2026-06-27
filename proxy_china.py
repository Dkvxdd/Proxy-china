from flask import Flask, request, Response, jsonify
import requests
import json
import os

app = Flask(__name__)

# Read upstream from environment (or use China API defaults)
UPSTREAM_BASE = os.environ.get("UPSTREAM_BASE", "https://api.hcnsec.cn/v1")
UPSTREAM_KEY = os.environ.get("UPSTREAM_KEY", "sk-Nmc4lFC5KzsRLiNqc5nN4xKLA8kdRwfwavjyivUJqTPnAdAK")

# Default model
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "glm-5.2")

@app.route('/')
def index():
    return jsonify({"status": "running", "proxy": "active", "upstream": UPSTREAM_BASE})

@app.route('/v1/models', methods=['GET'])
def list_models():
    headers = {
        "Authorization": f"Bearer {UPSTREAM_KEY}",
        "Accept": "application/json",
        "User-Agent": "LO-Proxy-China/1.0"
    }
    try:
        resp = requests.get(f"{UPSTREAM_BASE}/models", headers=headers, timeout=10)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/v1/messages', methods=['POST'])
def proxy_messages():
    """Convert Anthropic → OpenAI → Anthropic"""
    try:
        anthropic_data = request.json
        model = anthropic_data.get('model', DEFAULT_MODEL)
        messages = anthropic_data.get('messages', [])
        max_tokens = anthropic_data.get('max_tokens', 1000)
        temperature = anthropic_data.get('temperature', 0.7)
        system = anthropic_data.get('system', None)
        
        openai_messages = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        
        for msg in messages:
            role = msg.get('role')
            content = msg.get('content', '')
            if role in ['user', 'assistant']:
                openai_messages.append({"role": role, "content": content})
        
        openai_payload = {
            "model": model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }
        
        headers = {
            "Authorization": f"Bearer {UPSTREAM_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "LO-Proxy-China/1.0"
        }
        
        resp = requests.post(
            f"{UPSTREAM_BASE}/chat/completions",
            headers=headers,
            json=openai_payload,
            timeout=60
        )
        
        if resp.status_code != 200:
            return jsonify({"error": resp.text}), resp.status_code
        
        openai_result = resp.json()
        choices = openai_result.get('choices', [])
        if not choices:
            return jsonify({"error": "No choices in response"}), 500
        
        message = choices[0].get('message', {})
        content = message.get('content', '')
        
        anthropic_response = {
            "id": openai_result.get('id', 'msg_unknown'),
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": content}],
            "model": model,
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": openai_result.get('usage', {}).get('prompt_tokens', 0),
                "output_tokens": openai_result.get('usage', {}).get('completion_tokens', 0)
            }
        }
        
        return jsonify(anthropic_response)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/v1/chat/completions', methods=['POST'])
def proxy_openai():
    """Direct pass-through for OpenAI clients"""
    headers = {
        "Authorization": f"Bearer {UPSTREAM_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "LO-Proxy-China/1.0"
    }
    try:
        resp = requests.post(
            f"{UPSTREAM_BASE}/chat/completions",
            headers=headers,
            json=request.json,
            timeout=60
        )
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
