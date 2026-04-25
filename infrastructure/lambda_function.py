"""AWS Lambda function for receiving log uploads from StormFuse.

Two-step protocol:
  POST /logs/upload   — validate, generate upload UUID, return presigned S3 PUT URLs
  POST /logs/complete — list uploaded files, send SES notification email
"""

import json
import os
import re
import uuid
from datetime import UTC, datetime

import boto3

s3 = boto3.client('s3')
ses = boto3.client('ses')

BUCKET_NAME = os.environ['BUCKET_NAME']
NOTIFY_EMAIL = os.environ.get('NOTIFY_EMAIL', 'morgan@windsofstorm.net')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'morgan@windsofstorm.net')
MIN_SUPPORTED_VERSION = '1.0.0'

# Presigned PUT URLs expire after one hour — enough for any reasonable upload.
_PRESIGN_EXPIRES = 3600


def _parse_semver(version_text: str) -> tuple[int, int, int] | None:
    match = re.match(r'^\s*v?(\d+)\.(\d+)\.(\d+)', str(version_text))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _is_supported_version(app_version: str, min_supported_version: str) -> bool:
    app_tuple = _parse_semver(app_version)
    min_tuple = _parse_semver(min_supported_version)
    if app_tuple is None or min_tuple is None:
        return False
    return app_tuple >= min_tuple


def lambda_handler(event, context):
    raw_path = event.get('rawPath', '')
    http_ctx = event.get('requestContext', {}).get('http', {})
    method = http_ctx.get('method', event.get('httpMethod', ''))

    if method == 'OPTIONS':
        return _cors_response(200, {'message': 'OK'})

    if raw_path == '/logs/upload' and method == 'POST':
        return _handle_init(event)

    if raw_path == '/logs/complete' and method == 'POST':
        return _handle_complete(event)

    return _cors_response(404, {'message': 'Not found'})


# ── /logs/upload — init ────────────────────────────────────────────────────


def _handle_init(event: dict) -> dict:
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return _cors_response(400, {'success': False, 'message': 'Invalid JSON body'})

    if not body.get('user_notes'):
        return _cors_response(
            400, {'success': False, 'message': 'Missing required field: user_notes'}
        )

    app_version = body.get('app_version', 'unknown')
    if not _is_supported_version(app_version, MIN_SUPPORTED_VERSION):
        return _cors_response(
            426,
            {
                'success': False,
                'error_code': 'LOG-CLIENT-TOO-OLD',
                'message': (
                    'App version too old for log submission. '
                    'Please upgrade, reproduce the issue, and retest before sending logs.'
                ),
                'min_supported_version': MIN_SUPPORTED_VERSION,
                'app_version': app_version,
            },
        )

    upload_id = str(uuid.uuid4())
    filenames: list[str] = [str(f) for f in body.get('filenames', []) if f]

    presigned_urls = []
    for filename in filenames:
        key = f'{upload_id}/{filename}.gz'
        url = s3.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': BUCKET_NAME,
                'Key': key,
                'ContentType': 'application/gzip',
            },
            ExpiresIn=_PRESIGN_EXPIRES,
        )
        presigned_urls.append({'filename': filename, 'url': url})

    return _cors_response(
        200,
        {
            'upload_id': upload_id,
            'presigned_urls': presigned_urls,
        },
    )


# ── /logs/complete — finish ────────────────────────────────────────────────


def _handle_complete(event: dict) -> dict:
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return _cors_response(400, {'success': False, 'message': 'Invalid JSON body'})

    upload_id = body.get('upload_id', '').strip()
    if not upload_id:
        return _cors_response(
            400, {'success': False, 'message': 'Missing required field: upload_id'}
        )

    app_version = body.get('app_version', 'unknown')
    user_notes = body.get('user_notes', '')
    hostname = body.get('hostname', '')
    username = body.get('username', '')
    os_version = body.get('os_version', '')
    os_platform = body.get('os_platform', '')
    encoder = body.get('encoder', 'unknown')
    timestamp = datetime.now(UTC).strftime('%Y%m%d_%H%M%S')
    os_display = hostname or os_platform or 'Unknown host'

    # List what actually landed in S3 for this upload.
    paginator = s3.get_paginator('list_objects_v2')
    uploaded_files: list[str] = []
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=f'{upload_id}/'):
        for obj in page.get('Contents', []):
            uploaded_files.append(obj['Key'].removeprefix(f'{upload_id}/'))

    file_list = '\n'.join(f'  - {f}' for f in sorted(uploaded_files)) or '  (none)'

    email_body = (
        f'New diagnostic log submission from StormFuse.\n\n'
        f'Upload ID:   {upload_id}\n'
        f'Timestamp:   {timestamp}\n'
        f'App Version: {app_version}\n'
        f'Encoder:     {encoder}\n'
        f'Hostname:    {hostname}\n'
        f'Username:    {username}\n'
        f'OS Version:  {os_version}\n'
        f'OS Platform: {os_platform}\n\n'
        f'User Notes:\n{user_notes}\n\n'
        f'Uploaded files (gzip-compressed in S3):\n{file_list}\n\n'
        f'To download and decompress:\n'
        f'  ./infrastructure/download_logs.sh {upload_id}\n'
    )

    try:
        ses.send_email(
            Source=SENDER_EMAIL,
            Destination={'ToAddresses': [NOTIFY_EMAIL]},
            Message={
                'Subject': {
                    'Data': f'[StormFuse] Logs: {upload_id} from {os_display}',
                    'Charset': 'UTF-8',
                },
                'Body': {'Text': {'Data': email_body, 'Charset': 'UTF-8'}},
            },
        )
    except Exception as e:
        print(f'SES email failed: {e}')

    return _cors_response(200, {'success': True, 'upload_id': upload_id})


# ── helpers ────────────────────────────────────────────────────────────────


def _cors_response(status_code: int, body: dict) -> dict:
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
        },
        'body': json.dumps(body),
    }
