"""
TimescaleDB migration autodetector.

This module patches Django's migration autodetector to automatically
detect changes in TimescaleDB policies defined in model classes.
"""
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.state import ModelState
from django.apps import apps
from typing import Dict, List, Any, Optional

from .operations import ApplyTimescalePolicies, RemoveTimescalePolicies
from ..models.policies import get_model_timescale_policies
from ..models.fields import TimescaleDateTimeField


def has_timescale_field(model_class):
    """Check if a model has TimescaleDB fields."""
    if not model_class:
        return False

    for field in model_class._meta.get_fields():
        if isinstance(field, TimescaleDateTimeField):
            return True
    return False


def get_last_applied_policies_from_migrations(app_label: str, model_name: str, autodetector):
    """
    Get the last applied TimescaleDB policies for a model from migration history.

    This uses Django's MigrationLoader to find the most recent ApplyTimescalePolicies
    operation for the given model. This is more reliable than reading files directly.
    """
    try:
        from django.db.migrations.loader import MigrationLoader

        # Create a migration loader to access the migration graph
        loader = MigrationLoader(None, ignore_no_migrations=True)

        # Get all migrations for this app, sorted by name (which includes ordering)
        app_migrations = []
        for migration_key in loader.graph.nodes:
            if migration_key[0] == app_label:
                app_migrations.append(migration_key)

        # Sort by migration name to get chronological order
        app_migrations.sort(key=lambda x: x[1])

        # Look through migrations in reverse order to find the most recent policy
        for migration_key in reversed(app_migrations):
            migration = loader.graph.nodes[migration_key]

            # Check each operation in the migration
            for operation in migration.operations:
                if (hasattr(operation, 'model_name') and
                    hasattr(operation, '__class__') and
                    operation.__class__.__name__ == 'ApplyTimescalePolicies' and
                    operation.model_name.lower() == model_name.lower()):
                    # Found the most recent policy operation for this model
                    print(f"DEBUG: Found policies in migration {migration_key[1]}")
                    return {
                        'compression': getattr(operation, 'compression_settings', None),
                        'compression_policy': getattr(operation, 'compression_policy', None),
                        'retention_policy': getattr(operation, 'retention_policy', None),
                    }

        print(f"DEBUG: No policy operations found for {model_name}")
        return None

    except Exception as e:
        print(f"DEBUG: Error getting policies from migration history: {e}")
        # Fallback to disk reading approach if MigrationLoader fails
        return get_policies_from_disk_fallback(app_label, model_name)


def get_policies_from_disk_fallback(app_label: str, model_name: str):
    """
    Fallback method to read migration files from disk.

    This is used when the MigrationLoader approach fails.
    """
    import os
    import importlib.util
    from django.conf import settings

    try:
        # Find the app's migration directory
        app_config = None
        for app in settings.INSTALLED_APPS:
            if app.split('.')[-1] == app_label:
                app_config = app
                break

        if not app_config:
            return None

        # Get the migration directory path
        try:
            module = importlib.import_module(app_config)
            app_path = os.path.dirname(module.__file__)
            migrations_path = os.path.join(app_path, 'migrations')
        except:
            return None

        if not os.path.exists(migrations_path):
            return None

        # Get all migration files
        migration_files = []
        for filename in os.listdir(migrations_path):
            if filename.endswith('.py') and filename != '__init__.py':
                migration_files.append(filename)

        # Sort migration files by name (which includes ordering)
        migration_files.sort()

        # Look through migration files in reverse order
        for filename in reversed(migration_files):
            filepath = os.path.join(migrations_path, filename)

            try:
                # Load the migration module
                spec = importlib.util.spec_from_file_location(f"{app_label}.migrations.{filename[:-3]}", filepath)
                migration_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(migration_module)

                # Get the Migration class
                if hasattr(migration_module, 'Migration'):
                    migration = migration_module.Migration

                    # Check each operation in the migration
                    for operation in migration.operations:
                        if (hasattr(operation, 'model_name') and
                            hasattr(operation, '__class__') and
                            operation.__class__.__name__ == 'ApplyTimescalePolicies' and
                            operation.model_name.lower() == model_name.lower()):
                            # Found the most recent policy operation for this model
                            print(f"DEBUG: Found policies in migration {filename} (fallback)")
                            return {
                                'compression': getattr(operation, 'compression_settings', None),
                                'compression_policy': getattr(operation, 'compression_policy', None),
                                'retention_policy': getattr(operation, 'retention_policy', None),
                            }
            except Exception:
                continue

        return None

    except Exception:
        return None


def compare_model_policies(old_policies, new_policies):
    """
    Compare two policy definitions to determine if they are different.

    Args:
        old_policies: Previous policy definition (dict or TimescalePolicies object)
        new_policies: New policy definition (TimescalePolicies object)

    Returns:
        True if policies are different, False if they are the same
    """
    if old_policies is None and new_policies is None:
        return False

    if old_policies is None or new_policies is None:
        return True

    # Convert old_policies to comparable format
    if isinstance(old_policies, dict):
        old_compression = old_policies.get('compression')
        old_compression_policy = old_policies.get('compression_policy')
        old_retention_policy = old_policies.get('retention_policy')
    else:
        old_compression = getattr(old_policies, 'compression', None)
        old_compression_policy = getattr(old_policies, 'compression_policy', None)
        old_retention_policy = getattr(old_policies, 'retention_policy', None)

    # Get new policies
    new_compression = getattr(new_policies, 'compression', None)
    new_compression_policy = getattr(new_policies, 'compression_policy', None)
    new_retention_policy = getattr(new_policies, 'retention_policy', None)

    # Compare each policy type
    if old_compression != new_compression:
        return True

    if old_compression_policy != new_compression_policy:
        return True

    if old_retention_policy != new_retention_policy:
        return True

    return False


