#!/usr/bin/env python3
"""
MakeIt Labs Class Board - Local Dev Server & CLI Runner
Thin HTTP server to test and serve classes.cgi in development environments.
Can also export static HTML or force cache refreshes.
"""

import os
import sys
import argparse
import http.server
import socketserver
import urllib.parse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

def get_classes_module():
    try:
        import importlib.util
        from importlib.machinery import SourceFileLoader
        cgi_path = os.path.join(SCRIPT_DIR, "classes.cgi")
        loader = SourceFileLoader("classes_cgi", cgi_path)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return mod
    except Exception:
        import classes as classes_cgi
        return classes_cgi

classes_cgi = get_classes_module()


class ClassBoardHTTPHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        force_refresh = "refresh" in query or "1" in query.get("refresh", [])

        # Serve classes page for root
        if path in ("/", "/index.html", "/classes", "/classes.cgi"):
            try:
                mod = get_classes_module()
                html = mod.render_classes_page(force_refresh=force_refresh)
                content = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                err_html = f"<h1>Error rendering classes</h1><pre>{e}</pre>".encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(err_html)))
                self.end_headers()
                self.wfile.write(err_html)
            return

        # Serve static assets if requested
        if path.startswith("/static/"):
            rel_path = path[len("/static/"):]
            local_file = os.path.join(SCRIPT_DIR, "..", "static", rel_path)
            if os.path.exists(local_file) and os.path.isfile(local_file):
                mime = "application/octet-stream"
                if local_file.endswith(".svg"):
                    mime = "image/svg+xml"
                elif local_file.endswith(".png"):
                    mime = "image/png"
                elif local_file.endswith(".css"):
                    mime = "text/css"
                elif local_file.endswith(".js"):
                    mime = "application/javascript"

                with open(local_file, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

        # Fallback 404 or redirect
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        self.send_response(302)
        self.send_header("Location", "/")
        self.end_headers()

    def log_message(self, format, *args):
        # Format log cleanly
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")


def run_server(port=8080):
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), ClassBoardHTTPHandler) as httpd:
        print("=" * 64)
        print(f"MakeIt Labs Class Board Dev Server")
        print(f"Serving at: http://127.0.0.1:{port}")
        print(f"Testing classes.cgi with live Eventbrite data & responsive layout")
        print(f"Press Ctrl+C to stop.")
        print("=" * 64)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down dev server...")
        finally:
            httpd.server_close()


def main():
    parser = argparse.ArgumentParser(description="MakeIt Labs Class Board Server & Runner")
    parser.add_argument("port", nargs="?", type=int, default=8080, help="Port to serve on (default: 8080)")
    parser.add_argument("--serve", action="store_true", help="Start development HTTP server")
    parser.add_argument("--refresh", action="store_true", help="Force refresh Eventbrite cache")
    parser.add_argument("--output", type=str, help="Render HTML directly to an output file")

    args = parser.parse_args()

    if args.output:
        html = classes_cgi.render_classes_page(force_refresh=args.refresh)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Successfully generated {args.output}")
        return

    if args.refresh and not args.serve:
        classes_cgi.fetch_events_from_eventbrite(force_refresh=True)
        print("Eventbrite classes cache refreshed successfully.")
        return

    # Default action: run HTTP server
    run_server(port=args.port)


if __name__ == "__main__":
    main()
