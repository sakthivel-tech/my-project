import gevent.monkey
gevent.monkey.patch_all()

import multiprocessing
import os

# Binding
bind = "0.0.0.0:" + os.environ.get("PORT", "10000")

# Worker configuration
# Using gevent or eventlet is better for long-running streaming connections
worker_class = 'gevent'
workers = 2  # Hardcoded low worker count to prevent OOM on Render Starter
worker_connections = 1000

# Timeouts
# Increased timeout to handle large video processing/streaming
timeout = 600 
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
