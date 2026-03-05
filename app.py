import os
import re
import uuid
import boto3
from dotenv import load_dotenv
from botocore.exceptions import BotoCoreError, ClientError
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = {
    'png', 'jpg', 'jpeg', 'jfif', 'pjpeg', 'pjp',
    'gif', 'webp', 'avif', 'svg', 'bmp', 'ico',
    'tif', 'tiff', 'heic', 'heif', 'pdf'
}
SIGNED_URL_EXPIRATION = 600  # 10 minutes

app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

UUID_FILENAME_PATTERN = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\.[A-Za-z0-9]+$'
)


def get_s3_config():
    aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    aws_region = os.environ.get('AWS_REGION')
    bucket_name = os.environ.get('S3_BUCKET_NAME')

    if not all([aws_access_key_id, aws_secret_access_key, aws_region, bucket_name]):
        return None

    return {
        'aws_access_key_id': aws_access_key_id,
        'aws_secret_access_key': aws_secret_access_key,
        'aws_region': aws_region,
        'bucket_name': bucket_name,
    }


def get_s3_client():
    config = get_s3_config()
    if not config:
        return None

    return boto3.client(
        's3',
        aws_access_key_id=config['aws_access_key_id'],
        aws_secret_access_key=config['aws_secret_access_key'],
        region_name=config['aws_region'],
    )


def is_valid_storage_filename(filename):
    if not filename or '/' in filename or '\\' in filename:
        return False
    if not UUID_FILENAME_PATTERN.match(filename):
        return False

    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def s3_object_key(filename):
    return f"compliance/{filename}"


def generate_presigned_url(filename):
    if not is_valid_storage_filename(filename):
        return None, 'Invalid filename'

    config = get_s3_config()
    s3_client = get_s3_client()
    if not config or not s3_client:
        return None, 'S3 configuration is missing'

    try:
        signed_url = s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': config['bucket_name'],
                'Key': s3_object_key(filename),
            },
            ExpiresIn=SIGNED_URL_EXPIRATION,
        )
        return signed_url, None
    except (BotoCoreError, ClientError):
        return None, 'Failed to generate signed URL'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return jsonify({
        'message': 'Image & file hosting service is running',
        'api': '/api',
        'endpoints': {
            'upload': 'POST /upload or POST /api/upload',
            'view': 'GET /files/<filename>'
        }
    })



# --- Exposeable API ---

@app.route('/api')
def api_info():
    """API discovery and documentation for external clients."""
    base = request.host_url.rstrip('/')
    return jsonify({
        'name': 'Image & File Hosting API',
        'version': '1.4',
        'base_url': base,
        'storage': {
            'provider': 'aws_s3',
            'bucket_visibility': 'private',
            'path_format': 'compliance/<uuid>.<ext>',
            'access_pattern': 'pre-signed URL only',
            'signed_url_ttl_seconds': SIGNED_URL_EXPIRATION,
        },
        'limits': {
            'max_file_size_mb': 50,
            'allowed_types': sorted(ALLOWED_EXTENSIONS),
        },
        'required_env_vars': [
            'AWS_ACCESS_KEY_ID',
            'AWS_SECRET_ACCESS_KEY',
            'AWS_REGION',
            'S3_BUCKET_NAME',
        ],
        'endpoints': {
            'upload_api': {
                'method': 'POST',
                'path': '/api/upload',
                'description': 'Upload an image (PNG, JPG, JPEG, JFIF, PJPEG, PJP, GIF, WebP, AVIF, SVG, BMP, ICO, TIF, TIFF, HEIC, HEIF) or PDF',
                'request': 'multipart/form-data with field "file"',
                'response': {
                    'success': True,
                    'filename': '<uuid>.<ext>',
                    'url': '<base_url>/files/<uuid>.<ext>'
                }
            },
            'upload_legacy': {
                'method': 'POST',
                'path': '/upload',
                'description': 'Legacy alias for /api/upload',
                'request': 'multipart/form-data with field "file"',
                'response': {
                    'success': True,
                    'filename': '<uuid>.<ext>',
                    'url': '<base_url>/files/<uuid>.<ext>'
                }
            },
            'get_file_signed_json': {
                'method': 'GET',
                'path': '/files/<filename>',
                'description': 'Redirect to a 10-minute pre-signed URL for an uploaded file',
                'response': '302 redirect to S3 pre-signed URL'
            }
        }
    })


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(_error):
    return jsonify({'error': 'File too large. Maximum size is 50MB'}), 413


@app.route('/api/upload', methods=['POST'])
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400

    config = get_s3_config()
    s3_client = get_s3_client()
    if not config or not s3_client:
        return jsonify({'error': 'S3 configuration is missing'}), 500

    # Generate unique filename
    ext = secure_filename(file.filename).rsplit('.', 1)[1].lower()
    unique_filename = f"{uuid.uuid4()}.{ext}"
    object_key = s3_object_key(unique_filename)

    try:
        file.stream.seek(0)
        s3_client.upload_fileobj(
            Fileobj=file.stream,
            Bucket=config['bucket_name'],
            Key=object_key,
            ExtraArgs={'ContentType': file.content_type or 'application/octet-stream'},
        )
    except (BotoCoreError, ClientError):
        return jsonify({'error': 'Failed to upload file to S3'}), 502

    base_url = request.host_url.rstrip('/')
    file_url = f"{base_url}/files/{unique_filename}"

    return jsonify({
        'success': True,
        'url': file_url,
        'filename': unique_filename
    }), 201


@app.route('/files/<filename>')
def serve_file(filename):
    """Redirect to a temporary signed URL for any uploaded file."""
    signed_url, error = generate_presigned_url(filename)
    if error == 'Invalid filename':
        return jsonify({'error': 'Invalid filename'}), 400
    if error:
        return jsonify({'error': error}), 500

    return redirect(signed_url, code=302)

@app.route('/images/<filename>')
def serve_image_redirect(filename):
    """Redirect old /images/ URLs to /files/ for backward compatibility."""
    return redirect(f"/files/{filename}", code=302)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)