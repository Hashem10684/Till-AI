"""A local stand-in for Groq's API, so the real SDK path can be exercised without a key."""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = sys.argv[2] if len(sys.argv) > 2 else None
REVIEW = {
    "summary": "You are selling more, but thrift prices are climbing and your prices have not moved. That is why it feels like you are not making more.",
    "strengths": [{"point": "Demand is growing", "evidence": "Sales rose against the previous period."}],
    "weaknesses": [{"point": "The custom tote barely pays", "evidence": "It earns a very thin margin."}],
    "opportunities": [{"point": "Raise your prices", "evidence": "Prices have not moved while costs rose."}],
    "threats": [{"point": "Reliance on one bulk buyer", "evidence": "Campus Store is a large share of sales."}],
    "actions": [
        {"title": "Raise tee prices by $3", "why": "Your sourcing costs rose and your prices did not.", "first_step": "Change your next 10 Depop listings tonight.", "priority": "High"},
        {"title": "Fix or drop the custom tote", "why": "It takes hours and leaves about $2 each.", "first_step": "Find a cheaper blank tote.", "priority": "High"},
        {"title": "Call the three quiet regulars", "why": "They stopped buying two months ago.", "first_step": "DM Aisha, Ethan and Sofia today.", "priority": "Medium"}],
    "unknowns": ["Whether Campus Store pays on time, because no payment dates are recorded."],
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if LOG:
            with open(LOG, "a") as f:
                f.write(json.dumps({"model": body["model"], "stream": body.get("stream"), "format": (body.get("response_format") or {}).get("type"), "chars": sum(len(m["content"]) for m in body["messages"])}) + "\n")
        if self.headers.get("Authorization") == "Bearer bad":
            self.send_response(401); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(b'{"error":{"message":"invalid key"}}')
            return
        if body["model"] == sys.argv[1]:
            self.send_response(404); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(b'{"error":{"message":"model not found","code":"model_not_found"}}')
            return
        if body.get("stream"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            for word in "Your profit is shrinking because costs rose faster than prices. A tee at $22 and a hoodie at $38 both need a price check.".split(" "):
                chunk = {"id": "x", "object": "chat.completion.chunk", "created": 1, "model": body["model"],
                         "choices": [{"index": 0, "delta": {"content": word + " "}, "finish_reason": None}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            return
        reply = {"id": "x", "object": "chat.completion", "created": 1, "model": body["model"],
                 "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(REVIEW)}}],
                 "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(reply).encode())


ThreadingHTTPServer(("127.0.0.1", 8799), Handler).serve_forever()
