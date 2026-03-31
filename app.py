import os
import re
import uuid
import boto3
import logging
from datetime import datetime
from dotenv import load_dotenv
from botocore.exceptions import BotoCoreError, ClientError
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

load_dotenv()

# Configure logging
log_dir = 'logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_filename = os.path.join(log_dir, f'storage_service_{datetime.now().strftime("%Y%m%d")}.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
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
        logger.warning('S3 configuration incomplete. Missing required environment variables.')
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
    return bool(UUID_FILENAME_PATTERN.match(filename))


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

def build_storage_filename(original_filename):
    safe_name = secure_filename(original_filename or '')
    ext = ''
    if '.' in safe_name:
        ext = safe_name.rsplit('.', 1)[1].lower()

    if not ext:
        ext = 'bin'

    # Keep extension URL-safe and stable for generated UUID filenames.
    ext = re.sub(r'[^a-z0-9]', '', ext)
    if not ext:
        ext = 'bin'

    return f"{uuid.uuid4()}.{ext}"

@app.route('/')
def index():
    logger.info('Index endpoint accessed')
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
    logger.info('API info endpoint accessed from %s', request.remote_addr)
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
            'allowed_types': ['*'],
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
                'description': 'Upload any file type (video, audio, documents, images, archives, etc.) up to 50MB',
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
    logger.warning('File too large error from %s', request.remote_addr)
    return jsonify({'error': 'File too large. Maximum size is 50MB'}), 413


@app.route('/api/upload', methods=['POST'])
@app.route('/upload', methods=['POST'])
def upload_file():
    client_ip = request.remote_addr
    
    if 'file' not in request.files:
        logger.warning('Upload request from %s missing file field', client_ip)
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        logger.warning('Upload request from %s with empty filename', client_ip)
        return jsonify({'error': 'No file selected'}), 400

    config = get_s3_config()
    s3_client = get_s3_client()
    if not config or not s3_client:
        logger.error('Upload from %s failed - S3 configuration missing', client_ip)
        return jsonify({'error': 'S3 configuration is missing'}), 500

    # Generate unique UUID filename while preserving a safe extension when present.
    unique_filename = build_storage_filename(file.filename)
    object_key = s3_object_key(unique_filename)
    file_size = len(file.read()) if hasattr(file, 'read') else 0
    file.seek(0)

    logger.info('Upload started from %s - Original filename: %s, Generated: %s, Size: %d bytes, Type: %s',
                client_ip, file.filename, unique_filename, file_size, file.content_type or 'unknown')

    try:
        file.stream.seek(0)
        s3_client.upload_fileobj(
            Fileobj=file.stream,
            Bucket=config['bucket_name'],
            Key=object_key,
            ExtraArgs={'ContentType': file.content_type or 'application/octet-stream'},
        )
        logger.info('Upload completed successfully - Filename: %s, to S3 key: %s', unique_filename, object_key)
    except (BotoCoreError, ClientError) as e:
        logger.error('S3 upload failed for %s from %s: %s', unique_filename, client_ip, str(e))
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
    client_ip = request.remote_addr
    logger.info('File access request from %s - filename: %s', client_ip, filename)
    
    signed_url, error = generate_presigned_url(filename)
    if error == 'Invalid filename':
        logger.warning('Invalid filename requested from %s: %s', client_ip, filename)
        return jsonify({'error': 'Invalid filename'}), 400
    if error:
        logger.error('Failed to generate presigned URL for %s from %s: %s', filename, client_ip, error)
        return jsonify({'error': error}), 500

    logger.info('Presigned URL generated and redirecting for filename: %s', filename)
    return redirect(signed_url, code=302)

@app.route('/images/<filename>')
def serve_image_redirect(filename):
    """Redirect old /images/ URLs to /files/ for backward compatibility."""
    logger.info('Legacy /images/ endpoint accessed from %s - filename: %s', request.remote_addr, filename)
    return redirect(f"/files/{filename}", code=302)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    logger.info('Starting Image & File Hosting Service on port %d', port)
    app.run(host='0.0.0.0', port=port, debug=False)
