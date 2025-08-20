"""Integration tests for verification criteria templates with real project structures."""

import pytest
import tempfile
import subprocess
import json
from pathlib import Path
from typing import Dict, Any

from hydra.verification_system.criteria_templates import (
    StrictnessLevel,
    create_template_for_project_type,
    evaluate_project_against_template,
    CriteriaComposer,
    BossAgentIntegration
)


@pytest.fixture
def complex_api_project():
    """Create a complex API project with authentication and documentation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        # Main API module with authentication
        (project_dir / "api.py").write_text("""
from flask import Flask, request, jsonify
from functools import wraps
import jwt

app = Flask(__name__)

def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token missing'}), 401
        try:
            jwt.decode(token, 'secret', algorithms=['HS256'])
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated

def validate_user_data(data):
    required_fields = ['name', 'email']
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
    return True

@app.errorhandler(Exception)
def handle_error(e):
    return jsonify({'error': str(e)}), 500

try:
    app.run()
except Exception as e:
    print(f"Error starting app: {e}")
""")
        
        # Routes with comprehensive HTTP methods
        (project_dir / "routes.py").write_text("""
from flask import Blueprint, request, jsonify
from api import auth_required, validate_user_data

bp = Blueprint('api', __name__)

@bp.get('/users')
@auth_required
def get_users():
    return jsonify([])

@bp.post('/users')
@auth_required
def create_user():
    data = request.get_json()
    validate_user_data(data)
    return jsonify({'id': 1, **data}), 201

@bp.put('/users/<int:user_id>')
@auth_required
def update_user(user_id):
    data = request.get_json()
    validate_user_data(data)
    return jsonify({'id': user_id, **data})

@bp.delete('/users/<int:user_id>')
@auth_required
def delete_user(user_id):
    return '', 204
""")
        
        # Models with proper structure
        (project_dir / "models.py").write_text("""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class User:
    id: Optional[int]
    name: str
    email: str
    created_at: Optional[datetime] = None

class UserRepository:
    def __init__(self):
        self.users = []
    
    def create(self, user: User) -> User:
        user.id = len(self.users) + 1
        user.created_at = datetime.now()
        self.users.append(user)
        return user
    
    def get_all(self) -> list[User]:
        return self.users
""")
        
        # Comprehensive tests
        (project_dir / "test_api.py").write_text("""
import pytest
import json
from api import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_get_users_unauthorized(client):
    response = client.get('/users')
    assert response.status_code == 401

def test_create_user_with_auth(client):
    # This would test with proper auth token
    pass

def test_validate_user_data():
    from api import validate_user_data
    
    with pytest.raises(ValueError):
        validate_user_data({})
    
    assert validate_user_data({'name': 'John', 'email': 'john@example.com'})
""")
        
        # API documentation for strict mode
        (project_dir / "api_docs.md").write_text("""
# API Documentation

## Endpoints

### GET /users
Returns list of users.

**Authentication**: Required

**Response**: 
```json
[
  {
    "id": 1,
    "name": "John Doe",
    "email": "john@example.com"
  }
]
```

### POST /users
Creates a new user.

**Authentication**: Required

