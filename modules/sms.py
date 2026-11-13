"""
SMS to a group of people through an AWS SNS topic per group. The topic ARN of group <g> is the
config row sms/topic/<g>; the subscriptions (phone numbers) live in SNS, not in FIDO's DB.
Credentials come from AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in the environment.
"""
import asyncio
import logging
import threading

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from modules import configmanager

log = logging.getLogger(__name__)

REGION = 'eu-central-1'
CLIENT_CONFIG = Config(connect_timeout=5, read_timeout=10, retries={'max_attempts': 2})
TOPIC_MODULE = 'sms'
TOPIC_KEY_PREFIX = 'topic/'

_client = None
_client_lock = threading.Lock()


def client():
    """The SNS client, created on first use. Blocking: call it from a worker thread."""
    global _client
    with _client_lock:
        if _client is None:
            _client = boto3.Session().client('sns', region_name=REGION, config=CLIENT_CONFIG)
        return _client


def topic_for(group: str):
    """The topic ARN configured for group, or None."""
    return configmanager.get_value(TOPIC_MODULE, f'{TOPIC_KEY_PREFIX}{group}')


def _publish(topic: str, text: str) -> str:
    return client().publish(TopicArn=topic, Message=text)['MessageId']


async def send_to_group(group: str, text: str) -> bool:
    """
    Publish text to the SNS topic of group.
    :return: True if SNS accepted it; False if no topic is configured or the publish failed (logged)
    """
    topic = topic_for(group)
    if not topic:
        log.warning(f"No SMS topic configured for group {group} ({TOPIC_MODULE}/{TOPIC_KEY_PREFIX}{group}), "
                    f"nothing sent")
        return False
    try:
        message_id = await asyncio.to_thread(_publish, topic, text)
    except (BotoCoreError, ClientError) as error:
        log.error(f"SMS to group {group} failed: {error!r}")
        return False
    log.info(f"SMS to group {group} published, message id {message_id}")
    return True
