"""
Tests for TimescaleDB migration operations.

These tests verify that the migration operations work correctly for both
forward and reverse migrations.
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
from django.db import connection, models, migrations
from django.db.migrations.state import ProjectState
from django.utils import timezone
from datetime import timedelta
import tempfile

# Import directly to avoid circular imports
from timescale.db.models.fields import TimescaleDateTimeField
from timescale.db.models.managers import TimescaleManager
from timescale.db.migrations import (
    AddRetentionPolicy,
    RemoveRetentionPolicy,
    EnableCompression,
    AddCompressionPolicy,
    RemoveCompressionPolicy,
)


# Define test models (these won't be migrated, just created/dropped in tests)
class TestMigrationModel(models.Model):
    """Test model for migration operations."""
    time = TimescaleDateTimeField(interval="1 day")
    temperature = models.FloatField(default=0.0)
    device = models.IntegerField(default=0)

    objects = models.Manager()
    timescale = TimescaleManager()

    class Meta:
        app_label = 'timescale'
        db_table = 'timescale_testmigrationmodel'


class MigrationOperationTestCase(TransactionTestCase):
    """Base test case for migration operations."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test data."""
        super().setUpClass()
        
        # Create the test table
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(TestMigrationModel)
            
        # Create hypertable
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT create_hypertable('timescale_testmigrationmodel', 'time', if_not_exists => TRUE)"
            )
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test data."""
        # Drop the test table
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS timescale_testmigrationmodel CASCADE")
            
        super().tearDownClass()
    
    def setUp(self):
        """Set up test data."""
        # Create some test data
        self.timestamp = timezone.now()
        TestMigrationModel.objects.create(
            time=self.timestamp - timedelta(days=30),
            temperature=10.0,
            device=1
        )
        TestMigrationModel.objects.create(
            time=self.timestamp - timedelta(days=60),
            temperature=15.0,
            device=1
        )
    
    def tearDown(self):
        """Clean up after each test."""
        # Remove any policies that might have been created
        try:
            TestMigrationModel.timescale.remove_retention_policy(if_exists=True)
        except:
            pass
        try:
            TestMigrationModel.timescale.remove_compression_policy(if_exists=True)
        except:
            pass
        
        # Clear test data
        TestMigrationModel.objects.all().delete()
    
    def get_schema_editor(self):
        """Get a schema editor for testing."""
        return connection.schema_editor()
    
    def get_project_state(self):
        """Get a project state for testing."""
        # For our TimescaleDB operations, we don't need the model state
        # since they work directly with the database
        return ProjectState()


class AddRetentionPolicyTests(MigrationOperationTestCase):
    """Tests for AddRetentionPolicy migration operation."""
    
    def test_add_retention_policy_forward(self):
        """Test adding a retention policy in forward migration."""
        operation = AddRetentionPolicy(
            model_name='TestMigrationModel',
            drop_after='60 days',
            if_not_exists=True
        )
        
        # Test forward migration
        state = self.get_project_state()
        with self.get_schema_editor() as schema_editor:
            operation.database_forwards('timescale', schema_editor, state, state)
        
        # Verify the policy was created
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE proc_name = 'policy_retention'
                AND hypertable_name = 'timescale_testmigrationmodel'
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)
    
    def test_add_retention_policy_backward(self):
        """Test removing a retention policy in backward migration."""
        # First add a policy
        TestMigrationModel.timescale.add_retention_policy(
            drop_after='60 days',
            if_not_exists=True
        )
        
        operation = AddRetentionPolicy(
            model_name='TestMigrationModel',
            drop_after='60 days',
            if_not_exists=True
        )
        
        # Test backward migration
        state = self.get_project_state()
        with self.get_schema_editor() as schema_editor:
            operation.database_backwards('timescale', schema_editor, state, state)
        
        # Verify the policy was removed
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE proc_name = 'policy_retention'
                AND hypertable_name = 'timescale_testmigrationmodel'
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 0)
    
    def test_add_retention_policy_with_timedelta(self):
        """Test adding a retention policy with timedelta."""
        operation = AddRetentionPolicy(
            model_name='TestMigrationModel',
            drop_after=timedelta(days=30),
            schedule_interval=timedelta(hours=12),
            if_not_exists=True
        )
        
        # Test forward migration
        state = self.get_project_state()
        with self.get_schema_editor() as schema_editor:
            operation.database_forwards('timescale', schema_editor, state, state)
        
        # Verify the policy was created
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE proc_name = 'policy_retention'
                AND hypertable_name = 'timescale_testmigrationmodel'
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)
    
    def test_add_retention_policy_deconstruct(self):
        """Test that the operation can be deconstructed properly."""
        operation = AddRetentionPolicy(
            model_name='TestMigrationModel',
            drop_after='60 days',
            schedule_interval='1 day',
            if_not_exists=False  # Use non-default value to test inclusion
        )

        name, args, kwargs = operation.deconstruct()
        self.assertEqual(name, 'AddRetentionPolicy')
        self.assertEqual(args, [])
        self.assertEqual(kwargs['model_name'], 'TestMigrationModel')
        self.assertEqual(kwargs['drop_after'], '60 days')
        self.assertEqual(kwargs['schedule_interval'], '1 day')
        self.assertEqual(kwargs['if_not_exists'], False)  # Should be included when False


class RemoveRetentionPolicyTests(MigrationOperationTestCase):
    """Tests for RemoveRetentionPolicy migration operation."""
    
    def test_remove_retention_policy_forward(self):
        """Test removing a retention policy in forward migration."""
        # First add a policy
        TestMigrationModel.timescale.add_retention_policy(
            drop_after='60 days',
            if_not_exists=True
        )
        
        operation = RemoveRetentionPolicy(
            model_name='TestMigrationModel',
            if_exists=True
        )
        
        # Test forward migration
        state = self.get_project_state()
        with self.get_schema_editor() as schema_editor:
            operation.database_forwards('timescale', schema_editor, state, state)
        
        # Verify the policy was removed
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE proc_name = 'policy_retention'
                AND hypertable_name = 'timescale_testmigrationmodel'
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 0)
    
    def test_remove_retention_policy_backward_not_reversible(self):
        """Test that backward migration raises NotImplementedError."""
        operation = RemoveRetentionPolicy(
            model_name='TestMigrationModel',
            if_exists=True
        )
        
        state = self.get_project_state()
        with self.get_schema_editor() as schema_editor:
            with self.assertRaises(NotImplementedError):
                operation.database_backwards('timescale', schema_editor, state, state)


class EnableCompressionTests(MigrationOperationTestCase):
    """Tests for EnableCompression migration operation."""
    
    def test_enable_compression_forward(self):
        """Test enabling compression in forward migration."""
        operation = EnableCompression(
            model_name='TestMigrationModel',
            compress_orderby=['time'],
            if_not_exists=True
        )
        
        # Test forward migration
        state = self.get_project_state()
        with self.get_schema_editor() as schema_editor:
            operation.database_forwards('timescale', schema_editor, state, state)
        
        # Verify compression was enabled
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT compression_enabled FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'timescale_testmigrationmodel'
            """)
            result = cursor.fetchone()
            self.assertIsNotNone(result)
            self.assertTrue(result[0])
    
    def test_enable_compression_backward(self):
        """Test disabling compression in backward migration."""
        # First enable compression
        TestMigrationModel.timescale.enable_compression(
            compress_orderby=['time'],
            if_not_exists=True
        )
        
        operation = EnableCompression(
            model_name='TestMigrationModel',
            compress_orderby=['time'],
            if_not_exists=True
        )
        
        # Test backward migration (should succeed silently due to if_exists=True)
        state = self.get_project_state()
        with self.get_schema_editor() as schema_editor:
            result = operation.database_backwards('timescale', schema_editor, state, state)
            # Should not raise an error due to if_exists=True in disable_compression
    
    def test_enable_compression_with_segmentby(self):
        """Test enabling compression with segment by columns."""
        operation = EnableCompression(
            model_name='TestMigrationModel',
            compress_orderby=['time'],
            compress_segmentby=['device'],
            if_not_exists=True
        )
        
        # Test forward migration
        state = self.get_project_state()
        with self.get_schema_editor() as schema_editor:
            operation.database_forwards('timescale', schema_editor, state, state)
        
        # Verify compression was enabled
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT compression_enabled FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'timescale_testmigrationmodel'
            """)
            result = cursor.fetchone()
            self.assertIsNotNone(result)
            self.assertTrue(result[0])


class AddCompressionPolicyTests(MigrationOperationTestCase):
    """Tests for AddCompressionPolicy migration operation."""
    
    def test_add_compression_policy_forward(self):
        """Test adding a compression policy in forward migration."""
        # First enable compression
        TestMigrationModel.timescale.enable_compression(
            compress_orderby=['time'],
            if_not_exists=True
        )
        
        operation = AddCompressionPolicy(
            model_name='TestMigrationModel',
            compress_after='30 days',
            if_not_exists=True
        )
        
        # Test forward migration
        state = self.get_project_state()
        with self.get_schema_editor() as schema_editor:
            operation.database_forwards('timescale', schema_editor, state, state)
        
        # Verify the policy was created
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE proc_name = 'policy_compression'
                AND hypertable_name = 'timescale_testmigrationmodel'
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)
    
    def test_add_compression_policy_backward(self):
        """Test removing a compression policy in backward migration."""
        # First enable compression and add policy
        TestMigrationModel.timescale.enable_compression(
            compress_orderby=['time'],
            if_not_exists=True
        )
        TestMigrationModel.timescale.add_compression_policy(
            compress_after='30 days',
            if_not_exists=True
        )
        
        operation = AddCompressionPolicy(
            model_name='TestMigrationModel',
            compress_after='30 days',
            if_not_exists=True
        )
        
        # Test backward migration
        state = self.get_project_state()
        with self.get_schema_editor() as schema_editor:
            operation.database_backwards('timescale', schema_editor, state, state)
        
        # Verify the policy was removed
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE proc_name = 'policy_compression'
                AND hypertable_name = 'timescale_testmigrationmodel'
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 0)


class RemoveCompressionPolicyTests(MigrationOperationTestCase):
    """Tests for RemoveCompressionPolicy migration operation."""
    
    def test_remove_compression_policy_forward(self):
        """Test removing a compression policy in forward migration."""
        # First enable compression and add policy
        TestMigrationModel.timescale.enable_compression(
            compress_orderby=['time'],
            if_not_exists=True
        )
        TestMigrationModel.timescale.add_compression_policy(
            compress_after='30 days',
            if_not_exists=True
        )
        
        operation = RemoveCompressionPolicy(
            model_name='TestMigrationModel',
            if_exists=True
        )
        
        # Test forward migration
        state = self.get_project_state()
        with self.get_schema_editor() as schema_editor:
            operation.database_forwards('timescale', schema_editor, state, state)
        
        # Verify the policy was removed
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE proc_name = 'policy_compression'
                AND hypertable_name = 'timescale_testmigrationmodel'
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 0)
    
    def test_remove_compression_policy_backward_not_reversible(self):
        """Test that backward migration raises NotImplementedError."""
        operation = RemoveCompressionPolicy(
            model_name='TestMigrationModel',
            if_exists=True
        )
        
        state = self.get_project_state()
        with self.get_schema_editor() as schema_editor:
            with self.assertRaises(NotImplementedError):
                operation.database_backwards('timescale', schema_editor, state, state)


class MigrationOperationIntegrationTests(MigrationOperationTestCase):
    """Integration tests for multiple migration operations."""
    
    def test_full_policy_setup_workflow(self):
        """Test a complete workflow of setting up compression and retention policies."""
        # Step 1: Enable compression
        enable_compression_op = EnableCompression(
            model_name='TestMigrationModel',
            compress_orderby=['time'],
            compress_segmentby=['device'],
            if_not_exists=True
        )
        
        # Step 2: Add compression policy
        add_compression_policy_op = AddCompressionPolicy(
            model_name='TestMigrationModel',
            compress_after='7 days',
            if_not_exists=True
        )
        
        # Step 3: Add retention policy
        add_retention_policy_op = AddRetentionPolicy(
            model_name='TestMigrationModel',
            drop_after='90 days',
            if_not_exists=True
        )
        
        state = self.get_project_state()
        
        # Execute all operations
        with self.get_schema_editor() as schema_editor:
            enable_compression_op.database_forwards('timescale', schema_editor, state, state)
            add_compression_policy_op.database_forwards('timescale', schema_editor, state, state)
            add_retention_policy_op.database_forwards('timescale', schema_editor, state, state)
        
        # Verify compression is enabled
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT compression_enabled FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'timescale_testmigrationmodel'
            """)
            result = cursor.fetchone()
            self.assertIsNotNone(result)
            self.assertTrue(result[0])
        
        # Verify compression policy exists
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE proc_name = 'policy_compression'
                AND hypertable_name = 'timescale_testmigrationmodel'
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)
        
        # Verify retention policy exists
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE proc_name = 'policy_retention'
                AND hypertable_name = 'timescale_testmigrationmodel'
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)
    
    def test_operation_descriptions(self):
        """Test that operations have proper descriptions."""
        add_retention = AddRetentionPolicy(
            model_name='TestModel',
            drop_after='60 days'
        )
        self.assertIn('Add retention policy', add_retention.describe())
        self.assertIn('TestModel', add_retention.describe())
        
        remove_retention = RemoveRetentionPolicy(
            model_name='TestModel'
        )
        self.assertIn('Remove retention policy', remove_retention.describe())
        self.assertIn('TestModel', remove_retention.describe())
        
        enable_compression = EnableCompression(
            model_name='TestModel'
        )
        self.assertIn('Enable compression', enable_compression.describe())
        self.assertIn('TestModel', enable_compression.describe())
        
        add_compression = AddCompressionPolicy(
            model_name='TestModel',
            compress_after='30 days'
        )
        self.assertIn('Add compression policy', add_compression.describe())
        self.assertIn('TestModel', add_compression.describe())
        
        remove_compression = RemoveCompressionPolicy(
            model_name='TestModel'
        )
        self.assertIn('Remove compression policy', remove_compression.describe())
        self.assertIn('TestModel', remove_compression.describe())
    
    def test_migration_name_fragments(self):
        """Test that operations generate proper migration name fragments."""
        add_retention = AddRetentionPolicy(
            model_name='TestModel',
            drop_after='60 days'
        )
        self.assertEqual(add_retention.migration_name_fragment, 'add_retention_policy_testmodel')
        
        remove_retention = RemoveRetentionPolicy(
            model_name='TestModel'
        )
        self.assertEqual(remove_retention.migration_name_fragment, 'remove_retention_policy_testmodel')
        
        enable_compression = EnableCompression(
            model_name='TestModel'
        )
        self.assertEqual(enable_compression.migration_name_fragment, 'enable_compression_testmodel')
        
        add_compression = AddCompressionPolicy(
            model_name='TestModel',
            compress_after='30 days'
        )
        self.assertEqual(add_compression.migration_name_fragment, 'add_compression_policy_testmodel')
        
        remove_compression = RemoveCompressionPolicy(
            model_name='TestModel'
        )
        self.assertEqual(remove_compression.migration_name_fragment, 'remove_compression_policy_testmodel')