**Request Body**:
```json
{
  "name": "John Doe",
  "email": "john@example.com"
}
```
""")
        
        yield project_dir


@pytest.fixture
def advanced_cli_project():
    """Create an advanced CLI project with subcommands and validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        # Main CLI with subcommands
        (project_dir / "cli.py").write_text("""
#!/usr/bin/env python3
import argparse
import sys
import json
from pathlib import Path

def validate_file_path(path):
    if not Path(path).exists():
        raise argparse.ArgumentTypeError(f"File does not exist: {path}")
    return path

def validate_email(email):
    if '@' not in email:
        raise argparse.ArgumentTypeError(f"Invalid email format: {email}")
    return email

def create_user(args):
    user_data = {
        'name': args.name,
        'email': args.email
    }
    print(f"Created user: {json.dumps(user_data)}")
    return 0

def list_users(args):
    print("Listing users...")
    return 0

def delete_user(args):
    print(f"Deleting user {args.user_id}")
    return 0

def main():
    parser = argparse.ArgumentParser(
        description='User management CLI tool',
        help='Manage users through command line interface'
    )
    parser.add_argument('--version', action='version', version='1.0.0')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Create user subcommand
    create_parser = subparsers.add_parser('create', help='Create a new user')
    create_parser.add_argument('--name', required=True, help='User name')
    create_parser.add_argument('--email', required=True, type=validate_email, help='User email')
    create_parser.set_defaults(func=create_user)
    
    # List users subcommand
    list_parser = subparsers.add_parser('list', help='List all users')
    list_parser.set_defaults(func=list_users)
    
    # Delete user subcommand
    delete_parser = subparsers.add_parser('delete', help='Delete a user')
    delete_parser.add_argument('user_id', type=int, help='User ID to delete')
    delete_parser.set_defaults(func=delete_user)
    
    args = parser.parse_args()
    
    if not hasattr(args, 'func'):
        parser.print_help()
        sys.exit(1)
    
    try:
        exit_code = args.func(args)
        sys.exit(exit_code)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
""")
        
        # CLI tests for strict mode
        (project_dir / "test_cli.py").write_text("""
import pytest
import subprocess
import sys
from pathlib import Path

def test_cli_help():
    result = subprocess.run([sys.executable, 'cli.py', '--help'], 
                          capture_output=True, text=True)
    assert result.returncode == 0
    assert 'User management CLI tool' in result.stdout

def test_cli_version():
    result = subprocess.run([sys.executable, 'cli.py', '--version'], 
                          capture_output=True, text=True)
    assert result.returncode == 0
    assert '1.0.0' in result.stdout

def test_cli_create_user():
    result = subprocess.run([
        sys.executable, 'cli.py', 'create', 
        '--name', 'John', '--email', 'john@example.com'
    ], capture_output=True, text=True)
    assert result.returncode == 0
    assert 'Created user' in result.stdout

def test_cli_invalid_email():
    result = subprocess.run([
        sys.executable, 'cli.py', 'create', 
        '--name', 'John', '--email', 'invalid-email'
    ], capture_output=True, text=True)
    assert result.returncode != 0
""")
        
        yield project_dir


@pytest.fixture
def production_library_project():
    """Create a production-ready library project."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        # Main library module with type hints and comprehensive docstrings
        (project_dir / "__init__.py").write_text('''
"""Mathematical utilities library.

This library provides common mathematical operations with proper error handling
and type safety.
"""

from typing import Union, List, Optional
import logging

__version__ = "1.0.0"
__author__ = "Test Author"

Number = Union[int, float]

def add_numbers(a: Number, b: Number) -> Number:
    """Add two numbers together.
    
    Args:
        a: First number to add
        b: Second number to add
        
    Returns:
        The sum of a and b
        
    Raises:
        TypeError: If inputs are not numbers
        
    Examples:
        >>> add_numbers(2, 3)
        5
        >>> add_numbers(2.5, 3.7)
        6.2
    """
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("Both arguments must be numbers")
    return a + b

def multiply_numbers(a: Number, b: Number) -> Number:
    """Multiply two numbers.
    
    Args:
        a: First number
        b: Second number
        
    Returns:
        The product of a and b
    """
    return a * b

class Calculator:
    """Advanced calculator with history tracking.
    
    This calculator maintains a history of operations and provides
    statistical functions.
    """
    
    def __init__(self) -> None:
        """Initialize calculator with empty history."""
        self.history: List[str] = []
        self.logger = logging.getLogger(__name__)
    
    def add(self, a: Number, b: Number) -> Number:
        """Add two numbers and record in history.
        
        Args:
            a: First number
            b: Second number
            
        Returns:
            Sum of the numbers
        """
        result = add_numbers(a, b)
        self.history.append(f"{a} + {b} = {result}")
        self.logger.info(f"Addition performed: {a} + {b} = {result}")
        return result
    
    def get_history(self) -> List[str]:
        """Get calculation history.
        
        Returns:
            List of calculation strings
        """
        return self.history.copy()
    
    def clear_history(self) -> None:
        """Clear calculation history."""
        self.history.clear()
        self.logger.info("History cleared")
''')
        
        # Setup file for strict mode
        (project_dir / "setup.py").write_text("""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="math-utils",
    version="1.0.0",
    author="Test Author",
    author_email="test@example.com",
    description="Mathematical utilities library",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.8",
    install_requires=[],
    extras_require={
        "dev": [
            "pytest",
            "pytest-cov",
            "black",
            "mypy",
        ],
    },
)
""")
        
        # README for strict mode
        (project_dir / "README.md").write_text("""
