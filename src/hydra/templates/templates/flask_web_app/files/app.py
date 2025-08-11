"""App module."""

from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy

{% if auth_enabled %}from flask_login import LoginManager, login_required{% endif %}
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

{% if database == 'sqlite' %}
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///{{project_name}}.db'
{% elif database == 'postgresql' %}
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://user:pass@localhost/{{project_name}}')
{% elif database == 'mysql' %}
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'mysql://user:pass@localhost/{{project_name}}')
{% endif %}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

{% if auth_enabled %}
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

from models import User


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
{% endif %}

@app.route('/')
def index():
    return render_template('index.html', project_name='{{project_name}}')

@app.route('/api/health')
def health():
    return jsonify({'status': 'healthy', 'service': '{{project_name}}'})

{% if auth_enabled %}
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')
{% endif %}

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)