"""
TimescaleDB migration operations.

This module provides Django migration operations for managing TimescaleDB
retention and compression policies declaratively.

The operations are automatically generated when you define TimescalePolicies
in your Django models and run makemigrations.

Example model with declarative policies:

    from django.db import models
    from timescale.db.models.fields import TimescaleDateTimeField
    from timescale.db.models.managers import TimescaleManager

    class SensorData(models.Model):
        timestamp = TimescaleDateTimeField(interval="1 hour")
        sensor_id = models.CharField(max_length=50)
        temperature = models.FloatField()

        objects = models.Manager()
        timescale = TimescaleManager()

        class TimescalePolicies:
            compression = {
                'enabled': True,
                'compress_orderby': ['timestamp'],
                'compress_segmentby': ['sensor_id'],
            }
            compression_policy = {
                'compress_after': '7 days',
                'schedule_interval': '1 hour',
            }
            retention_policy = {
                'drop_after': '90 days',
                'schedule_interval': '1 day',
            }

When you run makemigrations, Django will automatically generate migration
operations to apply these policies to your TimescaleDB hypertables.
"""

from ..operations import TimescaleExtension
from .operations import (
    ApplyTimescalePolicies,
    RemoveTimescalePolicies,
    # Individual operations for backward compatibility and programmatic use
    AddRetentionPolicy,
    RemoveRetentionPolicy,
    EnableCompression,
    AddCompressionPolicy,
    RemoveCompressionPolicy,
)

__all__ = [
    'TimescaleExtension',
    'ApplyTimescalePolicies',
    'RemoveTimescalePolicies',
    # Individual operations
    'AddRetentionPolicy',
    'RemoveRetentionPolicy',
    'EnableCompression',
    'AddCompressionPolicy',
    'RemoveCompressionPolicy',
]