# Math Utils Library

A comprehensive mathematical utilities library with proper type safety and error handling.

## Installation

```bash
pip install math-utils
```

## Usage

```python
from math_utils import add_numbers, Calculator

# Simple function usage
result = add_numbers(2, 3)
print(result)  # 5

# Calculator with history
calc = Calculator()
result = calc.add(2, 3)
print(calc.get_history())  # ['2 + 3 = 5']
```

## Features

- Type-safe mathematical operations
- Comprehensive error handling
- Operation history tracking
- Full test coverage
- Production-ready code quality

## Development

```bash
pip install -e ".[dev]"
pytest
```
""")
        
        # Comprehensive tests
        tests_dir = project_dir / "tests"
        tests_dir.mkdir()
        
        (tests_dir / "test_main.py").write_text("""
import pytest
from math_utils import add_numbers, multiply_numbers, Calculator

class TestMathFunctions:
    def test_add_numbers_integers(self):
        assert add_numbers(2, 3) == 5
        assert add_numbers(-1, 1) == 0
        assert add_numbers(0, 0) == 0
    
    def test_add_numbers_floats(self):
        assert add_numbers(2.5, 3.7) == 6.2
        assert add_numbers(-1.5, 1.5) == 0.0
    
    def test_add_numbers_mixed(self):
        assert add_numbers(2, 3.5) == 5.5
        assert add_numbers(2.5, 3) == 5.5
    
    def test_add_numbers_type_error(self):
        with pytest.raises(TypeError):
            add_numbers("2", 3)
        with pytest.raises(TypeError):
            add_numbers(2, None)
    
    def test_multiply_numbers(self):
        assert multiply_numbers(2, 3) == 6
        assert multiply_numbers(2.5, 4) == 10.0

class TestCalculator:
    def test_calculator_add(self):
        calc = Calculator()
        result = calc.add(2, 3)
        assert result == 5
        assert len(calc.get_history()) == 1
        assert "2 + 3 = 5" in calc.get_history()[0]
    
    def test_calculator_history(self):
        calc = Calculator()
        calc.add(1, 2)
        calc.add(3, 4)
        
        history = calc.get_history()
        assert len(history) == 2
        assert "1 + 2 = 3" in history[0]
        assert "3 + 4 = 7" in history[1]
    
    def test_calculator_clear_history(self):
        calc = Calculator()
        calc.add(1, 2)
        assert len(calc.get_history()) == 1
        
        calc.clear_history()
        assert len(calc.get_history()) == 0
    
    def test_calculator_history_isolation(self):
        calc = Calculator()
        calc.add(1, 2)
        
        history1 = calc.get_history()
        history2 = calc.get_history()
        
        # Ensure history copies don't affect each other
        history1.append("fake")
        assert len(history2) == 1
