#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for `aioboto3` package."""

import pytest
from aiobotocore.client import AioBaseClient

import aioboto3


@pytest.mark.asyncio
async def test_getting_client():
    """Simple getting of client."""
    session = aioboto3.Session()

    async with session.client('ssm', region_name='eu-central-1') as client:
        assert isinstance(client, AioBaseClient)


@pytest.mark.asyncio
async def test_getting_resource_cm():
    """Simple getting of resource."""
    session = aioboto3.Session()

    async with session.resource('dynamodb', region_name='eu-central-1') as resource:
        assert isinstance(resource.meta.client, AioBaseClient)
