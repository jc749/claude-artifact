"""
Gemini + Notion Integration for Railway
Flask API that uses Gemini with Notion data access
"""

from flask import Flask, request, jsonify
import os
import json
import requests
from datetime import datetime, timedelta
import google.genai as genai

# Configuration
NOTION_TOKEN = os.getenv("NOTION_API_KEY")
DATABASE_IDS = os.getenv("DATABASE_IDS", "").split(",")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NOTION_VERSION = "2022-06-28"

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION
}

# Notion Helper Functions
def get_all_database_entries(database_id):
    """Get all entries from a Notion database"""
    all_results = []
    has_more = True
    next_cursor = None
    
    while has_more:
        url = f"https://api.notion.com/v1/databases/{database_id}/query"
        payload = {}
        if next_cursor:
            payload["start_cursor"] = next_cursor
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            all_results.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            next_cursor = data.get("next_cursor")
        else:
            break
    
    return all_results

def get_property_value(properties, property_name):
    """Extract value from Notion property"""
    prop = properties.get(property_name, {})
    prop_type = prop.get("type")
    
    if not prop_type:
        return None
    
    if prop_type == "title":
        title_list = prop.get("title", [])
        return title_list[0].get("plain_text", "") if title_list else ""
    elif prop_type == "rich_text":
        text_list = prop.get("rich_text", [])
        return " ".join([t.get("plain_text", "") for t in text_list])
    elif prop_type == "url":
        return prop.get("url", "")
    elif prop_type == "date":
        date_obj = prop.get("date", {})
        return date_obj.get("start", "") if date_obj else ""
    elif prop_type == "select":
        select_obj = prop.get("select", {})
        return select_obj.get("name", "") if select_obj else ""
    elif prop_type == "multi_select":
        return [item.get("name", "") for item in prop.get("multi_select", [])]
    
    return None

def parse_notion_page(page):
    """Parse a Notion page"""
    properties = page.get("properties", {})
    
    parsed = {
        "id": page.get("id", ""),
        "url": page.get("url", ""),
        "created": page.get("created_time", ""),
        "properties": {}
    }
    
    for prop_name in properties.keys():
        value = get_property_value(properties, prop_name)
        if value:
            parsed["properties"][prop_name] = value
    
    return parsed

def search_databases(keyword):
    """Search all databases for a keyword"""
    results = []
    
    for db_id in DATABASE_IDS:
        entries = get_all_database_entries(db_id)
        for entry in entries:
            parsed = parse_notion_page(entry)
            entry_text = json.dumps(parsed["properties"]).lower()
            if keyword.lower() in entry_text:
                results.append({
                    "database_id": db_id,
                    "entry": parsed
                })
    
    return results

def get_recent_entries(days=7):
    """Get recent entries from all databases"""
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
    recent = {}
    
    for db_id in DATABASE_IDS:
        entries = get_all_database_entries(db_id)
        recent_entries = []
        
        for entry in entries:
            if entry.get("created_time", "") >= cutoff_date:
                recent_entries.append(parse_notion_page(entry))
        
        if recent_entries:
            recent[db_id] = recent_entries
    
    return recent

def get_all_data():
    """Get all data from all databases"""
    all_data = {}
    
    for i, db_id in enumerate(DATABASE_IDS, 1):
        entries = get_all_database_entries(db_id)
        parsed_entries = [parse_notion_page(entry) for entry in entries]
        all_data[f"database_{i}"] = {
            "database_id": db_id,
            "entries": parsed_entries,
            "count": len(parsed_entries)
        }
    
    return all_data

def create_notion_context(data_summary):
    """Create context string from Notion data"""
    context_parts = []
    
    if isinstance(data_summary, dict):
        for key, value in data_summary.items():
            context_parts.append(f"{key}: {json.dumps(value, indent=2)}")
    else:
        context_parts.append(str(data_summary))
    
    return "\n".join(context_parts)

# Flask App
app = Flask(__name__)

# CORS Headers - Add to every response
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.route('/')
def home():
    return '''
    <h1>Gemini + Notion Hollywood Intelligence</h1>
    <p>Available endpoints:</p>
    <ul>
        <li><a href="/status">/status</a> - Check connection</li>
        <li>/search?keyword=awards - Search data</li>
        <li>/recent?days=7 - Get recent entries</li>
        <li>/chat (POST) - Chat with Gemini</li>
    </ul>
    '''

@app.route('/status')
def status():
    """Check connection"""
    try:
        data = get_all_data()
        total_entries = sum(db['count'] for db in data.values())
        
        return jsonify({
            "status": "success",
            "notion_connected": True,
            "gemini_configured": GEMINI_API_KEY is not None,
            "databases": len(data),
            "total_entries": total_entries
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/search')
def search():
    """Search databases"""
    keyword = request.args.get('keyword', '')
    
    if not keyword:
        return jsonify({"error": "Please provide a 'keyword' parameter"}), 400
    
    try:
        results = search_databases(keyword)
        
        return jsonify({
            "keyword": keyword,
            "matches": len(results),
            "results": results[:10]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/recent')
def recent():
    """Get recent entries"""
    days = request.args.get('days', 7, type=int)
    
    try:
        recent_news = get_recent_entries(days)
        total = sum(len(entries) for entries in recent_news.values())
        
        return jsonify({
            "days": days,
            "total_entries": total,
            "by_database": {db_id: len(entries) for db_id, entries in recent_news.items()},
            "data": recent_news
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/chat', methods=['POST', 'OPTIONS'])
def chat():
    """Chat with Gemini using Notion data"""
    
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        return '', 204
    
    if not GEMINI_API_KEY:
        return jsonify({
            "error": "GEMINI_API_KEY not configured"
        }), 500
    
    data = request.get_json()
    
    if not data or 'message' not in data:
        return jsonify({
            "error": "Please provide a 'message' in JSON body"
        }), 400
    
    user_message = data['message']
    
    try:
        # Configure Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-pro')
        
        # Check if user wants to search/query data
        search_keywords = ['search', 'find', 'recent', 'latest', 'show me', 'what']
        should_fetch_data = any(keyword in user_message.lower() for keyword in search_keywords)
        
        notion_context = ""
        
        if should_fetch_data:
            if 'recent' in user_message.lower() or 'latest' in user_message.lower():
                days = 7
                if 'week' in user_message.lower():
                    days = 7
                elif 'month' in user_message.lower():
                    days = 30
                
                notion_data = get_recent_entries(days)
                notion_context = f"\n\nRecent data (last {days} days):\n{create_notion_context(notion_data)}"
            
            else:
                # Try to extract search keyword
                words = user_message.split()
                for i, word in enumerate(words):
                    if word.lower() in ['search', 'find', 'about'] and i + 1 < len(words):
                        search_term = words[i + 1]
                        search_results = search_databases(search_term)
                        notion_context = f"\n\nSearch results for '{search_term}':\n{create_notion_context(search_results[:5])}"
                        break
        
        # Build prompt
        system_prompt = """You are an AI assistant with access to Hollywood intelligence data. 
Provide accurate, helpful answers about entertainment news, talent, and industry updates.
Focus on brand partnerships, PR opportunities, awards season coverage, and strategic insights."""

        full_prompt = f"{system_prompt}\n\n{notion_context}\n\nUser: {user_message}\n\nAssistant:"
        
        # Generate response
        response = model.generate_content(full_prompt)
        
        return jsonify({
            "message": user_message,
            "response": response.text,
            "used_notion_data": bool(notion_context)
        })
        
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