""")
        
        yield project_dir


@pytest.fixture
def full_stack_web_app():
    """Create a full-stack web application with all components."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        # Main Flask application
        (project_dir / "app.py").write_text("""
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3
import re

app = Flask(__name__)
app.secret_key = 'dev-secret-key'

def init_db():
    conn = sqlite3.connect('users.db')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    conn.close()

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    return len(password) >= 8

def validate_registration_form(data):
    errors = []
    
    if not data.get('username'):
        errors.append('Username is required')
    elif len(data['username']) < 3:
        errors.append('Username must be at least 3 characters')
    
    if not data.get('email'):
        errors.append('Email is required')
    elif not validate_email(data['email']):
        errors.append('Invalid email format')
    
    if not data.get('password'):
        errors.append('Password is required')
    elif not validate_password(data['password']):
        errors.append('Password must be at least 8 characters')
    
    return errors

@app.route('/')
def index():
    return render_template('index.html', title='Welcome')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.form.to_dict()
        errors = validate_registration_form(data)
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('register.html', title='Register')
        
        # Save user (simplified)
        flash('Registration successful!', 'success')
        return redirect(url_for('index'))
    
    return render_template('register.html', title='Register')

@app.route('/api/users', methods=['GET'])
def api_get_users():
    # Simplified API endpoint
    return jsonify([])

@app.route('/api/validate-email', methods=['POST'])
def api_validate_email():
    data = request.get_json()
    email = data.get('email', '')
    
    is_valid = validate_email(email)
    return jsonify({'valid': is_valid})

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
""")
        
        # Templates directory
        templates_dir = project_dir / "templates"
        templates_dir.mkdir()
        
        # Base template
        (templates_dir / "base.html").write_text("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% if title %}{{ title }} - {% endif %}My App</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
</head>
<body>
    <nav class="navbar">
        <div class="nav-container">
            <a href="{{ url_for('index') }}" class="nav-brand">My App</a>
            <ul class="nav-menu">
                <li><a href="{{ url_for('index') }}">Home</a></li>
                <li><a href="{{ url_for('register') }}">Register</a></li>
            </ul>
        </div>
    </nav>
    
    <main class="main-content">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="flash-messages">
                    {% for category, message in messages %}
                        <div class="flash flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}
        
        {% block content %}{% endblock %}
    </main>
    
    <script src="{{ url_for('static', filename='js/script.js') }}"></script>
</body>
</html>
""")
        
        # Index template
        (templates_dir / "index.html").write_text("""
{% extends "base.html" %}

{% block content %}
<div class="hero">
    <h1>Welcome to My App</h1>
    <p>A full-stack web application with modern features.</p>
    <a href="{{ url_for('register') }}" class="btn btn-primary">Get Started</a>
</div>

<div class="features">
    <div class="feature">
        <h3>User Registration</h3>
        <p>Secure user registration with validation.</p>
    </div>
    <div class="feature">
        <h3>API Endpoints</h3>
        <p>RESTful API for data access.</p>
    </div>
    <div class="feature">
        <h3>Responsive Design</h3>
        <p>Works on all devices.</p>
    </div>
</div>
{% endblock %}
""")
        
        # Registration template
        (templates_dir / "register.html").write_text("""
{% extends "base.html" %}

{% block content %}
<div class="form-container">
    <h2>Create Account</h2>
    
    <form method="POST" class="registration-form" id="registrationForm">
        <div class="form-group">
            <label for="username">Username:</label>
            <input type="text" id="username" name="username" required 
                   minlength="3" class="form-control">
        </div>
        
        <div class="form-group">
            <label for="email">Email:</label>
            <input type="email" id="email" name="email" required 
                   class="form-control">
            <div id="email-validation" class="validation-message"></div>
        </div>
        
        <div class="form-group">
            <label for="password">Password:</label>
            <input type="password" id="password" name="password" required 
                   minlength="8" class="form-control">
        </div>
        
        <button type="submit" class="btn btn-primary">Register</button>
    </form>
</div>
{% endblock %}
""")
        
        # Static files directory
        static_dir = project_dir / "static"
        static_dir.mkdir()
        
        # CSS subdirectory
        css_dir = static_dir / "css"
        css_dir.mkdir()
        
        (css_dir / "style.css").write_text("""
/* Base styles */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    line-height: 1.6;
    color: #333;
    background-color: #f8f9fa;
}

