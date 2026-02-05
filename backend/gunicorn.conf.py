# ABOUTME: Gunicorn configuration for production deployment
# ABOUTME: Sets worker timeout and binding settings for the Flask app

import multiprocessing

# Bind to all interfaces on port 8080
bind = "0.0.0.0:8080"

# Number of worker processes
# Number of worker processes
# Using 2 workers to provide redundancy and better CPU utilization
# Each worker is estimated to use ~600MB RAM (Pandas/AI models)
# 2 workers * 600MB = 1.2GB, leaving safety buffer for 2GB machine
workers = 2

# Worker timeout in seconds - set high to allow full stock screening to complete
# Stock screening can take several hours to process thousands of stocks
timeout = 28800  # 8 hours

# Worker class
worker_class = "gthread"
threads = 10


# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
