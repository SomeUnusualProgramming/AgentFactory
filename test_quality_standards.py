"""
Quality Standards Test Suite

Demonstrates how code should be generated for different module types:
- web_interface (Flask routes)
- service (Business logic)
- utility (Helper functions)

This test suite validates that generated code adheres to AgentFactory
quality standards and can be properly reviewed and approved.
"""

import json
from code_standards import CodeValidator, get_validator, ModuleType
from agent_code_reviewer import run_reviewer


# =================================================================
# EXAMPLE 1: WEB_INTERFACE MODULE (FLASK)
# =================================================================

FLASK_WEBINTERFACE_GOOD = """
from flask import Flask, render_template, jsonify, request
import logging
from typing import Dict, List

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.route('/', methods=['GET'])
def index():
    \"\"\"Render the main dashboard page.\"\"\"
    return render_template('index.html')


@app.route('/api/articles', methods=['GET'])
def get_articles() -> Dict:
    \"\"\"Fetch all articles.
    
    Query Parameters:
        limit (int): Maximum number of articles to return (default: 10)
        offset (int): Pagination offset (default: 0)
    
    Returns:
        JSON with articles list or error
    \"\"\"
    try:
        limit = int(request.args.get('limit', 10))
        offset = int(request.args.get('offset', 0))
        
        # Delegate to service layer
        from article_service import ArticleService
        service = ArticleService()
        articles = service.get_articles(limit=limit, offset=offset)
        
        return jsonify({"data": articles, "error": None}), 200
    except ValueError as e:
        logger.error(f"Invalid parameters: {e}")
        return jsonify({"error": "Invalid parameters"}), 400
    except Exception as e:
        logger.error(f"Error fetching articles: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/articles/<int:article_id>', methods=['GET'])
def get_article_detail(article_id: int) -> Dict:
    \"\"\"Get a specific article by ID.
    
    Args:
        article_id: ID of the article
    
    Returns:
        JSON with article details
    \"\"\"
    try:
        from article_service import ArticleService
        service = ArticleService()
        article = service.get_by_id(article_id)
        
        if not article:
            return jsonify({"error": "Article not found"}), 404
        
        return jsonify({"data": article, "error": None}), 200
    except Exception as e:
        logger.error(f"Error fetching article {article_id}: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
"""

FLASK_WEBINTERFACE_BAD = """
from flask import Flask, jsonify
import requests
import sqlite3

app = Flask(__name__)

@app.route('/articles')
def articles():
    # BAD: Business logic directly in web_interface
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM articles')
    rows = cursor.fetchall()
    
    # BAD: External API call in web_interface
    response = requests.get('https://api.news.com/articles')
    
    # BAD: No type hints, no docstring, no error handling
    return jsonify({"data": rows})
"""


# =================================================================
# EXAMPLE 2: SERVICE MODULE (BUSINESS LOGIC)
# =================================================================

SERVICE_GOOD = """
import logging
import requests
from typing import List, Dict, Optional
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ArticleService:
    \"\"\"Service for managing articles and fetching from news sources.\"\"\"
    
    def __init__(self, api_key: Optional[str] = None):
        \"\"\"Initialize the service.
        
        Args:
            api_key: API key for news service (optional)
        \"\"\"
        import os
        self.api_key = api_key or os.environ.get('NEWS_API_KEY', '')
        self.timeout = 5
    
    def get_articles(self, source_id: str, limit: int = 10, offset: int = 0) -> List[Dict]:
        \"\"\"Fetch articles from a specific source.
        
        Args:
            source_id: ID of the news source
            limit: Maximum articles to return
            offset: Pagination offset
        
        Returns:
            List of article dictionaries with id, title, content, published_at
        
        Raises:
            ValueError: If parameters are invalid
        \"\"\"
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        
        try:
            url = f"https://newsapi.org/v2/sources/{source_id}"
            headers = {"X-API-Key": self.api_key}
            
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            articles = data.get('articles', [])
            
            # Apply pagination
            paginated = articles[offset:offset + limit]
            
            return [
                {
                    'id': i,
                    'title': article.get('title'),
                    'content': article.get('description'),
                    'published_at': article.get('publishedAt')
                }
                for i, article in enumerate(paginated)
            ]
            
        except requests.Timeout:
            logger.error(f"API timeout for source {source_id}")
            raise
        except requests.RequestException as e:
            logger.error(f"API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching articles: {e}")
            raise
    
    def get_by_id(self, article_id: int) -> Optional[Dict]:
        \"\"\"Get article by ID.
        
        Args:
            article_id: Article ID
        
        Returns:
            Article dict or None if not found
        \"\"\"
        try:
            logger.info(f"Fetching article {article_id}")
            # Implementation would fetch from database or cache
            return {"id": article_id, "title": "Article Title", "content": "..."}
        except Exception as e:
            logger.error(f"Error fetching article {article_id}: {e}")
            raise
"""