/* Navigation */
.navbar {
    background: #2c3e50;
    padding: 1rem 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.nav-container {
    max-width: 1200px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 2rem;
}

.nav-brand {
    color: white;
    text-decoration: none;
    font-size: 1.5rem;
    font-weight: bold;
}

.nav-menu {
    display: flex;
    list-style: none;
    gap: 2rem;
}

.nav-menu a {
    color: white;
    text-decoration: none;
    transition: color 0.3s;
}

.nav-menu a:hover {
    color: #3498db;
}

/* Main content */
.main-content {
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem;
}

/* Flash messages */
.flash-messages {
    margin-bottom: 2rem;
}

.flash {
    padding: 1rem;
    border-radius: 4px;
    margin-bottom: 1rem;
}

.flash-success {
    background: #d4edda;
    color: #155724;
    border: 1px solid #c3e6cb;
}

.flash-error {
    background: #f8d7da;
    color: #721c24;
    border: 1px solid #f5c6cb;
}

/* Hero section */
.hero {
    text-align: center;
    padding: 4rem 0;
    background: white;
    border-radius: 8px;
    margin-bottom: 3rem;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

.hero h1 {
    font-size: 3rem;
    margin-bottom: 1rem;
    color: #2c3e50;
}

.hero p {
    font-size: 1.2rem;
    margin-bottom: 2rem;
    color: #666;
}

/* Features grid */
.features {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 2rem;
    margin-top: 3rem;
}

.feature {
    background: white;
    padding: 2rem;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    text-align: center;
}

.feature h3 {
    color: #2c3e50;
    margin-bottom: 1rem;
}

/* Form styles */
.form-container {
    max-width: 500px;
    margin: 0 auto;
    background: white;
    padding: 2rem;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

.form-group {
    margin-bottom: 1.5rem;
}

.form-group label {
    display: block;
    margin-bottom: 0.5rem;
    font-weight: bold;
    color: #555;
}

.form-control {
    width: 100%;
    padding: 0.75rem;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 1rem;
    transition: border-color 0.3s;
}

.form-control:focus {
    outline: none;
    border-color: #3498db;
    box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2);
}

.validation-message {
    margin-top: 0.5rem;
    font-size: 0.875rem;
}

.validation-message.error {
    color: #e74c3c;
}

.validation-message.success {
    color: #27ae60;
}

/* Buttons */
.btn {
    display: inline-block;
    padding: 0.75rem 1.5rem;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    text-decoration: none;
    font-size: 1rem;
    transition: all 0.3s;
}

.btn-primary {
    background: #3498db;
    color: white;
}

.btn-primary:hover {
    background: #2980b9;
    transform: translateY(-1px);
}

/* Responsive design */
@media (max-width: 768px) {
    .nav-container {
        flex-direction: column;
        gap: 1rem;
    }
    
    .hero h1 {
        font-size: 2rem;
    }
    
    .features {
        grid-template-columns: 1fr;
    }
    
    .main-content {
        padding: 1rem;
    }
}
""")
        
        # JavaScript subdirectory
        js_dir = static_dir / "js"
        js_dir.mkdir()
        
        (js_dir / "script.js").write_text("""
// Main application JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Initialize form validation
    initializeFormValidation();
    
    // Initialize flash message auto-hide
    initializeFlashMessages();
    
    // Initialize API validation
    initializeEmailValidation();
});

function initializeFormValidation() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!validateForm(this)) {
                e.preventDefault();
                showValidationErrors();
            }
        });
    });
}

function validateForm(form) {
    let isValid = true;
    const inputs = form.querySelectorAll('input[required]');
    
    inputs.forEach(input => {
        if (!validateInput(input)) {
            isValid = false;
        }
    });
    
    return isValid;
}

function validateInput(input) {
    const value = input.value.trim();
    const type = input.type;
    const minLength = input.getAttribute('minlength');
    
    // Clear previous validation
    clearValidationMessage(input);
    
    // Required field validation
    if (!value) {
        showInputError(input, 'This field is required');
        return false;
    }
    
    // Minimum length validation
    if (minLength && value.length < parseInt(minLength)) {
        showInputError(input, `Must be at least ${minLength} characters`);
        return false;
    }
    
    // Email validation
    if (type === 'email' && !isValidEmail(value)) {
        showInputError(input, 'Please enter a valid email address');
        return false;
    }
    
    // Password strength validation
    if (type === 'password' && !isStrongPassword(value)) {
        showInputError(input, 'Password must be at least 8 characters with letters and numbers');
        return false;
    }
    
    showInputSuccess(input);
    return true;
}

function isValidEmail(email) {
    const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    return emailRegex.test(email);
}

function isStrongPassword(password) {
    return password.length >= 8 && 
           /[a-zA-Z]/.test(password) && 
           /[0-9]/.test(password);
}

function showInputError(input, message) {
    input.classList.add('error');
    
    let errorElement = input.parentNode.querySelector('.validation-message');
    if (!errorElement) {
        errorElement = document.createElement('div');
        errorElement.className = 'validation-message';
        input.parentNode.appendChild(errorElement);
    }
    
    errorElement.textContent = message;
    errorElement.className = 'validation-message error';
}

function showInputSuccess(input) {
    input.classList.remove('error');
    input.classList.add('success');
    
    const errorElement = input.parentNode.querySelector('.validation-message');
    if (errorElement) {
        errorElement.className = 'validation-message success';
        errorElement.textContent = '✓ Valid';
    }
}

