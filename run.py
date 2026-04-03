import os
from app import create_app, celery, db

env = os.environ.get('FLASK_ENV', 'dev')
if env == 'development':
    env = 'dev'

# 1. Initialize the app
app = create_app(env)

# 2. Export the configured celery object for the worker
# celery -A run.celery worker
celery = celery

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