SERVICE_BAD = """
from flask import Flask, render_template

app = Flask(__name__)

# BAD: Service module has Flask app
@app.route('/articles')
def get_articles():
    # BAD: No type hints
    return []

# BAD: if __name__ block in service
if __name__ == '__main__':
    app.run()
"""


# =================================================================
# EXAMPLE 3: UTILITY MODULE (PURE FUNCTIONS)
# =================================================================

UTILITY_GOOD = """
from typing import Dict, List, Optional
import re
from datetime import datetime
import json


def validate_email(email: str) -> bool:
    \"\"\"Validate email address format.
    
    Args:
        email: Email address to validate
    
    Returns:
        True if valid, False otherwise
    \"\"\"
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def format_date(date_obj: Optional[datetime]) -> str:
    \"\"\"Format datetime to ISO 8601 string.
    
    Args:
        date_obj: datetime object or None
    
    Returns:
        ISO 8601 formatted string or empty string
    \"\"\"
    if date_obj is None:
        return ""
    return date_obj.strftime('%Y-%m-%dT%H:%M:%SZ')


def sanitize_html(text: str) -> str:
    \"\"\"Remove dangerous HTML characters from text.
    
    Args:
        text: Text to sanitize
    
    Returns:
        Sanitized text safe for HTML display
    \"\"\"
    replacements = {
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#x27;',
        '&': '&amp;'
    }
    result = text
    for char, entity in replacements.items():
        result = result.replace(char, entity)
    return result


def parse_json_safe(json_str: str) -> Dict:
    \"\"\"Parse JSON string with error handling.
    
    Args:
        json_str: JSON string to parse
    
    Returns:
        Parsed dict or empty dict on error
    \"\"\"
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return {}
"""

UTILITY_BAD = """
# BAD: Utility with class and state
class UserCache:
    def __init__(self):
        self.cache = {}
    
    def get_user(self, user_id):
        # BAD: Stateful, not pure function
        return self.cache.get(user_id)

# BAD: Utility importing service
from article_service import ArticleService

def get_articles():
    # BAD: Not pure, calls service
    service = ArticleService()
    return service.get_articles()

# BAD: Business logic in utility
def calculate_discount(price, customer_type):
    # This is business logic, not utility
    if customer_type == "premium":
        return price * 0.9
    return price
"""


# =================================================================
# TEST CASES
# =================================================================

def test_web_interface_good():
    """Test that good Flask web_interface passes validation."""
    print("\n" + "="*70)
    print("TEST 1: Web Interface (Flask) - GOOD CODE")
    print("="*70)
    
    validator = get_validator("web_interface", "web_interface.py")
    report = validator.validate(FLASK_WEBINTERFACE_GOOD, "WebInterface")
    
    print(f"\nQuality Score: {report.quality_score}/100")
    print(f"Verdict: {report.verdict}")
    print(f"Issues: {len(report.issues)}")
    
    assert report.quality_score >= 80, f"Expected score >= 80, got {report.quality_score}"
    assert report.verdict == "APPROVE", f"Expected APPROVE, got {report.verdict}"
    print("✅ PASSED")


def test_web_interface_bad():
    """Test that bad Flask code is caught."""
    print("\n" + "="*70)
    print("TEST 2: Web Interface (Flask) - BAD CODE")
    print("="*70)
    
    validator = get_validator("web_interface", "web_interface.py")
    report = validator.validate(FLASK_WEBINTERFACE_BAD, "WebInterface")
    
    print(f"\nQuality Score: {report.quality_score}/100")
    print(f"Verdict: {report.verdict}")
    print(f"Issues found: {len(report.issues)}")
    
    for issue in report.issues:
        print(f"  - [{issue.severity.value}] {issue.message}")
    
    assert report.quality_score < 70, f"Expected score < 70, got {report.quality_score}"
    assert report.verdict == "REJECT", f"Expected REJECT, got {report.verdict}"
    print("✅ PASSED - Correctly rejected bad code")