function clearValidationMessage(input) {
    input.classList.remove('error', 'success');
    
    const errorElement = input.parentNode.querySelector('.validation-message');
    if (errorElement) {
        errorElement.textContent = '';
        errorElement.className = 'validation-message';
    }
}

function showValidationErrors() {
    const firstError = document.querySelector('.form-control.error');
    if (firstError) {
        firstError.focus();
        firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

function initializeFlashMessages() {
    const flashMessages = document.querySelectorAll('.flash');
    
    flashMessages.forEach(message => {
        // Add close button
        const closeBtn = document.createElement('button');
        closeBtn.innerHTML = '×';
        closeBtn.className = 'flash-close';
        closeBtn.onclick = () => message.remove();
        message.appendChild(closeBtn);
        
        // Auto-hide after 5 seconds
        setTimeout(() => {
            if (message.parentNode) {
                message.style.opacity = '0';
                setTimeout(() => message.remove(), 300);
            }
        }, 5000);
    });
}

function initializeEmailValidation() {
    const emailInput = document.getElementById('email');
    if (!emailInput) return;
    
    let validationTimeout;
    
    emailInput.addEventListener('input', function() {
        clearTimeout(validationTimeout);
        
        validationTimeout = setTimeout(() => {
            validateEmailWithAPI(this.value);
        }, 500);
    });
}

function validateEmailWithAPI(email) {
    if (!email || !isValidEmail(email)) return;
    
    fetch('/api/validate-email', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email: email })
    })
    .then(response => response.json())
    .then(data => {
        const emailInput = document.getElementById('email');
        const validationDiv = document.getElementById('email-validation');
        
        if (data.valid) {
            validationDiv.textContent = '✓ Email format is valid';
            validationDiv.className = 'validation-message success';
        } else {
            validationDiv.textContent = '✗ Invalid email format';
            validationDiv.className = 'validation-message error';
        }
    })
    .catch(error => {
        console.error('Email validation error:', error);
    });
}

// Utility functions
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function showLoading(element) {
    element.disabled = true;
    element.textContent = 'Loading...';
}

