# ABOUTME: Gunicorn configuration for production deployment
# ABOUTME: Sets worker timeout and binding settings for the Flask app

import multiprocessing

# Bind to all interfaces on port 8080
bind = "0.0.0.0:8080"

# Number of worker processes
workers = multiprocessing.cpu_count() * 2 + 1

# Worker timeout in seconds - set high to allow full stock screening to complete
# Stock screening can take several hours to process thousands of stocks
timeout = 28800  # 8 hours

# Worker class
worker_class = "sync"

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
