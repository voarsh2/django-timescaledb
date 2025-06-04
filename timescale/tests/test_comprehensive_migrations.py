"""
Comprehensive tests for TimescaleDB migration operations and declarative policies.

This test suite combines unit tests and integration tests to thoroughly test:
1. Migration operation functionality (unit tests)
2. Real migration scenarios with data (integration tests)
3. Edge cases and policy changes
4. Both new and existing model scenarios
"""
import os
import sys
import unittest
import tempfile
from datetime import timedelta

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
from django.db.migrations.autodetector import MigrationAutodetector
from django.utils import timezone

# Import TimescaleDB components
from timescale.db.models.fields import TimescaleDateTimeField
from timescale.db.models.managers import TimescaleManager
from timescale.db.migrations.operations import (
    ApplyTimescalePolicies,
    RemoveTimescalePolicies,
)


class MigrationTestModel(models.Model):
    """Test model for migration operations."""
    time = TimescaleDateTimeField(interval="1 day")
    temperature = models.FloatField(default=0.0)
    device = models.IntegerField(default=0)

    objects = models.Manager()
    timescale = TimescaleManager()

    class Meta:
        app_label = 'timescale'
        db_table = 'test_timescale_model'


class MigrationTestModelWithPolicies(models.Model):
    """Test model with TimescaleDB policies defined."""
    timestamp = TimescaleDateTimeField(interval="1 hour")
    sensor_id = models.CharField(max_length=50)
    temperature = models.FloatField()
    humidity = models.FloatField()

    objects = models.Manager()
    timescale = TimescaleManager()

    class Meta:
        app_label = 'timescale'
        db_table = 'test_timescale_model_with_policies'

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


