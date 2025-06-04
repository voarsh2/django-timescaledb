"""
Unit tests for TimescaleDB migration operations.

These tests verify the migration operation structure, serialization, and basic functionality
without requiring a database connection.
"""
import unittest
from datetime import timedelta

from timescale.db.migrations import (
    AddRetentionPolicy,
    RemoveRetentionPolicy,
    EnableCompression,
    AddCompressionPolicy,
    RemoveCompressionPolicy,
)


class MigrationOperationUnitTests(unittest.TestCase):
    """Unit tests for migration operations that don't require a database."""

    def test_add_retention_policy_init(self):
        """Test AddRetentionPolicy initialization."""
        operation = AddRetentionPolicy(
            model_name='TestModel',
            drop_after='60 days',
            schedule_interval='1 day',
            if_not_exists=True
        )

        self.assertEqual(operation.model_name, 'TestModel')
        self.assertEqual(operation.drop_after, '60 days')
        self.assertEqual(operation.schedule_interval, '1 day')
        self.assertTrue(operation.if_not_exists)
        self.assertIsNone(operation.drop_created_before)
        self.assertIsNone(operation.initial_start)
        self.assertIsNone(operation.timezone)

    def test_add_retention_policy_with_timedelta(self):
        """Test AddRetentionPolicy with timedelta values."""
        operation = AddRetentionPolicy(
            model_name='TestModel',
            drop_after=timedelta(days=30),
            schedule_interval=timedelta(hours=12)
        )

        self.assertEqual(operation.model_name, 'TestModel')
        self.assertEqual(operation.drop_after, timedelta(days=30))
        self.assertEqual(operation.schedule_interval, timedelta(hours=12))

    def test_add_retention_policy_deconstruct(self):
        """Test AddRetentionPolicy deconstruction for serialization."""
        operation = AddRetentionPolicy(
            model_name='TestModel',
            drop_after='60 days',
            schedule_interval='1 day',
            if_not_exists=False  # Use non-default value to test inclusion
        )

        name, args, kwargs = operation.deconstruct()

        self.assertEqual(name, 'AddRetentionPolicy')
        self.assertEqual(args, [])
        self.assertEqual(kwargs['model_name'], 'TestModel')
        self.assertEqual(kwargs['drop_after'], '60 days')
        self.assertEqual(kwargs['schedule_interval'], '1 day')
        self.assertEqual(kwargs['if_not_exists'], False)
        self.assertNotIn('drop_created_before', kwargs)
        self.assertNotIn('initial_start', kwargs)
        self.assertNotIn('timezone', kwargs)

    def test_add_retention_policy_deconstruct_minimal(self):
        """Test AddRetentionPolicy deconstruction with minimal parameters."""
        operation = AddRetentionPolicy(
            model_name='TestModel',
            drop_after='60 days'
        )

        name, args, kwargs = operation.deconstruct()

        self.assertEqual(name, 'AddRetentionPolicy')
        self.assertEqual(args, [])
        self.assertEqual(kwargs['model_name'], 'TestModel')
        self.assertEqual(kwargs['drop_after'], '60 days')
        # Default values should not be included
        self.assertNotIn('if_not_exists', kwargs)
        self.assertNotIn('schedule_interval', kwargs)

    def test_add_retention_policy_describe(self):
        """Test AddRetentionPolicy description."""
        operation = AddRetentionPolicy(
            model_name='TestModel',
            drop_after='60 days'
        )

        description = operation.describe()
        self.assertIn('Add retention policy', description)
        self.assertIn('TestModel', description)
        self.assertIn('60 days', description)

    def test_add_retention_policy_migration_name_fragment(self):
        """Test AddRetentionPolicy migration name fragment."""
        operation = AddRetentionPolicy(
            model_name='TestModel',
            drop_after='60 days'
        )

        fragment = operation.migration_name_fragment
        self.assertEqual(fragment, 'add_retention_policy_testmodel')

    def test_remove_retention_policy_init(self):
        """Test RemoveRetentionPolicy initialization."""
        operation = RemoveRetentionPolicy(
            model_name='TestModel',
            if_exists=False
        )

        self.assertEqual(operation.model_name, 'TestModel')
        self.assertFalse(operation.if_exists)

    def test_remove_retention_policy_deconstruct(self):
        """Test RemoveRetentionPolicy deconstruction."""
        operation = RemoveRetentionPolicy(
            model_name='TestModel',
            if_exists=False
        )

        name, args, kwargs = operation.deconstruct()

        self.assertEqual(name, 'RemoveRetentionPolicy')
        self.assertEqual(args, [])
        self.assertEqual(kwargs['model_name'], 'TestModel')
        self.assertEqual(kwargs['if_exists'], False)

    def test_remove_retention_policy_deconstruct_default(self):
        """Test RemoveRetentionPolicy deconstruction with default values."""
        operation = RemoveRetentionPolicy(
            model_name='TestModel'
        )

        name, args, kwargs = operation.deconstruct()

        self.assertEqual(name, 'RemoveRetentionPolicy')
        self.assertEqual(args, [])
        self.assertEqual(kwargs['model_name'], 'TestModel')
        # Default value should not be included
        self.assertNotIn('if_exists', kwargs)

    def test_enable_compression_init(self):
        """Test EnableCompression initialization."""
        operation = EnableCompression(
            model_name='TestModel',
            compress_segmentby=['device_id'],
            compress_orderby=['time'],
            compress_chunk_time_interval='1 hour',
            if_not_exists=False
        )

        self.assertEqual(operation.model_name, 'TestModel')
        self.assertEqual(operation.compress_segmentby, ['device_id'])
        self.assertEqual(operation.compress_orderby, ['time'])
        self.assertEqual(operation.compress_chunk_time_interval, '1 hour')
        self.assertFalse(operation.if_not_exists)

    def test_enable_compression_init_defaults(self):
        """Test EnableCompression initialization with defaults."""
        operation = EnableCompression(
            model_name='TestModel'
        )

        self.assertEqual(operation.model_name, 'TestModel')
        self.assertEqual(operation.compress_segmentby, [])
        self.assertEqual(operation.compress_orderby, [])
        self.assertIsNone(operation.compress_chunk_time_interval)
        self.assertTrue(operation.if_not_exists)

    def test_enable_compression_deconstruct(self):
        """Test EnableCompression deconstruction."""
        operation = EnableCompression(
            model_name='TestModel',
            compress_segmentby=['device_id'],
            compress_orderby=['time'],
            if_not_exists=False
        )

        name, args, kwargs = operation.deconstruct()

        self.assertEqual(name, 'EnableCompression')
        self.assertEqual(args, [])
        self.assertEqual(kwargs['model_name'], 'TestModel')
        self.assertEqual(kwargs['compress_segmentby'], ['device_id'])
        self.assertEqual(kwargs['compress_orderby'], ['time'])
        self.assertEqual(kwargs['if_not_exists'], False)

    def test_enable_compression_deconstruct_minimal(self):
        """Test EnableCompression deconstruction with minimal parameters."""
        operation = EnableCompression(
            model_name='TestModel'
        )

        name, args, kwargs = operation.deconstruct()

        self.assertEqual(name, 'EnableCompression')
        self.assertEqual(args, [])
        self.assertEqual(kwargs['model_name'], 'TestModel')
        # Empty lists and default values should not be included
        self.assertNotIn('compress_segmentby', kwargs)
        self.assertNotIn('compress_orderby', kwargs)
        self.assertNotIn('compress_chunk_time_interval', kwargs)
        self.assertNotIn('if_not_exists', kwargs)

    def test_add_compression_policy_init(self):
        """Test AddCompressionPolicy initialization."""
        operation = AddCompressionPolicy(
            model_name='TestModel',
            compress_after='7 days',
            schedule_interval='1 hour',
            if_not_exists=False
        )

        self.assertEqual(operation.model_name, 'TestModel')
        self.assertEqual(operation.compress_after, '7 days')
        self.assertEqual(operation.schedule_interval, '1 hour')
        self.assertFalse(operation.if_not_exists)

    def test_add_compression_policy_with_timedelta(self):
        """Test AddCompressionPolicy with timedelta values."""
        operation = AddCompressionPolicy(
            model_name='TestModel',
            compress_after=timedelta(days=7),
            schedule_interval=timedelta(hours=1)
        )

        self.assertEqual(operation.model_name, 'TestModel')
        self.assertEqual(operation.compress_after, timedelta(days=7))
        self.assertEqual(operation.schedule_interval, timedelta(hours=1))

    def test_add_compression_policy_deconstruct(self):
        """Test AddCompressionPolicy deconstruction."""
        operation = AddCompressionPolicy(
            model_name='TestModel',
            compress_after='7 days',
            schedule_interval='1 hour',
            if_not_exists=False
        )

        name, args, kwargs = operation.deconstruct()

        self.assertEqual(name, 'AddCompressionPolicy')
        self.assertEqual(args, [])
        self.assertEqual(kwargs['model_name'], 'TestModel')
        self.assertEqual(kwargs['compress_after'], '7 days')
        self.assertEqual(kwargs['schedule_interval'], '1 hour')
        self.assertEqual(kwargs['if_not_exists'], False)

    def test_remove_compression_policy_init(self):
        """Test RemoveCompressionPolicy initialization."""
        operation = RemoveCompressionPolicy(
            model_name='TestModel',
            if_exists=False
        )

        self.assertEqual(operation.model_name, 'TestModel')
        self.assertFalse(operation.if_exists)

    def test_remove_compression_policy_deconstruct(self):
        """Test RemoveCompressionPolicy deconstruction."""
        operation = RemoveCompressionPolicy(
            model_name='TestModel',
            if_exists=False
        )

        name, args, kwargs = operation.deconstruct()

        self.assertEqual(name, 'RemoveCompressionPolicy')
        self.assertEqual(args, [])
        self.assertEqual(kwargs['model_name'], 'TestModel')
        self.assertEqual(kwargs['if_exists'], False)

    def test_all_operations_describe(self):
        """Test that all operations have proper descriptions."""
        operations = [
            AddRetentionPolicy(model_name='TestModel', drop_after='60 days'),
            RemoveRetentionPolicy(model_name='TestModel'),
            EnableCompression(model_name='TestModel'),
            AddCompressionPolicy(model_name='TestModel', compress_after='30 days'),
            RemoveCompressionPolicy(model_name='TestModel'),
        ]

        for operation in operations:
            description = operation.describe()
            self.assertIsInstance(description, str)
            self.assertGreater(len(description), 0)
            self.assertIn('TestModel', description)

    def test_all_operations_migration_name_fragment(self):
        """Test that all operations have proper migration name fragments."""
        operations = [
            AddRetentionPolicy(model_name='TestModel', drop_after='60 days'),
            RemoveRetentionPolicy(model_name='TestModel'),
            EnableCompression(model_name='TestModel'),
            AddCompressionPolicy(model_name='TestModel', compress_after='30 days'),
            RemoveCompressionPolicy(model_name='TestModel'),
        ]

        expected_fragments = [
            'add_retention_policy_testmodel',
            'remove_retention_policy_testmodel',
            'enable_compression_testmodel',
            'add_compression_policy_testmodel',
            'remove_compression_policy_testmodel',
        ]

        for operation, expected_fragment in zip(operations, expected_fragments):
            fragment = operation.migration_name_fragment
            self.assertEqual(fragment, expected_fragment)

    def test_state_forwards_no_op(self):
        """Test that state_forwards methods don't modify state."""
        operations = [
            AddRetentionPolicy(model_name='TestModel', drop_after='60 days'),
            RemoveRetentionPolicy(model_name='TestModel'),
            EnableCompression(model_name='TestModel'),
            AddCompressionPolicy(model_name='TestModel', compress_after='30 days'),
            RemoveCompressionPolicy(model_name='TestModel'),
        ]

        # Mock state object
        class MockState:
            def __init__(self):
                self.modified = False

        for operation in operations:
            state = MockState()
            # This should not raise an exception and should not modify state
            operation.state_forwards('test_app', state)
            self.assertFalse(state.modified)


if __name__ == '__main__':
    unittest.main()