def convert_policies_to_dict(policies_obj):
    """
    Convert a TimescalePolicies object to a dictionary for comparison.
    """
    if not policies_obj:
        return None

    return {
        'compression': getattr(policies_obj, 'compression', None),
        'compression_policy': getattr(policies_obj, 'compression_policy', None),
        'retention_policy': getattr(policies_obj, 'retention_policy', None),
    }


def generate_timescale_policy_operations(autodetector):
    """
    Generate TimescaleDB policy operations for the migration autodetector.

    This function detects when TimescaleDB policies are added, changed, or removed
    from models and generates the appropriate migration operations.
    """
    # Get all models from both old and new states
    old_model_keys = set(autodetector.from_state.models.keys())
    new_model_keys = set(autodetector.to_state.models.keys())

    # Check all models in the new state for TimescaleDB policies
    # This approach focuses on detecting when policies are added to models
    print(f"DEBUG: Checking {len(new_model_keys)} models for policies")

    for app_label, model_name in new_model_keys:
        print(f"DEBUG: Checking model {app_label}.{model_name}")
        new_model_state = autodetector.to_state.models[app_label, model_name]

        # Only process models with TimescaleDB fields
        try:
            model_class = apps.get_model(app_label, model_name)
            if not has_timescale_field(model_class):
                print(f"DEBUG: {model_name} has no TimescaleDB fields")
                continue
            print(f"DEBUG: {model_name} has TimescaleDB fields")
        except LookupError:
            print(f"DEBUG: Could not get model class for {model_name}")
            continue

        # Get current policies from the model class
        current_policies = get_model_timescale_policies(model_class)
        print(f"DEBUG: Current policies for {model_name}: {current_policies}")

        # Get last applied policies from migration history
        last_applied_policies = get_last_applied_policies_from_migrations(app_label, model_name, autodetector)
        print(f"DEBUG: Last applied policies for {model_name}: {last_applied_policies}")

        # Compare policies to determine what operations are needed
        operation = None

        if current_policies and (
            hasattr(current_policies, 'compression') or
            hasattr(current_policies, 'compression_policy') or
            hasattr(current_policies, 'retention_policy')
        ):
            if not last_applied_policies:
                # New policies - generate ApplyTimescalePolicies operation
                print(f"DEBUG: {model_name} has new policies")
                operation = ApplyTimescalePolicies(
                    model_name=model_name,
                    compression_settings=getattr(current_policies, 'compression', None),
                    compression_policy=getattr(current_policies, 'compression_policy', None),
                    retention_policy=getattr(current_policies, 'retention_policy', None),
                )
            elif compare_model_policies(last_applied_policies, current_policies):
                # Policies changed - generate ApplyTimescalePolicies operation
                print(f"DEBUG: {model_name} has changed policies")
                operation = ApplyTimescalePolicies(
                    model_name=model_name,
                    compression_settings=getattr(current_policies, 'compression', None),
                    compression_policy=getattr(current_policies, 'compression_policy', None),
                    retention_policy=getattr(current_policies, 'retention_policy', None),
                )
            else:
                print(f"DEBUG: {model_name} policies unchanged")
        elif last_applied_policies:
            # Policies removed - generate RemoveTimescalePolicies operation
            print(f"DEBUG: {model_name} policies removed")
            operation = RemoveTimescalePolicies(
                model_name=model_name,
                remove_compression_policy=bool(last_applied_policies.get('compression_policy')),
                remove_retention_policy=bool(last_applied_policies.get('retention_policy')),
            )
        else:
            print(f"DEBUG: {model_name} has no policies defined")

        # Add the operation to migrations if needed
        if operation:
            print(f"DEBUG: Adding operation for {model_name}: {operation}")

            # Ensure the app has a migration entry
            if app_label not in autodetector.migrations:
                autodetector.migrations[app_label] = []
                print(f"DEBUG: Created migration entry for {app_label}")

            # Create a migration if it doesn't exist
            if not autodetector.migrations[app_label]:
                from django.db.migrations import Migration
                migration = Migration(f'timescale_policies_{model_name.lower()}', app_label)
                autodetector.migrations[app_label].append(migration)
                print(f"DEBUG: Created new migration for {app_label}")

            # Add operation to the migration
            migration = autodetector.migrations[app_label][0]
            migration.operations.append(operation)
            print(f"DEBUG: Added operation to migration: {operation}")




def patch_migration_autodetector():
    """
    Patch Django's MigrationAutodetector to include TimescaleDB policy detection.

    This function is called during Django app initialization to enable
    automatic detection of TimescaleDB policy changes.
    """
    # print("DEBUG: Patching MigrationAutodetector...")

    # Store the original _detect_changes method
    original_detect_changes = MigrationAutodetector._detect_changes

    def enhanced_detect_changes(self, convert_apps=None, graph=None):
        """Enhanced version that also detects TimescaleDB policy changes."""
        print("DEBUG: Enhanced _detect_changes called")

        # Call the original method first
        result = original_detect_changes(self, convert_apps, graph)

        # Add our TimescaleDB policy detection
        try:
            print("DEBUG: Calling generate_timescale_policy_operations")
            generate_timescale_policy_operations(self)
            print(f"DEBUG: After policy detection, migrations: {self.migrations}")
        except Exception as e:
            print(f"DEBUG: Error in policy detection: {e}")
            # Don't break migration generation if our detection fails
            pass

        # Return the result
        return result

    # Patch the method
    MigrationAutodetector._detect_changes = enhanced_detect_changes
    print("DEBUG: MigrationAutodetector patched successfully")