class MigrationOperationUnitTests(unittest.TestCase):
    """Unit tests for migration operations that don't require a database."""

    def test_apply_timescale_policies_init(self):
        """Test ApplyTimescalePolicies initialization."""
        operation = ApplyTimescalePolicies(
            model_name='TestModel',
            compression_settings={'enabled': True, 'compress_orderby': ['time']},
            compression_policy={'compress_after': '7 days'},
            retention_policy={'drop_after': '90 days'}
        )

        self.assertEqual(operation.model_name, 'TestModel')
        self.assertEqual(operation.compression_settings['enabled'], True)
        self.assertEqual(operation.compression_policy['compress_after'], '7 days')
        self.assertEqual(operation.retention_policy['drop_after'], '90 days')

    def test_apply_timescale_policies_deconstruct(self):
        """Test ApplyTimescalePolicies deconstruction for serialization."""
        operation = ApplyTimescalePolicies(
            model_name='TestModel',
            compression_settings={'enabled': True},
            compression_policy={'compress_after': '7 days'},
            retention_policy={'drop_after': '90 days'}
        )

        name, args, kwargs = operation.deconstruct()

        self.assertEqual(name, 'ApplyTimescalePolicies')
        self.assertEqual(args, [])
        self.assertEqual(kwargs['model_name'], 'TestModel')
        self.assertIn('compression_settings', kwargs)
        self.assertIn('compression_policy', kwargs)
        self.assertIn('retention_policy', kwargs)

    def test_apply_timescale_policies_describe(self):
        """Test ApplyTimescalePolicies description."""
        operation = ApplyTimescalePolicies(
            model_name='TestModel',
            compression_settings={'enabled': True},
            compression_policy={'compress_after': '7 days'},
            retention_policy={'drop_after': '90 days'}
        )

        description = operation.describe()
        self.assertIn('Apply TimescaleDB', description)
        self.assertIn('TestModel', description)
        self.assertIn('compression', description)
        self.assertIn('retention policy', description)

    def test_remove_timescale_policies_init(self):
        """Test RemoveTimescalePolicies initialization."""
        operation = RemoveTimescalePolicies(
            model_name='TestModel',
            remove_compression_policy=True,
            remove_retention_policy=True
        )

        self.assertEqual(operation.model_name, 'TestModel')
        self.assertTrue(operation.remove_compression_policy)
        self.assertTrue(operation.remove_retention_policy)

    def test_remove_timescale_policies_deconstruct(self):
        """Test RemoveTimescalePolicies deconstruction."""
        operation = RemoveTimescalePolicies(
            model_name='TestModel',
            remove_compression_policy=True,
            remove_retention_policy=False
        )

        name, args, kwargs = operation.deconstruct()

        self.assertEqual(name, 'RemoveTimescalePolicies')
        self.assertEqual(list(args), [])
        self.assertEqual(kwargs['model_name'], 'TestModel')
        self.assertEqual(kwargs['remove_compression_policy'], True)
        self.assertEqual(kwargs['remove_retention_policy'], False)

    def test_state_forwards_no_op(self):
        """Test that state_forwards methods don't modify state."""
        operations = [
            ApplyTimescalePolicies(model_name='TestModel'),
            RemoveTimescalePolicies(model_name='TestModel'),
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


class MigrationOperationIntegrationTests(TransactionTestCase):
    """Integration tests for migration operations with real database."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test data."""
        super().setUpClass()
        
        # Create the test table
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(MigrationTestModel)
            
        # Create hypertable
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT create_hypertable('test_timescale_model', 'time', if_not_exists => TRUE)"
            )
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test data."""
        # Drop the test table
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS test_timescale_model CASCADE")
            
        super().tearDownClass()
    
    def setUp(self):
        """Set up test data."""
        # Create some test data
        self.timestamp = timezone.now()
        MigrationTestModel.objects.create(
            time=self.timestamp - timedelta(days=30),
            temperature=10.0,
            device=1
        )
        MigrationTestModel.objects.create(
            time=self.timestamp - timedelta(days=60),
            temperature=15.0,
            device=1
        )
    
    def tearDown(self):
        """Clean up after each test."""
        # Remove any policies that might have been created
        try:
            MigrationTestModel.timescale.remove_retention_policy(if_exists=True)
        except:
            pass
        try:
            MigrationTestModel.timescale.remove_compression_policy(if_exists=True)
        except:
            pass
        
        # Clear test data
        MigrationTestModel.objects.all().delete()
    
    def get_schema_editor(self):
        """Get a schema editor for testing."""
        return connection.schema_editor()
    
    def get_project_state(self):
        """Get a project state for testing."""
        # For our TimescaleDB operations, we don't need the model state
        # since they work directly with the database
        return ProjectState()

    def test_apply_timescale_policies_forward(self):
        """Test applying TimescaleDB policies in forward migration."""
        operation = ApplyTimescalePolicies(
            model_name='MigrationTestModel',
            compression_settings={
                'enabled': True,
                'compress_orderby': ['time'],
                'compress_segmentby': ['device'],
            },
            compression_policy={
                'compress_after': '30 days',
                'schedule_interval': '1 hour',
            },
            retention_policy={
                'drop_after': '90 days',
                'schedule_interval': '1 day',
            }
        )
        
        # Test forward migration
        state = self.get_project_state()
        with self.get_schema_editor() as schema_editor:
            operation.database_forwards('timescale', schema_editor, state, state)
        
        # Verify compression was enabled
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT compression_enabled FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'test_timescale_model'
            """)
            result = cursor.fetchone()
            self.assertIsNotNone(result)
            self.assertTrue(result[0])
        
        # Verify compression policy exists
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE proc_name = 'policy_compression'
                AND hypertable_name = 'test_timescale_model'
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)
        
        # Verify retention policy exists
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE proc_name = 'policy_retention'
                AND hypertable_name = 'test_timescale_model'
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)

    def test_apply_timescale_policies_backward(self):
        """Test removing TimescaleDB policies in backward migration."""
        # First apply policies
        MigrationTestModel.timescale.enable_compression(
            compress_orderby=['time'],
            if_not_exists=True
        )
        MigrationTestModel.timescale.add_compression_policy(
            compress_after='30 days',
            if_not_exists=True
        )
        MigrationTestModel.timescale.add_retention_policy(
            drop_after='90 days',
            if_not_exists=True
        )
        
        operation = ApplyTimescalePolicies(
            model_name='MigrationTestModel',
            compression_settings={'enabled': True},
            compression_policy={'compress_after': '30 days'},
            retention_policy={'drop_after': '90 days'}
        )
        
        # Test backward migration
        state = self.get_project_state()
        with self.get_schema_editor() as schema_editor:
            operation.database_backwards('timescale', schema_editor, state, state)
        
        # Verify policies were removed
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE hypertable_name = 'test_timescale_model'
                AND proc_name IN ('policy_compression', 'policy_retention')
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 0)


    def test_remove_timescale_policies_forward(self):
        """Test removing TimescaleDB policies in forward migration."""
        # First clean up any existing policies and compression
        try:
            MigrationTestModel.timescale.remove_compression_policy(if_exists=True)
            MigrationTestModel.timescale.remove_retention_policy(if_exists=True)
        except:
            pass

        # Apply policies with consistent compression settings
        MigrationTestModel.timescale.enable_compression(
            compress_orderby=['time'],
            compress_segmentby=['device'],  # Include segmentby to avoid conflicts
            if_not_exists=True
        )
        MigrationTestModel.timescale.add_compression_policy(
            compress_after='30 days',
            if_not_exists=True
        )
        MigrationTestModel.timescale.add_retention_policy(
            drop_after='90 days',
            if_not_exists=True
        )

        operation = RemoveTimescalePolicies(
            model_name='MigrationTestModel',
            remove_compression_policy=True,
            remove_retention_policy=True
        )

        # Test forward migration
        state = self.get_project_state()
        with self.get_schema_editor() as schema_editor:
            operation.database_forwards('timescale', schema_editor, state, state)

        # Verify policies were removed
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM timescaledb_information.jobs
                WHERE hypertable_name = 'test_timescale_model'
                AND proc_name IN ('policy_compression', 'policy_retention')
            """)
            count = cursor.fetchone()[0]
            self.assertEqual(count, 0)

    def test_remove_timescale_policies_backward_not_reversible(self):
        """Test that backward migration raises NotImplementedError."""
        operation = RemoveTimescalePolicies(
            model_name='MigrationTestModel',
            remove_compression_policy=True,
            remove_retention_policy=True
        )

        state = self.get_project_state()
        with self.get_schema_editor() as schema_editor:
            with self.assertRaises(NotImplementedError):
                operation.database_backwards('timescale', schema_editor, state, state)


class SelfContainedMigrationTests(TransactionTestCase):
    """Self-contained tests that don't depend on external models or migrations."""

    def setUp(self):
        """Set up for each test."""
        self.timestamp = timezone.now()

    def tearDown(self):
        """Clean up after each test."""
        # Clean up any test tables
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS test_self_contained CASCADE")

    def create_test_table_and_model(self, table_name='test_self_contained'):
        """Create a test table and corresponding model."""
        with connection.cursor() as cursor:
            # Create table
            cursor.execute(f"""
                CREATE TABLE {table_name} (
                    id SERIAL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    value FLOAT NOT NULL,
                    PRIMARY KEY (id, timestamp)
                )
            """)

            # Create hypertable
            cursor.execute(f"SELECT create_hypertable('{table_name}', 'timestamp')")

            # Insert test data
            for i in range(10):
                cursor.execute(f"""
                    INSERT INTO {table_name} (timestamp, value)
                    VALUES (%s, %s)
                """, [
                    self.timestamp - timedelta(days=i),
                    float(i * 10)
                ])

        # Create and register a test model
        class TestSelfContainedModel(models.Model):
            timestamp = TimescaleDateTimeField(interval="1 hour")
            value = models.FloatField()

            objects = models.Manager()
            timescale = TimescaleManager()

            class Meta:
                app_label = 'timescale'
                db_table = table_name

        # Register the model temporarily
        from django.apps import apps
        apps.register_model('timescale', TestSelfContainedModel)
        return TestSelfContainedModel

    def test_new_model_with_policies_migration(self):
        """Test creating a new model with policies from scratch."""
        # Create the table and model
        TestModel = self.create_test_table_and_model()

        try:
            # Simulate applying policies via migration
            operation = ApplyTimescalePolicies(
                model_name='TestSelfContainedModel',
                compression_settings={
                    'enabled': True,
                    'compress_orderby': ['timestamp'],
                },
                retention_policy={
                    'drop_after': '90 days',
                    'schedule_interval': '1 day',
                }
            )

            # Apply the operation
            state = ProjectState()
            with connection.schema_editor() as schema_editor:
                operation.database_forwards('timescale', schema_editor, state, state)

            # Verify the policies were applied
            with connection.cursor() as cursor:
                # Check compression enabled
                cursor.execute("""
                    SELECT compression_enabled FROM timescaledb_information.hypertables
                    WHERE hypertable_name = 'test_self_contained'
                """)
                result = cursor.fetchone()
                self.assertTrue(result[0])

                # Check retention policy exists
                cursor.execute("""
                    SELECT COUNT(*) FROM timescaledb_information.jobs
                    WHERE hypertable_name = 'test_self_contained'
                    AND proc_name = 'policy_retention'
                """)
                count = cursor.fetchone()[0]
                self.assertEqual(count, 1)

        finally:
            # Unregister the model
            from django.apps import apps
            try:
                del apps.all_models['timescale']['testselfcontainedmodel']
            except KeyError:
                pass

    def test_policy_update_migration(self):
        """Test updating policies on an existing model."""
        # Create table and model
        TestModel = self.create_test_table_and_model()

        try:
            # Apply initial policies
            initial_operation = ApplyTimescalePolicies(
                model_name='TestSelfContainedModel',
                retention_policy={'drop_after': '90 days', 'schedule_interval': '1 day'}
            )

            state = ProjectState()
            with connection.schema_editor() as schema_editor:
                initial_operation.database_forwards('timescale', schema_editor, state, state)

            # Verify initial policy
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT schedule_interval FROM timescaledb_information.jobs
                    WHERE hypertable_name = 'test_self_contained'
                    AND proc_name = 'policy_retention'
                """)
                result = cursor.fetchone()
                self.assertEqual(result[0], timedelta(days=1))

            # Now change the policy
            changed_operation = ApplyTimescalePolicies(
                model_name='TestSelfContainedModel',
                retention_policy={'drop_after': '60 days', 'schedule_interval': '12 hours'}
            )

            with connection.schema_editor() as schema_editor:
                changed_operation.database_forwards('timescale', schema_editor, state, state)

            # Verify policy was updated
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT schedule_interval FROM timescaledb_information.jobs
                    WHERE hypertable_name = 'test_self_contained'
                    AND proc_name = 'policy_retention'
                """)
                result = cursor.fetchone()
                self.assertEqual(result[0], timedelta(hours=12))

        finally:
            # Unregister the model
            from django.apps import apps
            try:
                del apps.all_models['timescale']['testselfcontainedmodel']
            except KeyError:
                pass


