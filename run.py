import os
from app import create_app, celery, db

env = os.environ.get('FLASK_ENV', 'dev')
if env == 'development':
    env = 'dev'
app = create_app(env)
# The celery object in app is now configured due to create_app() calling CELERY_CONF.update

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
