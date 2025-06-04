"""
Django app configuration for TimescaleDB.

This module handles the initialization of the TimescaleDB Django app,
including patching Django's migration system to support automatic
detection of TimescaleDB policy changes.
"""
from django.apps import AppConfig


class TimescaleConfig(AppConfig):
    """
    Configuration for the TimescaleDB Django app.
    
    This app config patches Django's migration autodetector to automatically
    detect changes in TimescaleDB policies defined in model classes.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'timescale'
    verbose_name = 'TimescaleDB'
    
    def ready(self):
        """
        Called when the app is ready.
        
        This method patches Django's migration system to include
        TimescaleDB policy detection.
        """
        # Import here to avoid circular imports
        from .db.migrations.autodetector import patch_migration_autodetector
        
        # Patch Django's migration autodetector
        patch_migration_autodetector()
