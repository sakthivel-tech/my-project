import gevent.monkey
gevent.monkey.patch_all()

import os
from app import create_app, db

env = os.environ.get('FLASK_ENV', 'dev')
if env == 'development':
    env = 'dev'
app = create_app(env)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