function hideLoading(element, originalText) {
    element.disabled = false;
    element.textContent = originalText;
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        validateForm,
        isValidEmail,
        isStrongPassword
    };
}
""")
        
        yield project_dir


class TestAPIProjectVerification:
    """Test API project verification with different strictness levels."""
    
    def test_complex_api_balanced_strictness(self, complex_api_project):
        template = create_template_for_project_type("api_endpoint", StrictnessLevel.BALANCED)
        result = evaluate_project_against_template(str(complex_api_project), template)
        
        # Should pass most balanced criteria
        assert result["success_rate"] >= 0.8
        assert result["overall_status"] == "PASS"
        
        # Check specific successful criteria
        passed_criteria = [c["name"] for c in result["criteria_results"] if c["passed"]]
        assert "API module exists" in passed_criteria
        assert "Routes module exists" in passed_criteria
        assert "Models defined" in passed_criteria
        assert "HTTP methods implemented" in passed_criteria
        assert "Error handling present" in passed_criteria
        assert "API tests exist" in passed_criteria
    
    def test_complex_api_strict_strictness(self, complex_api_project):
        template = create_template_for_project_type("api_endpoint", StrictnessLevel.STRICT)
        result = evaluate_project_against_template(str(complex_api_project), template)
        
        # Should pass all strict criteria for well-structured project
        assert result["success_rate"] >= 0.9
        assert result["overall_status"] == "PASS"
        
        # Check strict criteria
        passed_criteria = [c["name"] for c in result["criteria_results"] if c["passed"]]
        assert "Input validation" in passed_criteria
        assert "Authentication present" in passed_criteria
        assert "API documentation" in passed_criteria
    
    def test_incomplete_api_project(self, temp_project_dir):
        # Create minimal API project
        (temp_project_dir / "api.py").write_text("print('hello')")
        
        template = create_template_for_project_type("api_endpoint", StrictnessLevel.BALANCED)
        result = evaluate_project_against_template(str(temp_project_dir), template)
        
        # Should fail many criteria
        assert result["success_rate"] < 0.5
        assert result["overall_status"] == "FAIL"
        
        failed_criteria = [c["name"] for c in result["criteria_results"] if not c["passed"]]
        assert len(failed_criteria) > 0


class TestCLIProjectVerification:
    """Test CLI project verification."""
    
    def test_advanced_cli_balanced_strictness(self, advanced_cli_project):
        template = create_template_for_project_type("cli_tool", StrictnessLevel.BALANCED)
        result = evaluate_project_against_template(str(advanced_cli_project), template)
        
        # Should pass basic CLI criteria
        assert result["success_rate"] >= 0.6
        
        passed_criteria = [c["name"] for c in result["criteria_results"] if c["passed"]]
        assert "Main CLI file exists" in passed_criteria
        assert "Argument parser implemented" in passed_criteria
        assert "Help text available" in passed_criteria
        assert "Exit codes handled" in passed_criteria
    
    def test_advanced_cli_strict_strictness(self, advanced_cli_project):
        template = create_template_for_project_type("cli_tool", StrictnessLevel.STRICT)
        result = evaluate_project_against_template(str(advanced_cli_project), template)
        
        passed_criteria = [c["name"] for c in result["criteria_results"] if c["passed"]]
        assert "Subcommands implemented" in passed_criteria
        assert "Input validation" in passed_criteria
        assert "CLI tests exist" in passed_criteria


class TestLibraryProjectVerification:
    """Test library project verification."""
    
    def test_production_library_balanced_strictness(self, production_library_project):
        template = create_template_for_project_type("library", StrictnessLevel.BALANCED)
        result = evaluate_project_against_template(str(production_library_project), template)
        
        # Should pass all balanced criteria for production library
        assert result["success_rate"] >= 0.9
        assert result["overall_status"] == "PASS"
        
        passed_criteria = [c["name"] for c in result["criteria_results"] if c["passed"]]
        assert "Main module exists" in passed_criteria
        assert "Core functionality implemented" in passed_criteria
        assert "Docstrings present" in passed_criteria
        assert "Package structure" in passed_criteria
        assert "Tests exist" in passed_criteria
    
    def test_production_library_strict_strictness(self, production_library_project):
        template = create_template_for_project_type("library", StrictnessLevel.STRICT)
        result = evaluate_project_against_template(str(production_library_project), template)
        
        # Should pass all strict criteria
        assert result["success_rate"] >= 0.9
        assert result["overall_status"] == "PASS"
        
        passed_criteria = [c["name"] for c in result["criteria_results"] if c["passed"]]
        assert "Type hints" in passed_criteria
        assert "Setup file exists" in passed_criteria
        assert "Documentation exists" in passed_criteria


class TestWebAppProjectVerification:
    """Test web application project verification."""
    
    def test_full_stack_web_app_balanced_strictness(self, full_stack_web_app):
        template = create_template_for_project_type("web_app", StrictnessLevel.BALANCED)
        result = evaluate_project_against_template(str(full_stack_web_app), template)
        
        # Should pass all balanced criteria
        assert result["success_rate"] >= 0.9
        assert result["overall_status"] == "PASS"
        
        passed_criteria = [c["name"] for c in result["criteria_results"] if c["passed"]]
        assert "App entry point exists" in passed_criteria
        assert "Templates directory" in passed_criteria
        assert "Static files directory" in passed_criteria
        assert "Routes configured" in passed_criteria
        assert "HTML templates exist" in passed_criteria
    
    def test_full_stack_web_app_strict_strictness(self, full_stack_web_app):
        template = create_template_for_project_type("web_app", StrictnessLevel.STRICT)
        result = evaluate_project_against_template(str(full_stack_web_app), template)
        
        # Should pass all strict criteria
        assert result["success_rate"] >= 0.9
        assert result["overall_status"] == "PASS"
        
        passed_criteria = [c["name"] for c in result["criteria_results"] if c["passed"]]
        assert "CSS styles exist" in passed_criteria
        assert "JavaScript exists" in passed_criteria
        assert "Form validation" in passed_criteria


class TestCustomTemplateComposition:
    """Test custom template composition scenarios."""
    
    def test_microservice_template_composition(self, complex_api_project):
        """Test creating a microservice template by combining API and CLI templates."""
        composer = CriteriaComposer()
        
        api_template = composer.create_template("api_endpoint", StrictnessLevel.BALANCED)
        cli_template = composer.create_template("cli_tool", StrictnessLevel.BALANCED)
        
        microservice_template = composer.merge_templates(
            [api_template, cli_template],
            "Microservice Template",
            "API service with CLI management interface"
        )
        
        # Add CLI file to API project for testing
        (complex_api_project / "cli.py").write_text("""
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(help='API management CLI')
    args = parser.parse_args()
    sys.exit(0)

