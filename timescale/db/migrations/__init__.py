"""
TimescaleDB migration operations.

This module provides Django migration operations for managing TimescaleDB
retention and compression policies.

Example usage in a migration file:

    from timescale.db.migrations import (
        AddRetentionPolicy,
        AddCompressionPolicy,
        EnableCompression
    )

    class Migration(migrations.Migration):
        dependencies = [
            ('myapp', '0001_initial'),
        ]

        operations = [
            # Enable compression on the model
            EnableCompression(
                model_name='MyTimeSeriesModel',
                compress_orderby=['time'],
                compress_segmentby=['device_id'],
            ),
            # Add compression policy
            AddCompressionPolicy(
                model_name='MyTimeSeriesModel',
                compress_after='7 days',
            ),
            # Add retention policy
            AddRetentionPolicy(
                model_name='MyTimeSeriesModel',
                drop_after='90 days',
            ),
        ]
"""

from ..operations import TimescaleExtension
from .operations import (
    AddRetentionPolicy,
    RemoveRetentionPolicy,
    EnableCompression,
    AddCompressionPolicy,
    RemoveCompressionPolicy,
)

__all__ = [
    'TimescaleExtension',
    'AddRetentionPolicy',
    'RemoveRetentionPolicy',
    'EnableCompression',
    'AddCompressionPolicy',
    'RemoveCompressionPolicy',
]
