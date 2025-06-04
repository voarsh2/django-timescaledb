# TimescaleDB Migration Operations

This module provides Django migration operations for managing TimescaleDB retention and compression policies declaratively in Django migrations.

## Available Operations

### AddRetentionPolicy

Adds a retention policy to automatically remove old data from a TimescaleDB hypertable.

```python
from timescale.db.migrations import AddRetentionPolicy

AddRetentionPolicy(
    model_name='MyTimeSeriesModel',
    drop_after='90 days',
    schedule_interval='1 day',  # Optional
    if_not_exists=True,  # Optional, default True
)
```

### RemoveRetentionPolicy

Removes a retention policy from a TimescaleDB hypertable.

```python
from timescale.db.migrations import RemoveRetentionPolicy

RemoveRetentionPolicy(
    model_name='MyTimeSeriesModel',
    if_exists=True,  # Optional, default True
)
```

### EnableCompression

Enables compression on a TimescaleDB hypertable with specified settings.

```python
from timescale.db.migrations import EnableCompression

EnableCompression(
    model_name='MyTimeSeriesModel',
    compress_orderby=['time'],  # Optional
    compress_segmentby=['device_id'],  # Optional
    compress_chunk_time_interval='1 hour',  # Optional
    if_not_exists=True,  # Optional, default True
)
```

### AddCompressionPolicy

Adds a compression policy to automatically compress chunks older than a specified interval.

```python
from timescale.db.migrations import AddCompressionPolicy

AddCompressionPolicy(
    model_name='MyTimeSeriesModel',
    compress_after='7 days',
    schedule_interval='1 hour',  # Optional
    if_not_exists=True,  # Optional, default True
)
```

### RemoveCompressionPolicy

Removes a compression policy from a TimescaleDB hypertable.

```python
from timescale.db.migrations import RemoveCompressionPolicy

RemoveCompressionPolicy(
    model_name='MyTimeSeriesModel',
    if_exists=True,  # Optional, default True
)
```

## Complete Migration Example

Here's a complete example of a Django migration that sets up compression and retention policies for a TimescaleDB hypertable:

```python
# migrations/0002_add_timescale_policies.py
from django.db import migrations
from timescale.db.migrations import (
    EnableCompression,
    AddCompressionPolicy,
    AddRetentionPolicy,
)

class Migration(migrations.Migration):
    dependencies = [
        ('myapp', '0001_initial'),
    ]

    operations = [
        # First, enable compression on the hypertable
        EnableCompression(
            model_name='SensorData',
            compress_orderby=['timestamp'],
            compress_segmentby=['sensor_id'],
        ),
        
        # Add a compression policy to compress data older than 7 days
        AddCompressionPolicy(
            model_name='SensorData',
            compress_after='7 days',
            schedule_interval='1 hour',
        ),
        
        # Add a retention policy to drop data older than 1 year
        AddRetentionPolicy(
            model_name='SensorData',
            drop_after='1 year',
            schedule_interval='1 day',
        ),
    ]
```

## Using with timedelta

You can also use Python `timedelta` objects instead of string intervals:

```python
from datetime import timedelta
from timescale.db.migrations import AddRetentionPolicy

AddRetentionPolicy(
    model_name='MyTimeSeriesModel',
    drop_after=timedelta(days=90),
    schedule_interval=timedelta(hours=12),
)
```

## Migration Workflow

### Setting up policies for a new hypertable

1. Create your model with `TimescaleDateTimeField`
2. Run `makemigrations` to create the initial migration
3. Create a new migration for policies: `python manage.py makemigrations --empty myapp`
4. Add the policy operations to the new migration
5. Run `migrate` to apply the policies

### Modifying existing policies

To modify an existing policy, you typically need to:

1. Remove the old policy
2. Add the new policy with updated parameters

```python
operations = [
    # Remove old retention policy
    RemoveRetentionPolicy(
        model_name='SensorData',
    ),
    
    # Add new retention policy with different interval
    AddRetentionPolicy(
        model_name='SensorData',
        drop_after='6 months',  # Changed from 1 year
    ),
]
```

## Important Notes

### Reversibility

- `AddRetentionPolicy` and `AddCompressionPolicy` are reversible (they remove the policy when reversed)
- `RemoveRetentionPolicy` and `RemoveCompressionPolicy` are **not reversible** - you need to manually create the reverse operation with the original parameters
- `EnableCompression` attempts to disable compression when reversed, but TimescaleDB has limitations on disabling compression

### Prerequisites

- The table must already be a TimescaleDB hypertable before applying compression or retention policies
- For compression policies, compression must be enabled on the hypertable first using `EnableCompression`

### Error Handling

All operations use `if_not_exists=True` and `if_exists=True` by default to make migrations more robust and idempotent.

## Advanced Usage

### Custom Schedule Intervals

You can specify custom schedule intervals for when policies run:

```python
AddRetentionPolicy(
    model_name='MyModel',
    drop_after='90 days',
    schedule_interval='6 hours',  # Run every 6 hours
)
```

### Timezone Support

You can specify a timezone for policy execution:

```python
AddRetentionPolicy(
    model_name='MyModel',
    drop_after='90 days',
    timezone='America/New_York',
)
```

### Initial Start Time

You can specify when a policy should first run:

```python
from datetime import datetime
from django.utils import timezone

AddRetentionPolicy(
    model_name='MyModel',
    drop_after='90 days',
    initial_start=timezone.now() + timedelta(hours=1),
)
```

## Troubleshooting

### Common Issues

1. **"relation is not a hypertable"**: Make sure your model uses `TimescaleDateTimeField` and the hypertable was created before applying policies.

2. **"compression not enabled"**: You must use `EnableCompression` before adding compression policies.

3. **"policy already exists"**: Use `if_not_exists=True` (default) to avoid this error.

### Checking Policy Status

You can check if policies are active by querying TimescaleDB system tables:

```sql
-- Check retention policies
SELECT * FROM timescaledb_information.jobs 
WHERE proc_name = 'policy_retention';

-- Check compression policies  
SELECT * FROM timescaledb_information.jobs 
WHERE proc_name = 'policy_compression';

-- Check compression status
SELECT * FROM timescaledb_information.hypertables;
```
