import logging

from boto3.resources.base import ServiceResource

logger = logging.getLogger(__name__)


class AIOBoto3ServiceResource(ServiceResource):
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.meta.client.close()
        return False

    def close(self):
        return self.meta.client.close()
