"""
Tests for TimescaleDB retention and compression policies.
"""
import os

# Configure Django settings before importing Django modules
import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        DEBUG=True,
        DATABASES={
            'default': {
                'ENGINE': 'timescale.db.backends.postgresql',
                'NAME': os.environ.get('DB_DATABASE', 'test_timescale'),
                'USER': os.environ.get('DB_USERNAME', 'postgres'),
                'PASSWORD': os.environ.get('DB_PASSWORD', 'password'),
                'HOST': os.environ.get('DB_HOST', 'localhost'),
                'PORT': os.environ.get('DB_PORT', '5433'),
            }
        },
        INSTALLED_APPS=[
            'timescale',
        ],
        USE_TZ=True,
        SECRET_KEY='test-secret-key-for-testing-only',
    )
    django.setup()

from django.test import TransactionTestCase
from django.db import connection, models
from django.utils import timezone
from datetime import timedelta

# Import directly to avoid circular imports
from timescale.db.models.fields import TimescaleDateTimeField
from timescale.db.models.managers import TimescaleManager


# Define test models (these won't be migrated, just created/dropped in tests)
class RetentionTestMetric(models.Model):
    """Test model with TimescaleDateTimeField."""
    time = TimescaleDateTimeField(interval="1 day")
    temperature = models.FloatField(default=0.0)
    device = models.IntegerField(default=0)

    objects = models.Manager()
    timescale = TimescaleManager()

    class Meta:
        app_label = 'timescale'
        db_table = 'timescale_retentiontestmetric'


class RetentionTestTimescaleModel(models.Model):
    """Test model similar to TimescaleModel."""
    time = TimescaleDateTimeField(interval="1 day")
    value = models.FloatField(default=0.0)

    objects = models.Manager()
    timescale = TimescaleManager()

    class Meta:
        app_label = 'timescale'
        db_table = 'timescale_retentiontesttimescalemodel'


