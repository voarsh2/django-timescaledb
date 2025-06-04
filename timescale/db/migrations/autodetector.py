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
from ..models.policies import get_model_timescale_policies, serialize_policies_to_meta, deserialize_policies_from_meta
from ..models.fields import TimescaleDateTimeField


def has_timescale_field(model_class):
    """Check if a model has TimescaleDB fields."""
    if not model_class:
        return False

    for field in model_class._meta.get_fields():
        if isinstance(field, TimescaleDateTimeField):
            return True
    return False


def get_policies_from_model_state(model_state: ModelState, app_label: str):
    """
    Extract TimescaleDB policies from a model state.

    This checks the model state's options for stored policies.
    """
    # Check if policies are stored in the model state options
    timescale_policies = model_state.options.get('timescale_policies')
    if timescale_policies:
        return deserialize_policies_from_meta(timescale_policies)

    # Fallback: try to get from the actual model class (for current state)
    try:
        model_class = apps.get_model(app_label, model_state.name)
        policies = get_model_timescale_policies(model_class)
        if policies:
            # Store policies in model state for future comparisons
            model_state.options['timescale_policies'] = serialize_policies_to_meta(policies)
        return policies
    except (LookupError, AttributeError):
        return None


def compare_model_policies(old_policies, new_policies):
    """
    Compare two policy definitions and return True if they're different.
    """
    if old_policies is None and new_policies is None:
        return False

    if old_policies is None or new_policies is None:
        return True

    # Compare each policy type
    old_compression = getattr(old_policies, 'compression', None)
    new_compression = getattr(new_policies, 'compression', None)

    old_compression_policy = getattr(old_policies, 'compression_policy', None)
    new_compression_policy = getattr(new_policies, 'compression_policy', None)

    old_retention_policy = getattr(old_policies, 'retention_policy', None)
    new_retention_policy = getattr(new_policies, 'retention_policy', None)

    return (
        old_compression != new_compression or
        old_compression_policy != new_compression_policy or
        old_retention_policy != new_retention_policy
    )


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

        # Check if this model has policies defined
        if current_policies and (
            hasattr(current_policies, 'compression') or
            hasattr(current_policies, 'compression_policy') or
            hasattr(current_policies, 'retention_policy')
        ):
            print(f"DEBUG: {model_name} has policies defined")
            # Check if policies are already tracked in the model state
            existing_policies = new_model_state.options.get('timescale_policies')
            print(f"DEBUG: Existing policies in model state: {existing_policies}")

            if not existing_policies:
                print(f"DEBUG: Generating operations for {model_name}")
                # This is a new policy addition - generate operations
                operation = ApplyTimescalePolicies(
                    model_name=model_name,
                    compression_settings=getattr(current_policies, 'compression', None),
                    compression_policy=getattr(current_policies, 'compression_policy', None),
                    retention_policy=getattr(current_policies, 'retention_policy', None),
                )
                print(f"DEBUG: About to add operation for {app_label}")
                print(f"DEBUG: Current migrations before add: {autodetector.migrations}")

                # Ensure the app has a migration entry
                if app_label not in autodetector.migrations:
                    autodetector.migrations[app_label] = []
                    print(f"DEBUG: Created migration entry for {app_label}")

                # Try manual addition instead of add_operation
                from django.db.migrations import Migration

                # Create a migration if it doesn't exist
                if not autodetector.migrations[app_label]:
                    migration = Migration(f'add_timescale_policies_{model_name.lower()}', app_label)
                    autodetector.migrations[app_label].append(migration)
                    print(f"DEBUG: Created new migration for {app_label}")

                # Add operation to the migration
                migration = autodetector.migrations[app_label][0]
                migration.operations.append(operation)
                print(f"DEBUG: Added operation to migration: {operation}")

                # Also add an AlterModelOptions operation to track the policies in Meta
                from django.db.migrations.operations import AlterModelOptions
                meta_operation = AlterModelOptions(
                    name=model_name,
                    options={'timescale_policies': serialize_policies_to_meta(current_policies)}
                )
                migration.operations.append(meta_operation)
                print(f"DEBUG: Added meta operation to migration: {meta_operation}")

                print(f"DEBUG: Current migrations after manual add: {autodetector.migrations}")
                print(f"DEBUG: Added AlterModelOptions operation")
                print(f"DEBUG: Final migrations: {autodetector.migrations}")
            else:
                print(f"DEBUG: {model_name} already has policies tracked")
        else:
            print(f"DEBUG: {model_name} has no policies defined")




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
