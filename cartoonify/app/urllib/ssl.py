import ssl
import certifi
from urllib import request

def create_ssl_context():
    return ssl.create_default_context(cafile=certifi.where())

# SSL fix for some misconfigured devices.
ssl._create_default_https_context = create_ssl_context

def urlretrieve(url, path):
    request.urlretrieve(url, path)