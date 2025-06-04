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
from timescale.db.models.fields import TimescaleDateTimeField
from timescale.db.models.managers import TimescaleManager


# Define test model (self-contained, no external dependencies)
class PolicyTestMetric(models.Model):
    """Test model with TimescaleDateTimeField."""
    time = TimescaleDateTimeField(interval="1 day")
    temperature = models.FloatField(default=0.0)
    device = models.IntegerField(default=0)

    objects = models.Manager()
    timescale = TimescaleManager()

    class Meta:
        app_label = 'timescale'
        db_table = 'timescale_policytestmetric'


class RetentionPolicyTests(TransactionTestCase):
    """Tests for TimescaleDB retention policies."""

    @classmethod
    def setUpClass(cls):
        """Set up test data."""
        super().setUpClass()

        # Create the test table
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(PolicyTestMetric)

        # Create hypertable
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT create_hypertable('timescale_policytestmetric', 'time', if_not_exists => TRUE)"
            )

    @classmethod
    def tearDownClass(cls):
        """Clean up test data."""
        # Drop the test table
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS timescale_policytestmetric CASCADE")

        super().tearDownClass()

    def setUp(self):
        """Set up test data."""
        # Create some test data
        self.timestamp = timezone.now()
        PolicyTestMetric.objects.create(
            time=self.timestamp - timedelta(days=30),
            temperature=10.0,
            device=1
        )
        PolicyTestMetric.objects.create(
            time=self.timestamp - timedelta(days=60),
            temperature=15.0,
            device=1
        )
        PolicyTestMetric.objects.create(
            time=self.timestamp - timedelta(days=90),
            temperature=20.0,
            device=1
        )
    
    def test_add_retention_policy(self):
        """Test adding a retention policy."""
        # Add a retention policy to drop data older than 60 days
        job_id = PolicyTestMetric.timescale.add_retention_policy(
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
        job_id = PolicyTestMetric.timescale.add_retention_policy(
            drop_after='60 days',
            if_not_exists=True
        )
        
        # Remove the policy
        result = PolicyTestMetric.timescale.remove_retention_policy(if_exists=True)
        
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

        # Create the test table
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(PolicyTestMetric)

        # Create hypertable
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT create_hypertable('timescale_policytestmetric', 'time', if_not_exists => TRUE)"
            )

    @classmethod
    def tearDownClass(cls):
        """Clean up test data."""
        # Drop the test table
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS timescale_policytestmetric CASCADE")

        super().tearDownClass()

    def setUp(self):
        """Set up test data."""
        # Create some test data
        self.timestamp = timezone.now()
        PolicyTestMetric.objects.create(
            time=self.timestamp - timedelta(days=30),
            temperature=10.0,
            device=1
        )
        PolicyTestMetric.objects.create(
            time=self.timestamp - timedelta(days=60),
            temperature=15.0,
            device=1
        )
        PolicyTestMetric.objects.create(
            time=self.timestamp - timedelta(days=90),
            temperature=20.0,
            device=1
        )
    
    def test_enable_compression(self):
        """Test enabling compression on a hypertable."""
        # Enable compression
        result = PolicyTestMetric.timescale.enable_compression(
            compress_orderby=['time'],
            if_not_exists=True
        )
        
        # Check that compression was enabled
        self.assertTrue(result)
        
        # Check that compression is enabled in the database
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT compression_enabled FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'timescale_policytestmetric'
            """)
            result = cursor.fetchone()
            self.assertTrue(result[0])
    
    def test_add_compression_policy(self):
        """Test adding a compression policy."""
        # Enable compression first
        PolicyTestMetric.timescale.enable_compression(
            compress_orderby=['time'],
            if_not_exists=True
        )
        
        # Add a compression policy to compress data older than 30 days
        job_id = PolicyTestMetric.timescale.add_compression_policy(
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
        PolicyTestMetric.timescale.enable_compression(
            compress_orderby=['time'],
            if_not_exists=True
        )
        
        # Add a compression policy
        job_id = PolicyTestMetric.timescale.add_compression_policy(
            compress_after='30 days',
            if_not_exists=True
        )
        
        # Remove the policy
        result = PolicyTestMetric.timescale.remove_compression_policy(if_exists=True)
        
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
        PolicyTestMetric.timescale.enable_compression(
            compress_orderby=['time'],
            if_not_exists=True
        )
        
        # Get compression stats
        stats = PolicyTestMetric.timescale.get_compression_stats()
        
        # Check that stats were returned
        self.assertIsInstance(stats, list)
        
        # There should be at least one row for our hypertable
        self.assertTrue(len(stats) > 0)
