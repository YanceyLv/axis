const http = require("http");
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "dist");
const port = Number(process.env.PORT || 5173);

const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".json": "application/json; charset=utf-8",
};

function proxyApi(req, res) {
  const proxy = http.request(
    {
      hostname: "127.0.0.1",
      port: 8000,
      path: req.url,
      method: req.method,
      headers: req.headers,
    },
    (apiRes) => {
      res.writeHead(apiRes.statusCode || 500, apiRes.headers);
      apiRes.pipe(res);
    }
  );

  proxy.on("error", () => {
    res.writeHead(502, { "Content-Type": "application/json; charset=utf-8" });
    res.end(JSON.stringify({ code: "api_unavailable", message: "API server unavailable" }));
  });

  req.pipe(proxy);
}

function serveFile(req, res) {
  const urlPath = decodeURIComponent((req.url || "/").split("?")[0]);
  const safePath = path.normalize(urlPath).replace(/^(\.\.[/\\])+/, "");
  let filePath = path.join(root, safePath === "/" ? "index.html" : safePath);

  if (!filePath.startsWith(root)) {
    res.writeHead(403);
    res.end("Forbidden");
    return;
  }

  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    filePath = path.join(root, "index.html");
  }

  const ext = path.extname(filePath);
  res.writeHead(200, { "Content-Type": types[ext] || "application/octet-stream" });
  fs.createReadStream(filePath).pipe(res);
}

http
  .createServer((req, res) => {
    if ((req.url || "").startsWith("/api/")) {
      proxyApi(req, res);
      return;
    }
    serveFile(req, res);
  })
  .listen(port, "127.0.0.1", () => {
    console.log(`TrendAI frontend listening on http://127.0.0.1:${port}`);
  });