class EdgeCaseTests(TransactionTestCase):
    """Tests for edge cases and error conditions."""

    def test_apply_policies_to_nonexistent_model(self):
        """Test applying policies to a model that doesn't exist."""
        operation = ApplyTimescalePolicies(
            model_name='NonExistentModel',
            retention_policy={'drop_after': '90 days'}
        )

        state = ProjectState()
        with connection.schema_editor() as schema_editor:
            # This should raise an exception
            with self.assertRaises(Exception):
                operation.database_forwards('timescale', schema_editor, state, state)

    def test_apply_policies_with_invalid_intervals(self):
        """Test applying policies with invalid time intervals."""
        # Create a test table first
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE test_invalid_table (
                    id SERIAL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (id, timestamp)
                )
            """)
            cursor.execute("SELECT create_hypertable('test_invalid_table', 'timestamp')")

        try:
            operation = ApplyTimescalePolicies(
                model_name='TestModel',
                retention_policy={'drop_after': 'invalid_interval'}
            )

            state = ProjectState()
            with connection.schema_editor() as schema_editor:
                # This should raise an exception due to invalid interval
                with self.assertRaises(Exception):
                    operation.database_forwards('timescale', schema_editor, state, state)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE IF EXISTS test_invalid_table CASCADE")

    def test_policy_update_functionality(self):
        """Test that policy updates actually change the database policies."""
        # Create a test table
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS test_policy_update CASCADE")
            cursor.execute("""
                CREATE TABLE test_policy_update (
                    id SERIAL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    value FLOAT,
                    PRIMARY KEY (id, timestamp)
                )
            """)
            cursor.execute("SELECT create_hypertable('test_policy_update', 'timestamp')")

        # Create a test model dynamically
        class TestPolicyUpdateModel(models.Model):
            timestamp = TimescaleDateTimeField(interval="1 hour")
            value = models.FloatField()

            objects = models.Manager()
            timescale = TimescaleManager()

            class Meta:
                app_label = 'timescale'
                db_table = 'test_policy_update'

        # Register the model temporarily
        from django.apps import apps
        apps.register_model('timescale', TestPolicyUpdateModel)

        try:
            # Apply initial policies
            initial_operation = ApplyTimescalePolicies(
                model_name='TestPolicyUpdateModel',
                compression_settings={'enabled': True, 'compress_orderby': ['timestamp']},
                compression_policy={'compress_after': '30 days', 'schedule_interval': '1 hour'},
                retention_policy={'drop_after': '90 days', 'schedule_interval': '1 day'}
            )

            state = ProjectState()
            with connection.schema_editor() as schema_editor:
                initial_operation.database_forwards('timescale', schema_editor, state, state)

            # Verify initial policies
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT config FROM timescaledb_information.jobs
                    WHERE hypertable_name = 'test_policy_update'
                    AND proc_name = 'policy_compression'
                """)
                result = cursor.fetchone()
                self.assertIn('"compress_after": "30 days"', result[0])

            # Apply updated policies
            updated_operation = ApplyTimescalePolicies(
                model_name='TestPolicyUpdateModel',
                compression_settings={'enabled': True, 'compress_orderby': ['timestamp']},
                compression_policy={'compress_after': '14 days', 'schedule_interval': '30 minutes'},
                retention_policy={'drop_after': '60 days', 'schedule_interval': '12 hours'}
            )

            with connection.schema_editor() as schema_editor:
                updated_operation.database_forwards('timescale', schema_editor, state, state)

            # Verify policies were updated
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT config FROM timescaledb_information.jobs
                    WHERE hypertable_name = 'test_policy_update'
                    AND proc_name = 'policy_compression'
                """)
                result = cursor.fetchone()
                self.assertIn('"compress_after": "14 days"', result[0])

                cursor.execute("""
                    SELECT config FROM timescaledb_information.jobs
                    WHERE hypertable_name = 'test_policy_update'
                    AND proc_name = 'policy_retention'
                """)
                result = cursor.fetchone()
                self.assertIn('"drop_after": "60 days"', result[0])

        finally:
            # Unregister the model
            try:
                del apps.all_models['timescale']['testpolicyupdatemodel']
            except KeyError:
                pass

            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE IF EXISTS test_policy_update CASCADE")


class IndividualOperationTests(TransactionTestCase):
    """Tests for individual operations (backward compatibility)."""

    def setUp(self):
        """Set up test table."""
        with connection.cursor() as cursor:
            # Clean up any existing table first
            cursor.execute("DROP TABLE IF EXISTS test_individual_ops CASCADE")

            cursor.execute("""
                CREATE TABLE test_individual_ops (
                    id SERIAL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    value FLOAT,
                    PRIMARY KEY (id, timestamp)
                )
            """)
            cursor.execute("SELECT create_hypertable('test_individual_ops', 'timestamp')")

    def tearDown(self):
        """Clean up test table."""
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS test_individual_ops CASCADE")

    def test_add_retention_policy_operation(self):
        """Test AddRetentionPolicy operation."""
        from timescale.db.migrations import AddRetentionPolicy

        # Create a test model dynamically
        class TestIndividualOpsModel(models.Model):
            timestamp = TimescaleDateTimeField(interval="1 hour")
            value = models.FloatField()

            objects = models.Manager()
            timescale = TimescaleManager()

            class Meta:
                app_label = 'timescale'
                db_table = 'test_individual_ops'

        # Register the model temporarily
        from django.apps import apps
        apps.register_model('timescale', TestIndividualOpsModel)

        try:
            operation = AddRetentionPolicy(
                model_name='TestIndividualOpsModel',
                drop_after='90 days',
                schedule_interval='1 day'
            )

            # Test forward migration
            state = ProjectState()
            with connection.schema_editor() as schema_editor:
                operation.database_forwards('timescale', schema_editor, state, state)

            # Verify policy was created
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM timescaledb_information.jobs
                    WHERE hypertable_name = 'test_individual_ops'
                    AND proc_name = 'policy_retention'
                """)
                count = cursor.fetchone()[0]
                self.assertEqual(count, 1)

        finally:
            # Unregister the model
            try:
                del apps.all_models['timescale']['testindividualopsmodel']
            except KeyError:
                pass

    def test_enable_compression_operation(self):
        """Test EnableCompression operation."""
        from timescale.db.migrations import EnableCompression

        # Create a test model dynamically
        class TestEnableCompressionModel(models.Model):
            timestamp = TimescaleDateTimeField(interval="1 hour")
            value = models.FloatField()

            objects = models.Manager()
            timescale = TimescaleManager()

            class Meta:
                app_label = 'timescale'
                db_table = 'test_individual_ops'

        # Register the model temporarily
        from django.apps import apps
        apps.register_model('timescale', TestEnableCompressionModel)

        try:
            operation = EnableCompression(
                model_name='TestEnableCompressionModel',
                compress_orderby=['timestamp'],
                compress_segmentby=['value']
            )

            # Test forward migration
            state = ProjectState()
            with connection.schema_editor() as schema_editor:
                operation.database_forwards('timescale', schema_editor, state, state)

            # Verify compression was enabled
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT compression_enabled FROM timescaledb_information.hypertables
                    WHERE hypertable_name = 'test_individual_ops'
                """)
                result = cursor.fetchone()
                self.assertTrue(result[0])

        finally:
            # Unregister the model
            try:
                del apps.all_models['timescale']['testenablecompressionmodel']
            except KeyError:
                pass

    def test_add_compression_policy_operation(self):
        """Test AddCompressionPolicy operation."""
        from timescale.db.migrations import EnableCompression, AddCompressionPolicy

        # Create a test model dynamically
        class TestCompressionPolicyModel(models.Model):
            timestamp = TimescaleDateTimeField(interval="1 hour")
            value = models.FloatField()

            objects = models.Manager()
            timescale = TimescaleManager()

            class Meta:
                app_label = 'timescale'
                db_table = 'test_individual_ops'

        # Register the model temporarily
        from django.apps import apps
        apps.register_model('timescale', TestCompressionPolicyModel)

        try:
            # First enable compression
            enable_op = EnableCompression(
                model_name='TestCompressionPolicyModel',
                compress_orderby=['timestamp']
            )

            state = ProjectState()
            with connection.schema_editor() as schema_editor:
                enable_op.database_forwards('timescale', schema_editor, state, state)

            # Then add compression policy
            policy_op = AddCompressionPolicy(
                model_name='TestCompressionPolicyModel',
                compress_after='7 days',
                schedule_interval='1 hour'
            )

            with connection.schema_editor() as schema_editor:
                policy_op.database_forwards('timescale', schema_editor, state, state)

            # Verify policy was created
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM timescaledb_information.jobs
                    WHERE hypertable_name = 'test_individual_ops'
                    AND proc_name = 'policy_compression'
                """)
                count = cursor.fetchone()[0]
                self.assertEqual(count, 1)

        finally:
            # Unregister the model
            try:
                del apps.all_models['timescale']['testcompressionpolicymodel']
            except KeyError:
                pass