class RetentionPolicyTests(TransactionTestCase):
    """Tests for TimescaleDB retention policies."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test data."""
        super().setUpClass()
        
        # Create the test tables
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(RetentionTestMetric)
            schema_editor.create_model(RetentionTestTimescaleModel)
            
        # Create hypertables
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT create_hypertable('timescale_retentiontestmetric', 'time', if_not_exists => TRUE)"
            )
            cursor.execute(
                "SELECT create_hypertable('timescale_retentiontesttimescalemodel', 'time', if_not_exists => TRUE)"
            )
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test data."""
        # Drop the test tables
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS timescale_retentiontestmetric CASCADE")
            cursor.execute("DROP TABLE IF EXISTS timescale_retentiontesttimescalemodel CASCADE")
            
        super().tearDownClass()
    
    def setUp(self):
        """Set up test data."""
        # Create some test data
        self.timestamp = timezone.now()
        RetentionTestMetric.objects.create(
            time=self.timestamp - timedelta(days=30),
            temperature=10.0,
            device=1
        )
        RetentionTestMetric.objects.create(
            time=self.timestamp - timedelta(days=60),
            temperature=15.0,
            device=1
        )
        RetentionTestMetric.objects.create(
            time=self.timestamp - timedelta(days=90),
            temperature=20.0,
            device=1
        )

    def test_add_retention_policy(self):
        """Test adding a retention policy."""
        # Add a retention policy to drop data older than 60 days
        job_id = RetentionTestMetric.timescale.add_retention_policy(
            drop_after='60 days',
            if_not_exists=True
        )
        
        # Check that the job was created
        self.assertIsNotNone(job_id)
        
        # Check that the policy exists in the database
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM timescaledb_information.jobs
                WHERE job_id = %s
            """, [job_id])
            result = cursor.fetchone()
            self.assertIsNotNone(result)
    
    def test_remove_retention_policy(self):
        """Test removing a retention policy."""
        # Add a retention policy
        job_id = RetentionTestMetric.timescale.add_retention_policy(
            drop_after='60 days',
            if_not_exists=True
        )
        
        # Remove the policy
        result = RetentionTestMetric.timescale.remove_retention_policy(if_exists=True)
        
        # Check that the policy was removed
        self.assertTrue(result)
        
        # Check that the policy no longer exists in the database
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM timescaledb_information.jobs
                WHERE job_id = %s
            """, [job_id])
            result = cursor.fetchone()
            self.assertIsNone(result)
    
class CompressionPolicyTests(TransactionTestCase):
    """Tests for TimescaleDB compression policies."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test data."""
        super().setUpClass()
        
        # Create the test tables
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(RetentionTestMetric)
            schema_editor.create_model(RetentionTestTimescaleModel)
            
        # Create hypertables
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT create_hypertable('timescale_retentiontestmetric', 'time', if_not_exists => TRUE)"
            )
            cursor.execute(
                "SELECT create_hypertable('timescale_retentiontesttimescalemodel', 'time', if_not_exists => TRUE)"
            )
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test data."""
        # Drop the test tables
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS timescale_retentiontestmetric CASCADE")
            cursor.execute("DROP TABLE IF EXISTS timescale_retentiontesttimescalemodel CASCADE")
            
        super().tearDownClass()
    
    def setUp(self):
        """Set up test data."""
        # Create some test data
        self.timestamp = timezone.now()
        RetentionTestMetric.objects.create(
            time=self.timestamp - timedelta(days=30),
            temperature=10.0,
            device=1
        )
        RetentionTestMetric.objects.create(
            time=self.timestamp - timedelta(days=60),
            temperature=15.0,
            device=1
        )
        RetentionTestMetric.objects.create(
            time=self.timestamp - timedelta(days=90),
            temperature=20.0,
            device=1
        )
    
    def test_enable_compression(self):
        """Test enabling compression on a hypertable."""
        # Enable compression
        result = RetentionTestMetric.timescale.enable_compression(
            compress_orderby=['time'],
            if_not_exists=True
        )
        
        # Check that compression was enabled
        self.assertTrue(result)
        
        # Check that compression is enabled in the database
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT compression_enabled FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'timescale_retentiontestmetric'
            """)
            result = cursor.fetchone()
            # If result is None, compression might not be properly enabled
            self.assertIsNotNone(result, "Compression status not found in hypertables")
            self.assertTrue(result[0], "Compression is not enabled")
    
    def test_add_compression_policy(self):
        """Test adding a compression policy."""
        # Enable compression first
        RetentionTestMetric.timescale.enable_compression(
            compress_orderby=['time'],
            if_not_exists=True
        )
        
        # Add a compression policy to compress data older than 30 days
        job_id = RetentionTestMetric.timescale.add_compression_policy(
            compress_after='30 days',
            if_not_exists=True
        )
        
        # Check that the job was created
        self.assertIsNotNone(job_id)
        
        # Check that the policy exists in the database
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM timescaledb_information.jobs
                WHERE job_id = %s
            """, [job_id])
            result = cursor.fetchone()
            self.assertIsNotNone(result)
    
    def test_remove_compression_policy(self):
        """Test removing a compression policy."""
        # Enable compression first
        RetentionTestMetric.timescale.enable_compression(
            compress_orderby=['time'],
            if_not_exists=True
        )
        
        # Add a compression policy
        job_id = RetentionTestMetric.timescale.add_compression_policy(
            compress_after='30 days',
            if_not_exists=True
        )
        
        # Remove the policy
        result = RetentionTestMetric.timescale.remove_compression_policy(if_exists=True)
        
        # Check that the policy was removed
        self.assertTrue(result)
        
        # Check that the policy no longer exists in the database
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM timescaledb_information.jobs
                WHERE job_id = %s
            """, [job_id])
            result = cursor.fetchone()
            self.assertIsNone(result)
    
    def test_get_compression_stats(self):
        """Test getting compression statistics."""
        # Enable compression
        RetentionTestMetric.timescale.enable_compression(
            compress_orderby=['time'],
            if_not_exists=True
        )
        
        # Get compression stats
        stats = RetentionTestMetric.timescale.get_compression_stats()
        
        # Check that stats were returned
        self.assertIsInstance(stats, list)
        
        # There should be at least one row for our hypertable
        self.assertTrue(len(stats) > 0)


