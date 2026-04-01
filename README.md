# Image & File Hosting Service

A simple, lossless file hosting service with a Flask backend and React frontend. Exposeable REST API for uploads and retrieval.

## Features
- Upload any file type and get shareable URLs
- Lossless storage (original quality preserved)
- No authentication required
- Public access for all files
- **Exposeable API**: `GET /api` for discovery, `POST /api/upload` for uploads
- Support for all file formats (including video, audio, documents, images, and archives)
- Max file size: 50MB

## Project Structure
```
imageServer/
├── app.py                  # Flask backend
├── requirements.txt        # Python dependencies
├── Procfile               # Railway deployment config
├── railway.json           # Railway configuration
├── runtime.txt            # Python version
├── RAILWAY_DEPLOY.md      # Backend deployment guide
├── VERCEL_DEPLOY.md       # Frontend deployment guide
└── frontend/
    ├── index.html         # Main page
    ├── style.css          # Styling
    ├── script.js          # Upload logic
    └── vercel.json        # Vercel configuration
```

## Local Development

### Backend
```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
python app.py
```
Backend runs on `http://localhost:5000`

### Frontend
Open `frontend/index.html` in a browser, or use a local server:
```bash
cd frontend
python -m http.server 8000
```
Frontend available at `http://localhost:8000`

**Important**: Update `API_URL` in `frontend/script.js` to point to your backend URL.

## Deployment

### Backend (Railway)
See [RAILWAY_DEPLOY.md](RAILWAY_DEPLOY.md) for detailed instructions.

### Frontend (Vercel)
See [VERCEL_DEPLOY.md](VERCEL_DEPLOY.md) for detailed instructions.

## How It Works
1. User uploads any file via the frontend (or any client via the API)
2. Client sends the file to `POST /upload` or `POST /api/upload`
3. Backend saves the file with a unique UUID filename
4. Backend returns a public URL
5. User can share the URL; files are served via `GET /files/<filename>` (old `/images/<filename>` URLs redirect to `/files/` for backward compatibility)

## Exposeable API

External clients can use the API without the web UI.

### `GET /api`
API discovery: returns endpoints, allowed types, and usage.

**Response** (example):
```json
{
  "name": "Image & File Hosting API",
  "version": "1.1",
  "base_url": "https://your-backend.railway.app",
  "endpoints": {
    "upload": { "method": "POST", "path": "/api/upload", ... },
    "get_file": { "method": "GET", "path": "/files/<filename>", ... }
  },
  "allowed_types": ["*"]
}
```

### `POST /api/upload` or `POST /upload`
Upload any file type.

**Request**: `multipart/form-data` with `file` field (max 50MB)

**Response**:
```json
{
  "success": true,
  "url": "https://your-backend.railway.app/files/abc123.pdf",
  "filename": "abc123.pdf"
}
```

### `GET /files/<filename>`
Retrieve any uploaded file.

**Response**: File with appropriate `Content-Type`

### `GET /images/<filename>` (legacy)
Redirects to `/files/<filename>`. Kept so old shared links still work.

## Environment Variables

### Backend
- `PORT` - Port to run the server (automatically set by Railway)
- `UPLOAD_FOLDER` - Directory to store uploads (set to `/app/uploads` on Railway)
- `S3_OBJECT_PREFIX` - Optional S3 folder/prefix for new uploads (default: `compliance`). Reads stay backward-compatible with existing `compliance/` objects.

## Notes
- Files are stored with no conversion (lossless/original)
- Files are renamed with UUID to prevent conflicts
- CORS is enabled for all origins
- Railway volumes ensure persistent storage across deployments
- Use `GET /api` from scripts or tools to discover the API programmatically
