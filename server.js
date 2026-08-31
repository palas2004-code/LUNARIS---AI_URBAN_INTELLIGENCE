const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = parseInt(process.env.PORT, 10) || 8080;
const ROOT_DIR = __dirname;
const SEARCH_DIRS = [
  path.join(ROOT_DIR, 'frontend'),
  path.join(ROOT_DIR, 'live-camera'),
  ROOT_DIR
];

const MIME_TYPES = {
  '.html': 'text/html; charset=UTF-8',
  '.js': 'application/javascript; charset=UTF-8',
  '.css': 'text/css; charset=UTF-8',
  '.json': 'application/json; charset=UTF-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf'
};

function resolveFilePath(reqPath) {
  let cleanPath = reqPath.split('?')[0];
  if (cleanPath === '/' || cleanPath === '') cleanPath = '/index.html';
  if (cleanPath === '/live-monitoring') cleanPath = '/live_monitoring.html';
  if (cleanPath === '/mobile-camera') cleanPath = '/mobile_camera.html';

  const safePath = path.normalize(cleanPath).replace(/^(\.\.[\/\\])+/, '');

  for (const baseDir of SEARCH_DIRS) {
    const candidate = path.join(baseDir, safePath);
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
      return candidate;
    }
  }
  return null;
}

const server = http.createServer((req, res) => {
  // Enable Universal CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  const parsedUrl = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const reqPath = parsedUrl.pathname;

  // 1. Health API Endpoint
  if (reqPath === '/api/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      status: 'ONLINE',
      service: 'LUNARIS Web Server',
      port: PORT,
      structure: 'modular (frontend, backend, ai-detection, live-camera, database-supabase, main)',
      timestamp: new Date().toISOString()
    }));
    return;
  }

  // 2. Config API Endpoint
  if (reqPath === '/api/config') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      supabaseUrl: 'https://ecmtwoccsdlhphdlutmz.supabase.co',
      supabaseKey: 'sb_publishable_l4l1lR2MLi_WOwtjs4CxTw_yBjCx01G',
      projectRef: 'ecmtwoccsdlhphdlutmz'
    }));
    return;
  }

  // 3. Static Asset Resolution across Modular Directories
  const targetFile = resolveFilePath(reqPath);

  if (!targetFile) {
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end(`404 Not Found: ${reqPath}`);
    return;
  }

  const ext = path.extname(targetFile).toLowerCase();
  const contentType = MIME_TYPES[ext] || 'application/octet-stream';

  res.writeHead(200, { 'Content-Type': contentType });
  const stream = fs.createReadStream(targetFile);
  stream.pipe(res);
});

server.listen(PORT, () => {
  console.log(`[LUNARIS HTTP] Server running at http://localhost:${PORT}/ (Modular structure active)`);
});
