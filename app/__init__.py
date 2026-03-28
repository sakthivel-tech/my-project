from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from .config import config_by_name
from .models import db, User

login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
talisman = Talisman()


def create_app(config_name='prod'):
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    
    csp = {
        'default-src': ['\'self\''],
        'script-src': ['\'self\'', '\'unsafe-inline\''],
        'style-src': ['\'self\'', '\'unsafe-inline\'', 'https://fonts.googleapis.com'],
        'font-src': ['\'self\'', 'https://fonts.gstatic.com'],
        'img-src': ['\'self\'', 'data:', 'https:']
    }
    talisman.init_app(app, content_security_policy=csp)

    # Ensure database tables exist automatically in production servers (Render/Gunicorn)
    import os
    instance_path = os.path.join(os.getcwd(), 'instance')
    if not os.path.exists(instance_path):
        os.makedirs(instance_path, exist_ok=True)

    with app.app_context():
        db.create_all()

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(user_id)

    from .routes.auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from .routes.main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .routes.download import download_bp as download_blueprint
    app.register_blueprint(download_blueprint)

    from flask import jsonify
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return jsonify(error=f"Rate limit exceeded: {e.description}"), 429

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        return jsonify(error="Security token expired. Please refresh the page and try again."), 400

    return app