class IndividualMigrationOperationTests(TransactionTestCase):
    """Tests for individual migration operations (programmatic API)."""

    @classmethod
    def setUpClass(cls):
        """Set up test data."""
        super().setUpClass()

        # Create the test tables
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(RetentionTestMetric)

        # Create hypertables
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT create_hypertable('timescale_retentiontestmetric', 'time', if_not_exists => TRUE)"
            )

    @classmethod
    def tearDownClass(cls):
        """Clean up test data."""
        # Drop the test tables
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS timescale_retentiontestmetric CASCADE")

        super().tearDownClass()

    def setUp(self):
        """Set up test data."""
        # Clean up any existing policies
        try:
            RetentionTestMetric.timescale.remove_retention_policy(if_exists=True)
            RetentionTestMetric.timescale.remove_compression_policy(if_exists=True)
        except:
            pass

    def test_individual_operations_import(self):
        """Test that individual operations can be imported."""
        from timescale.db.migrations import (
            AddRetentionPolicy,
            RemoveRetentionPolicy,
            EnableCompression,
            AddCompressionPolicy,
            RemoveCompressionPolicy
        )

        # Test that all operations exist and can be instantiated
        operations = [
            AddRetentionPolicy('TestModel', drop_after='30 days'),
            RemoveRetentionPolicy('TestModel'),
            EnableCompression('TestModel', compress_orderby=['time']),
            AddCompressionPolicy('TestModel', compress_after='7 days'),
            RemoveCompressionPolicy('TestModel'),
        ]

        for op in operations:
            # Test that each operation has required methods
            self.assertTrue(hasattr(op, 'describe'))
            self.assertTrue(hasattr(op, 'migration_name_fragment'))
            self.assertTrue(hasattr(op, 'deconstruct'))

            # Test descriptions
            description = op.describe()
            self.assertIsInstance(description, str)
            self.assertGreater(len(description), 0)

            # Test migration fragments
            fragment = op.migration_name_fragment
            self.assertIsInstance(fragment, str)
            self.assertGreater(len(fragment), 0)

    def test_enable_compression_operation(self):
        """Test EnableCompression migration operation."""
        from timescale.db.migrations import EnableCompression
        from django.db.migrations.state import ProjectState

        operation = EnableCompression(
            model_name='RetentionTestMetric',
            compress_orderby=['time'],
            if_not_exists=True
        )

        # Test database operation
        state = ProjectState()
        with connection.schema_editor() as schema_editor:
            operation.database_forwards('timescale', schema_editor, state, state)

        # Verify compression was enabled
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT compression_enabled FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'timescale_retentiontestmetric'
            """)
            result = cursor.fetchone()
            self.assertTrue(result[0])

    def test_add_retention_policy_operation(self):
        """Test AddRetentionPolicy migration operation."""
        from timescale.db.migrations import AddRetentionPolicy
        from django.db.migrations.state import ProjectState

        operation = AddRetentionPolicy(
            model_name='RetentionTestMetric',
            drop_after='60 days',
            schedule_interval='1 day',
            if_not_exists=True
        )

        # Test database operation
        state = ProjectState()
        with connection.schema_editor() as schema_editor:
            operation.database_forwards('timescale', schema_editor, state, state)

        # Verify policy was created
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE hypertable_name = 'timescale_retentiontestmetric'
                AND proc_name = 'policy_retention'
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)

    def test_add_compression_policy_operation(self):
        """Test AddCompressionPolicy migration operation."""
        from timescale.db.migrations import EnableCompression, AddCompressionPolicy
        from django.db.migrations.state import ProjectState

        # First enable compression
        enable_op = EnableCompression(
            model_name='RetentionTestMetric',
            compress_orderby=['time']
        )

        state = ProjectState()
        with connection.schema_editor() as schema_editor:
            enable_op.database_forwards('timescale', schema_editor, state, state)

        # Then add compression policy
        policy_op = AddCompressionPolicy(
            model_name='RetentionTestMetric',
            compress_after='30 days',
            schedule_interval='1 hour',
            if_not_exists=True
        )

        with connection.schema_editor() as schema_editor:
            policy_op.database_forwards('timescale', schema_editor, state, state)

        # Verify policy was created
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE hypertable_name = 'timescale_retentiontestmetric'
                AND proc_name = 'policy_compression'
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)

    def test_remove_policies_operations(self):
        """Test RemoveRetentionPolicy and RemoveCompressionPolicy operations."""
        from timescale.db.migrations import (
            EnableCompression, AddCompressionPolicy, AddRetentionPolicy,
            RemoveCompressionPolicy, RemoveRetentionPolicy
        )
        from django.db.migrations.state import ProjectState

        # Set up policies first
        state = ProjectState()
        with connection.schema_editor() as schema_editor:
            # Enable compression and add policies
            EnableCompression(
                model_name='RetentionTestMetric',
                compress_orderby=['time']
            ).database_forwards('timescale', schema_editor, state, state)

            AddCompressionPolicy(
                model_name='RetentionTestMetric',
                compress_after='7 days'
            ).database_forwards('timescale', schema_editor, state, state)

            AddRetentionPolicy(
                model_name='RetentionTestMetric',
                drop_after='30 days'
            ).database_forwards('timescale', schema_editor, state, state)

        # Verify policies exist
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE hypertable_name = 'timescale_retentiontestmetric'
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 2)  # compression + retention

        # Test removing compression policy
        remove_compression = RemoveCompressionPolicy(
            model_name='RetentionTestMetric',
            if_exists=True
        )

        with connection.schema_editor() as schema_editor:
            remove_compression.database_forwards('timescale', schema_editor, state, state)

        # Verify compression policy removed
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE hypertable_name = 'timescale_retentiontestmetric'
                AND proc_name = 'policy_compression'
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 0)

        # Test removing retention policy
        remove_retention = RemoveRetentionPolicy(
            model_name='RetentionTestMetric',
            if_exists=True
        )

        with connection.schema_editor() as schema_editor:
            remove_retention.database_forwards('timescale', schema_editor, state, state)

        # Verify retention policy removed
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE hypertable_name = 'timescale_retentiontestmetric'
                AND proc_name = 'policy_retention'
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 0)
