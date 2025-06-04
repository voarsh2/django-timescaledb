"""
Example Django migration showing how to use TimescaleDB policy operations.

This is an example migration file that demonstrates how to use the TimescaleDB
migration operations to set up compression and retention policies.

To use this in your own project:
1. Copy the operations you need into your own migration file
2. Update the model_name to match your actual model
3. Adjust the time intervals as needed for your use case
"""

from django.db import migrations
from timescale.db.migrations import (
    EnableCompression,
    AddCompressionPolicy,
    AddRetentionPolicy,
    RemoveRetentionPolicy,
    RemoveCompressionPolicy,
)


class Migration(migrations.Migration):
    """
    Example migration for setting up TimescaleDB policies.
    
    This migration assumes you have a model called 'SensorData' that is already
    a TimescaleDB hypertable (created by having a TimescaleDateTimeField).
    """
    
    dependencies = [
        ('myapp', '0001_initial'),  # Replace with your actual app and migration
    ]

    operations = [
        # Step 1: Enable compression on the hypertable
        # This configures the hypertable for compression with specific settings
        EnableCompression(
            model_name='SensorData',  # Replace with your model name
            compress_orderby=['timestamp'],  # Order by timestamp for better compression
            compress_segmentby=['sensor_id'],  # Segment by sensor_id for parallel processing
        ),
        
        # Step 2: Add a compression policy
        # This automatically compresses chunks older than 7 days
        AddCompressionPolicy(
            model_name='SensorData',  # Replace with your model name
            compress_after='7 days',  # Compress data older than 7 days
            schedule_interval='1 hour',  # Check for new chunks to compress every hour
        ),
        
        # Step 3: Add a retention policy
        # This automatically removes data older than 1 year
        AddRetentionPolicy(
            model_name='SensorData',  # Replace with your model name
            drop_after='1 year',  # Remove data older than 1 year
            schedule_interval='1 day',  # Check for old data to remove daily
        ),
    ]


# Example of a migration that modifies existing policies
class ModifyPoliciesMigration(migrations.Migration):
    """
    Example migration for modifying existing TimescaleDB policies.
    
    This shows how to change policy parameters by removing the old policy
    and adding a new one with different settings.
    """
    
    dependencies = [
        ('myapp', '0002_add_timescale_policies'),  # The migration that added the original policies
    ]

    operations = [
        # Remove the old retention policy
        RemoveRetentionPolicy(
            model_name='SensorData',
        ),
        
        # Add a new retention policy with a shorter retention period
        AddRetentionPolicy(
            model_name='SensorData',
            drop_after='6 months',  # Changed from 1 year to 6 months
            schedule_interval='1 day',
        ),
        
        # You could also modify compression policies in the same way:
        # RemoveCompressionPolicy(
        #     model_name='SensorData',
        # ),
        # AddCompressionPolicy(
        #     model_name='SensorData',
        #     compress_after='3 days',  # Changed from 7 days to 3 days
        #     schedule_interval='30 minutes',  # More frequent compression
        # ),
    ]


# Example using timedelta objects instead of strings
class TimedeltaExampleMigration(migrations.Migration):
    """
    Example migration using Python timedelta objects for time intervals.
    
    This shows an alternative way to specify time intervals using Python's
    timedelta objects instead of string intervals.
    """
    
    from datetime import timedelta
    
    dependencies = [
        ('myapp', '0001_initial'),
    ]

    operations = [
        EnableCompression(
            model_name='SensorData',
            compress_orderby=['timestamp'],
        ),
        
        AddCompressionPolicy(
            model_name='SensorData',
            compress_after=timedelta(days=7),  # Using timedelta
            schedule_interval=timedelta(hours=1),  # Using timedelta
        ),
        
        AddRetentionPolicy(
            model_name='SensorData',
            drop_after=timedelta(days=365),  # 1 year using timedelta
            schedule_interval=timedelta(days=1),  # Using timedelta
        ),
    ]


# Example for multiple models
class MultipleModelsMigration(migrations.Migration):
    """
    Example migration for setting up policies on multiple models.
    
    This shows how to apply different policies to different models
    based on their specific requirements.
    """
    
    dependencies = [
        ('myapp', '0001_initial'),
    ]

    operations = [
        # High-frequency sensor data - aggressive compression and shorter retention
        EnableCompression(
            model_name='HighFrequencySensorData',
            compress_orderby=['timestamp'],
            compress_segmentby=['sensor_id'],
        ),
        AddCompressionPolicy(
            model_name='HighFrequencySensorData',
            compress_after='1 day',  # Compress quickly
        ),
        AddRetentionPolicy(
            model_name='HighFrequencySensorData',
            drop_after='30 days',  # Short retention
        ),
        
        # Low-frequency sensor data - less aggressive compression and longer retention
        EnableCompression(
            model_name='LowFrequencySensorData',
            compress_orderby=['timestamp'],
        ),
        AddCompressionPolicy(
            model_name='LowFrequencySensorData',
            compress_after='30 days',  # Compress less frequently
        ),
        AddRetentionPolicy(
            model_name='LowFrequencySensorData',
            drop_after='2 years',  # Longer retention
        ),
        
        # Audit logs - compression but no automatic deletion
        EnableCompression(
            model_name='AuditLog',
            compress_orderby=['timestamp'],
            compress_segmentby=['user_id'],
        ),
        AddCompressionPolicy(
            model_name='AuditLog',
            compress_after='90 days',
        ),
        # Note: No retention policy for audit logs - keep forever
    ]
