#!/usr/bin/env bash

# Start the Celery worker in the background
echo "Starting Celery worker..."
celery -A run.celery worker --loglevel=info &

# Start the Gunicorn web server in the foreground
echo "Starting Gunicorn web server..."
# Using the standard gunicorn configuration
gunicorn -c gunicorn_config.py run:app

# Wait for background processes to finish (optional but good for signal propagation)
wait -n
exit $?
