# wsgi.py
from urllib.parse import quote

class ClosingIterator:
    def __init__(self, iterable, callbacks=None):
        self.iterable = iterable
        self.callbacks = callbacks or []

    def __iter__(self):
        return iter(self.iterable)

    def close(self):
        for callback in self.callbacks:
            try:
                callback()
            except Exception:
                pass

def get_current_url(environ, root_only=False, strip_querystring=False):
    """WSGI環境から現在のURLを組み立てる関数"""
    scheme = environ.get('wsgi.url_scheme', 'http')
    host = environ.get('HTTP_HOST')
    if not host:
        server_name = environ.get('SERVER_NAME')
        server_port = environ.get('SERVER_PORT')
        host = f"{server_name}:{server_port}"

    url = f"{scheme}://{host}"
    if root_only:
        return url + '/'

    # SCRIPT_NAME と PATH_INFO を組み合わせてパスを作成
    path = quote(environ.get('SCRIPT_NAME', ''))
    path += quote(environ.get('PATH_INFO', ''))
    url += path

    if not strip_querystring:
        qs = environ.get('QUERY_STRING', '')
        if qs:
            url += '?' + qs

    return url
