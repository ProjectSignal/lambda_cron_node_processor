import gzip
import time
import boto3
import logging
import sys
from botocore.exceptions import ClientError

from config import config
from logging_config import setup_logger

# Initialize logger for this module
logger = setup_logger(__name__)


def setup_r2_client():
    """Create R2 client with Lambda-optimized settings"""
    return boto3.client(
        's3',
        region_name=config.R2_REGION,
        aws_access_key_id=config.R2_ACCESS_KEY_ID,
        aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
        endpoint_url=config.R2_ENDPOINT_URL,
        config=boto3.session.Config(
            retries={'max_attempts': 3},
            max_pool_connections=5
        )
    )


def download_file_from_r2(r2_client, html_path, max_retries=3, initial_backoff=0.5):
    """
    Download file from R2 with Lambda-optimized retry logic
    Modified from processors/common/utils.py to accept r2_client parameter
    NOTE: This function is deprecated. Use the async version in processor.py instead.
    """
    bucket_name = config.R2_BUCKET_NAME
    retry_count = 0
    last_exception = None
    
    while retry_count < max_retries:
        try:
            logger.info(f"Downloading file: {bucket_name}/{html_path}")
            
            # First check if the file exists
            try:
                r2_client.head_object(Bucket=bucket_name, Key=html_path)
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    logger.warning(f"File does not exist: {html_path}")
                    return None
                raise
            
            response = r2_client.get_object(Bucket=bucket_name, Key=html_path)
            
            if html_path.endswith('.html.gz'):
                with gzip.GzipFile(fileobj=response['Body']) as gz:
                    file_content = gz.read().decode('utf-8')
            else:
                file_content = response['Body'].read().decode('utf-8')

            logger.info("File downloaded successfully.")
            return file_content
            
        except Exception as e:
            last_exception = e
            retry_count += 1
            
            if retry_count < max_retries:
                wait_time = initial_backoff * (2 ** (retry_count - 1))  # exponential backoff
                logger.warning(f"Attempt {retry_count} failed. Retrying in {wait_time} seconds. Error: {str(e)}")
                time.sleep(wait_time)
            else:
                logger.error(f"Error downloading file {html_path} after {max_retries} attempts. Last error: {str(e)}")
                if isinstance(e, ClientError):
                    logger.error(f"Error response: {e.response}")
                return None
    
    return None


def delete_file_from_r2(r2_client, file_path):
    """Delete a file from R2 storage"""
    try:
        r2_client.delete_object(Bucket=config.R2_BUCKET_NAME, Key=file_path)
        logger.info(f"Deleted file from R2: {file_path}")
    except Exception as e:
        logger.error(f"Failed to delete file from R2: {file_path}, error: {str(e)}")
        raise e


def setup_logging():
    """
    DEPRECATED: Simple CloudWatch-compatible logging setup for Lambda
    Use logger_config.get_logger() instead for consistency.
    """
    # Configure root logger for CloudWatch
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )
    
    # Return logger instance
    return logging.getLogger('lambda_node_processor')


def get_logger(name):
    """
    DEPRECATED: Get a logger instance for CloudWatch compatibility
    Use logger_config.get_logger() instead for consistency.
    """
    return logging.getLogger(name)