class MigrationHistoryTests(TransactionTestCase):
    """Tests for migration history detection."""

    def test_migration_loader_approach(self):
        """Test that migration history detection uses MigrationLoader correctly."""
        from timescale.db.migrations.autodetector import get_last_applied_policies_from_migrations

        # This should not raise an exception and should return None for non-existent model
        result = get_last_applied_policies_from_migrations('test_app', 'NonExistentModel', None)
        self.assertIsNone(result)

    def test_disk_fallback_approach(self):
        """Test that disk fallback works when MigrationLoader fails."""
        from timescale.db.migrations.autodetector import get_policies_from_disk_fallback

        # This should not raise an exception and should return None for non-existent app
        result = get_policies_from_disk_fallback('nonexistent_app', 'NonExistentModel')
        self.assertIsNone(result)


class RealDataEdgeCaseTests(TransactionTestCase):
    """Tests for edge cases with real data scenarios."""

    def setUp(self):
        """Set up test table with real data."""
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS test_real_data CASCADE")
            cursor.execute("""
                CREATE TABLE test_real_data (
                    id SERIAL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    sensor_id VARCHAR(50) NOT NULL,
                    value FLOAT NOT NULL,
                    PRIMARY KEY (id, timestamp)
                )
            """)
            cursor.execute("SELECT create_hypertable('test_real_data', 'timestamp')")

            # Insert test data spanning different time periods
            cursor.execute("""
                INSERT INTO test_real_data (timestamp, sensor_id, value)
                SELECT
                    NOW() - (i || ' days')::INTERVAL,
                    'sensor_' || (i % 5),
                    random() * 100
                FROM generate_series(1, 100) i
            """)

    def tearDown(self):
        """Clean up test table."""
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS test_real_data CASCADE")

    def test_policy_changes_with_existing_data(self):
        """Test changing policies on tables with existing data."""
        # Create test model
        class TestRealDataModel(models.Model):
            timestamp = TimescaleDateTimeField(interval="1 hour")
            sensor_id = models.CharField(max_length=50)
            value = models.FloatField()

            objects = models.Manager()
            timescale = TimescaleManager()

            class Meta:
                app_label = 'timescale'
                db_table = 'test_real_data'

        from django.apps import apps
        apps.register_model('timescale', TestRealDataModel)

        try:
            # Apply initial policies
            initial_operation = ApplyTimescalePolicies(
                model_name='TestRealDataModel',
                compression_settings={'enabled': True, 'compress_orderby': ['timestamp']},
                compression_policy={'compress_after': '30 days', 'schedule_interval': '1 hour'},
                retention_policy={'drop_after': '90 days', 'schedule_interval': '1 day'}
            )

            state = ProjectState()
            with connection.schema_editor() as schema_editor:
                initial_operation.database_forwards('timescale', schema_editor, state, state)

            # Verify data count before policy change
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM test_real_data")
                initial_count = cursor.fetchone()[0]
                self.assertGreater(initial_count, 0)

            # Change policies
            updated_operation = ApplyTimescalePolicies(
                model_name='TestRealDataModel',
                compression_settings={'enabled': True, 'compress_orderby': ['timestamp']},
                compression_policy={'compress_after': '14 days', 'schedule_interval': '30 minutes'},
                retention_policy={'drop_after': '60 days', 'schedule_interval': '12 hours'}
            )

            with connection.schema_editor() as schema_editor:
                updated_operation.database_forwards('timescale', schema_editor, state, state)

            # Verify policies were updated
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT config FROM timescaledb_information.jobs
                    WHERE hypertable_name = 'test_real_data'
                    AND proc_name = 'policy_compression'
                """)
                result = cursor.fetchone()
                self.assertIn('"compress_after": "14 days"', result[0])

                # Verify data integrity maintained
                cursor.execute("SELECT COUNT(*) FROM test_real_data")
                final_count = cursor.fetchone()[0]
                self.assertGreater(final_count, 0)  # Data should still exist

        finally:
            try:
                del apps.all_models['timescale']['testrealdatamodel']
            except KeyError:
                pass

    def test_adding_policies_to_existing_hypertable(self):
        """Test adding policies to an existing hypertable that had no policies."""
        # Create test model
        class TestExistingHypertableModel(models.Model):
            timestamp = TimescaleDateTimeField(interval="1 hour")
            value = models.FloatField()

            objects = models.Manager()
            timescale = TimescaleManager()

            class Meta:
                app_label = 'timescale'
                db_table = 'test_real_data'

        from django.apps import apps
        apps.register_model('timescale', TestExistingHypertableModel)

        try:
            # Verify no policies exist initially
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM timescaledb_information.jobs
                    WHERE hypertable_name = 'test_real_data'
                """)
                initial_jobs = cursor.fetchone()[0]
                self.assertEqual(initial_jobs, 0)

            # Add policies to existing hypertable
            operation = ApplyTimescalePolicies(
                model_name='TestExistingHypertableModel',
                compression_settings={'enabled': True, 'compress_orderby': ['timestamp']},
                compression_policy={'compress_after': '7 days', 'schedule_interval': '2 hours'},
                retention_policy={'drop_after': '180 days', 'schedule_interval': '1 day'}
            )

            state = ProjectState()
            with connection.schema_editor() as schema_editor:
                operation.database_forwards('timescale', schema_editor, state, state)

            # Verify policies were added
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM timescaledb_information.jobs
                    WHERE hypertable_name = 'test_real_data'
                """)
                final_jobs = cursor.fetchone()[0]
                self.assertEqual(final_jobs, 2)  # compression + retention

                # Verify compression was enabled
                cursor.execute("""
                    SELECT compression_enabled FROM timescaledb_information.hypertables
                    WHERE hypertable_name = 'test_real_data'
                """)
                compression_enabled = cursor.fetchone()[0]
                self.assertTrue(compression_enabled)

        finally:
            try:
                del apps.all_models['timescale']['testexistinghypertablemodel']
            except KeyError:
                pass


class BackwardCompatibilityTests(TransactionTestCase):
    """Tests for backward compatibility with existing programmatic usage."""

    def test_declarative_and_programmatic_together(self):
        """Test that declarative and programmatic approaches work together."""
        # Create two test tables
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS test_declarative CASCADE")
            cursor.execute("DROP TABLE IF EXISTS test_programmatic CASCADE")

            cursor.execute("""
                CREATE TABLE test_declarative (
                    id SERIAL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    value FLOAT,
                    PRIMARY KEY (id, timestamp)
                )
            """)
            cursor.execute("SELECT create_hypertable('test_declarative', 'timestamp')")

            cursor.execute("""
                CREATE TABLE test_programmatic (
                    id SERIAL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    value FLOAT,
                    PRIMARY KEY (id, timestamp)
                )
            """)
            cursor.execute("SELECT create_hypertable('test_programmatic', 'timestamp')")

        try:
            # Create models
            class TestDeclarativeModel(models.Model):
                timestamp = TimescaleDateTimeField(interval="1 hour")
                value = models.FloatField()

                objects = models.Manager()
                timescale = TimescaleManager()

                class Meta:
                    app_label = 'timescale'
                    db_table = 'test_declarative'

            class TestProgrammaticModel(models.Model):
                timestamp = TimescaleDateTimeField(interval="1 hour")
                value = models.FloatField()

                objects = models.Manager()
                timescale = TimescaleManager()

                class Meta:
                    app_label = 'timescale'
                    db_table = 'test_programmatic'

            from django.apps import apps
            apps.register_model('timescale', TestDeclarativeModel)
            apps.register_model('timescale', TestProgrammaticModel)

            # Apply declarative policies
            declarative_operation = ApplyTimescalePolicies(
                model_name='TestDeclarativeModel',
                compression_settings={'enabled': True, 'compress_orderby': ['timestamp']},
                retention_policy={'drop_after': '90 days', 'schedule_interval': '1 day'}
            )

            state = ProjectState()
            with connection.schema_editor() as schema_editor:
                declarative_operation.database_forwards('timescale', schema_editor, state, state)

            # Apply programmatic policies using individual operations
            from timescale.db.migrations import EnableCompression, AddRetentionPolicy

            enable_compression = EnableCompression(
                model_name='TestProgrammaticModel',
                compress_orderby=['timestamp']
            )

            add_retention = AddRetentionPolicy(
                model_name='TestProgrammaticModel',
                drop_after='60 days',
                schedule_interval='12 hours'
            )

            with connection.schema_editor() as schema_editor:
                enable_compression.database_forwards('timescale', schema_editor, state, state)
                add_retention.database_forwards('timescale', schema_editor, state, state)

            # Verify both approaches worked
            with connection.cursor() as cursor:
                # Check declarative policies
                cursor.execute("""
                    SELECT COUNT(*) FROM timescaledb_information.jobs
                    WHERE hypertable_name = 'test_declarative'
                """)
                declarative_jobs = cursor.fetchone()[0]
                self.assertEqual(declarative_jobs, 1)  # retention only

                # Check programmatic policies
                cursor.execute("""
                    SELECT COUNT(*) FROM timescaledb_information.jobs
                    WHERE hypertable_name = 'test_programmatic'
                """)
                programmatic_jobs = cursor.fetchone()[0]
                self.assertEqual(programmatic_jobs, 1)  # retention only

                # Check compression enabled on both
                cursor.execute("""
                    SELECT COUNT(*) FROM timescaledb_information.hypertables
                    WHERE hypertable_name IN ('test_declarative', 'test_programmatic')
                    AND compression_enabled = true
                """)
                compressed_tables = cursor.fetchone()[0]
                self.assertEqual(compressed_tables, 2)  # Both tables

        finally:
            try:
                del apps.all_models['timescale']['testdeclarativemodel']
                del apps.all_models['timescale']['testprogrammaticmodel']
            except KeyError:
                pass

            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE IF EXISTS test_declarative CASCADE")
                cursor.execute("DROP TABLE IF EXISTS test_programmatic CASCADE")


if __name__ == '__main__':
    unittest.main()