def test_service_good():
    """Test that good service module passes validation."""
    print("\n" + "="*70)
    print("TEST 3: Service Module - GOOD CODE")
    print("="*70)
    
    validator = get_validator("service", "article_service.py")
    report = validator.validate(SERVICE_GOOD, "ArticleService")
    
    print(f"\nQuality Score: {report.quality_score}/100")
    print(f"Verdict: {report.verdict}")
    print(f"Issues: {len(report.issues)}")
    
    assert report.quality_score >= 80, f"Expected score >= 80, got {report.quality_score}"
    assert report.verdict == "APPROVE", f"Expected APPROVE, got {report.verdict}"
    print("✅ PASSED")


def test_service_bad():
    """Test that bad service code is caught."""
    print("\n" + "="*70)
    print("TEST 4: Service Module - BAD CODE")
    print("="*70)
    
    validator = get_validator("service", "article_service.py")
    report = validator.validate(SERVICE_BAD, "ArticleService")
    
    print(f"\nQuality Score: {report.quality_score}/100")
    print(f"Verdict: {report.verdict}")
    print(f"Issues found: {len(report.issues)}")
    
    for issue in report.issues:
        print(f"  - [{issue.severity.value}] {issue.message}")
    
    assert report.quality_score < 70, f"Expected score < 70, got {report.quality_score}"
    assert report.verdict == "REJECT", f"Expected REJECT, got {report.verdict}"
    print("✅ PASSED - Correctly rejected bad code")


def test_utility_good():
    """Test that good utility module passes validation."""
    print("\n" + "="*70)
    print("TEST 5: Utility Module - GOOD CODE")
    print("="*70)
    
    validator = get_validator("utility", "utils.py")
    report = validator.validate(UTILITY_GOOD, "Utilities")
    
    print(f"\nQuality Score: {report.quality_score}/100")
    print(f"Verdict: {report.verdict}")
    print(f"Issues: {len(report.issues)}")
    
    assert report.quality_score >= 80, f"Expected score >= 80, got {report.quality_score}"
    assert report.verdict == "APPROVE", f"Expected APPROVE, got {report.verdict}"
    print("✅ PASSED")


def test_utility_bad():
    """Test that bad utility code is caught."""
    print("\n" + "="*70)
    print("TEST 6: Utility Module - BAD CODE")
    print("="*70)
    
    validator = get_validator("utility", "utils.py")
    report = validator.validate(UTILITY_BAD, "Utilities")
    
    print(f"\nQuality Score: {report.quality_score}/100")
    print(f"Verdict: {report.verdict}")
    print(f"Issues found: {len(report.issues)}")
    
    for issue in report.issues:
        print(f"  - [{issue.severity.value}] {issue.message}")
    
    assert report.quality_score < 70, f"Expected score < 70, got {report.quality_score}"
    assert report.verdict == "REJECT", f"Expected REJECT, got {report.verdict}"
    print("✅ PASSED - Correctly rejected bad code")


def test_hardcoded_secrets():
    """Test that hardcoded credentials are detected."""
    print("\n" + "="*70)
    print("TEST 7: Security - Hardcoded Secrets")
    print("="*70)
    
    bad_code = '''
from flask import Flask

app = Flask(__name__)

# BAD: Hardcoded credentials
API_KEY = "sk_live_51234567890abcdef"
PASSWORD = "admin123"
DATABASE_URL = "postgres://user:password@localhost:5432/db"

@app.route('/data')
def get_data():
    return "secret"
'''
    
    validator = get_validator("web_interface", "bad_secrets.py")
    report = validator.validate(bad_code, "BadSecrets")
    
    print(f"\nQuality Score: {report.quality_score}/100")
    
    # Check if hardcoded secrets are detected
    has_security_issue = any(
        issue.type.value == "security" 
        for issue in report.issues
    )
    
    assert has_security_issue, "Expected to detect hardcoded secrets"
    print("✅ PASSED - Correctly detected hardcoded secrets")


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("AGENTFACTORY QUALITY STANDARDS TEST SUITE")
    print("Testing code generation standards for Flask web applications")
    print("="*70)
    
    try:
        test_web_interface_good()
        test_web_interface_bad()
        test_service_good()
        test_service_bad()
        test_utility_good()
        test_utility_bad()
        test_hardcoded_secrets()
        
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED!")
        print("="*70)
        print("\nThe quality standards validation system is working correctly.")
        print("All generated code will be validated against these standards.")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()
