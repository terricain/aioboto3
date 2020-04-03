#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for `aioboto3` package."""

import pytest
from aiobotocore.client import AioBaseClient

import aioboto3


@pytest.mark.asyncio
async def test_getting_client(event_loop):
    """Simple getting of client."""
    aioboto3.DEFAULT_SESSION = None

    async with aioboto3.client('ssm', region_name='eu-central-1') as client:
        assert isinstance(client, AioBaseClient)


@pytest.mark.asyncio
async def test_getting_resource_cm(event_loop):
    """Simple getting of resource."""
    aioboto3.DEFAULT_SESSION = None

    async with aioboto3.resource('dynamodb', region_name='eu-central-1') as resource:
        assert isinstance(resource.meta.client, AioBaseClient)