if __name__ == '__main__':
    main()
""")
        
        result = evaluate_project_against_template(str(complex_api_project), microservice_template)
        
        # Should validate both API and CLI criteria
        assert len(microservice_template.criteria) > 6  # More than just API criteria
        
        # Should pass API criteria
        api_criteria = [c for c in result["criteria_results"] if "API" in c["name"]]
        assert len(api_criteria) > 0
        
        # Should have CLI criteria
        cli_criteria = [c for c in result["criteria_results"] if "CLI" in c["name"]]
        assert len(cli_criteria) > 0
    
    def test_full_stack_template_composition(self, full_stack_web_app):
        """Test creating a full-stack template with web app + API."""
        composer = CriteriaComposer()
        
        web_template = composer.create_template("web_app", StrictnessLevel.BALANCED)
        api_template = composer.create_template("api_endpoint", StrictnessLevel.BALANCED)
        
        full_stack_template = composer.merge_templates(
            [web_template, api_template],
            "Full Stack Template",
            "Web application with API backend"
        )
        
        # Add API files to web app project
        (full_stack_web_app / "routes.py").write_text("""
@app.get('/api/users')
def get_users():
    return []
""")
        (full_stack_web_app / "models.py").write_text("""
class User:
    pass
""")
        
        result = evaluate_project_against_template(str(full_stack_web_app), full_stack_template)
        
        # Should validate both web and API criteria
        web_passed = [c for c in result["criteria_results"] 
                     if c["passed"] and ("template" in c["name"].lower() or "static" in c["name"].lower())]
        api_passed = [c for c in result["criteria_results"] 
                     if c["passed"] and ("API" in c["name"] or "route" in c["name"].lower())]
        
        assert len(web_passed) > 0
        assert len(api_passed) > 0


class TestBossAgentIntegrationScenarios:
    """Test boss agent integration with real project scenarios."""
    
    def test_boss_agent_feedback_generation(self, temp_project_dir):
        """Test boss agent feedback generation for failed projects."""
        composer = CriteriaComposer()
        integration = BossAgentIntegration(composer)
        
        # Create incomplete API project
        (temp_project_dir / "api.py").write_text("# Empty file")
        
        template = composer.create_template("api_endpoint", StrictnessLevel.STRICT)
        result = integration.evaluate_criteria_template(template, str(temp_project_dir))
        
        # Should fail and generate detailed feedback
        assert result["overall_status"] == "FAIL"
        
        feedback = integration.generate_failure_feedback(result)
        
        # Feedback should be detailed and actionable
        assert "API Endpoint Template" in feedback
        assert "failed verification" in feedback
        assert "Failed required criteria:" in feedback
        
        # Should list specific failures
        failed_criteria_names = [c["name"] for c in result["criteria_results"] if not c["passed"]]
        for criteria_name in failed_criteria_names[:3]:  # Check first few
            assert criteria_name in feedback
    
    def test_progressive_strictness_evaluation(self, production_library_project):
        """Test evaluating same project with increasing strictness."""
        composer = CriteriaComposer()
        integration = BossAgentIntegration(composer)
        
        strictness_levels = [StrictnessLevel.LENIENT, StrictnessLevel.BALANCED, StrictnessLevel.STRICT]
        results = []
        
        for strictness in strictness_levels:
            template = composer.create_template("library", strictness)
            result = integration.evaluate_criteria_template(template, str(production_library_project))
            results.append((strictness, result))
        
        # Should have increasing number of criteria with strictness
        lenient_criteria = len(results[0][1]["criteria_results"])
        balanced_criteria = len(results[1][1]["criteria_results"])
        strict_criteria = len(results[2][1]["criteria_results"])
        
        assert balanced_criteria >= lenient_criteria
        assert strict_criteria >= balanced_criteria
        
        # Production library should pass all levels
        for strictness, result in results:
            assert result["overall_status"] == "PASS", f"Failed at {strictness.value} level"


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


if __name__ == "__main__":
    pytest.main([__file__])