"""
Declarative TimescaleDB policy definitions for Django models.

This module provides a way to define TimescaleDB retention and compression
policies directly in Django model classes, which will be automatically
detected by Django's migration system.
"""
from typing import Optional, Union, List, Dict, Any
from datetime import timedelta, datetime


class TimescalePolicies:
    """
    Base class for defining TimescaleDB policies in Django models.

    Usage:
        class MyModel(models.Model):
            time = TimescaleDateTimeField(interval="1 day")
            # ... other fields

            class TimescalePolicies:
                compression = {
                    'enabled': True,
                    'compress_orderby': ['time'],
                    'compress_segmentby': ['device_id'],
                }
                compression_policy = {
                    'compress_after': '7 days',
                    'schedule_interval': '1 hour',
                }
                retention_policy = {
                    'drop_after': '90 days',
                    'schedule_interval': '1 day',
                }
    """

    def __init_subclass__(cls, **kwargs):
        """
        Called when a subclass is created. This allows us to validate
        the policy definitions at class creation time.
        """
        super().__init_subclass__(**kwargs)
        cls._validate_policies()

    @classmethod
    def _validate_policies(cls):
        """
        Validate the policy definitions to catch errors early.
        """
        # Validate compression settings
        if hasattr(cls, 'compression'):
            compression = cls.compression
            if not isinstance(compression, dict):
                raise ValueError("compression must be a dictionary")

            if 'enabled' in compression and not isinstance(compression['enabled'], bool):
                raise ValueError("compression.enabled must be a boolean")

            if 'compress_orderby' in compression:
                if not isinstance(compression['compress_orderby'], list):
                    raise ValueError("compression.compress_orderby must be a list")

            if 'compress_segmentby' in compression:
                if not isinstance(compression['compress_segmentby'], list):
                    raise ValueError("compression.compress_segmentby must be a list")

        # Validate compression policy
        if hasattr(cls, 'compression_policy'):
            policy = cls.compression_policy
            if not isinstance(policy, dict):
                raise ValueError("compression_policy must be a dictionary")

            if 'compress_after' not in policy:
                raise ValueError("compression_policy must have 'compress_after'")

        # Validate retention policy
        if hasattr(cls, 'retention_policy'):
            policy = cls.retention_policy
            if not isinstance(policy, dict):
                raise ValueError("retention_policy must be a dictionary")

            if 'drop_after' not in policy:
                raise ValueError("retention_policy must have 'drop_after'")

    @classmethod
    def get_compression_settings(cls) -> Optional[Dict[str, Any]]:
        """Get compression settings if defined."""
        return getattr(cls, 'compression', None)

    @classmethod
    def get_compression_policy(cls) -> Optional[Dict[str, Any]]:
        """Get compression policy if defined."""
        return getattr(cls, 'compression_policy', None)

    @classmethod
    def get_retention_policy(cls) -> Optional[Dict[str, Any]]:
        """Get retention policy if defined."""
        return getattr(cls, 'retention_policy', None)

    @classmethod
    def has_any_policies(cls) -> bool:
        """Check if any policies are defined."""
        return (
            hasattr(cls, 'compression') or
            hasattr(cls, 'compression_policy') or
            hasattr(cls, 'retention_policy')
        )


def get_model_timescale_policies(model_class) -> Optional[TimescalePolicies]:
    """
    Extract TimescaleDB policies from a Django model class.

    This function checks both the direct TimescalePolicies class and
    the Meta options (for migration state compatibility).

    Args:
        model_class: Django model class to inspect

    Returns:
        TimescalePolicies instance if policies are defined, None otherwise
    """
    # First check if policies are stored in Meta options (for migration state compatibility)
    if hasattr(model_class, '_meta') and hasattr(model_class._meta, 'timescale_policies'):
        return model_class._meta.timescale_policies

    # Fallback to direct TimescalePolicies class
    if hasattr(model_class, 'TimescalePolicies'):
        return model_class.TimescalePolicies
    return None


def serialize_policies_to_meta(policies_class) -> Dict[str, Any]:
    """
    Convert a TimescalePolicies class to a dictionary suitable for Meta options.

    This allows Django's migration system to track policy changes.
    """
    if not policies_class:
        return {}

    meta_dict = {}

    if hasattr(policies_class, 'compression'):
        meta_dict['compression'] = policies_class.compression

    if hasattr(policies_class, 'compression_policy'):
        meta_dict['compression_policy'] = policies_class.compression_policy

    if hasattr(policies_class, 'retention_policy'):
        meta_dict['retention_policy'] = policies_class.retention_policy

    return meta_dict


def deserialize_policies_from_meta(meta_dict: Dict[str, Any]):
    """
    Convert a Meta options dictionary back to a TimescalePolicies-like object.
    """
    if not meta_dict:
        return None

    # Create a dynamic class with the policy attributes
    class DeserializedPolicies(TimescalePolicies):
        pass

    for key, value in meta_dict.items():
        setattr(DeserializedPolicies, key, value)

    return DeserializedPolicies


def compare_policies(old_policies: Optional[TimescalePolicies],
                    new_policies: Optional[TimescalePolicies]) -> Dict[str, Any]:
    """
    Compare two policy definitions and return the differences.

    This is used by the migration autodetector to determine what changes
    need to be made.

    Args:
        old_policies: Previous policy definition
        new_policies: New policy definition

    Returns:
        Dictionary describing the changes needed
    """
    changes = {
        'compression_changes': None,
        'compression_policy_changes': None,
        'retention_policy_changes': None,
    }

    # Compare compression settings
    old_compression = old_policies.get_compression_settings() if old_policies else None
    new_compression = new_policies.get_compression_settings() if new_policies else None

    if old_compression != new_compression:
        changes['compression_changes'] = {
            'old': old_compression,
            'new': new_compression,
        }

    # Compare compression policy
    old_comp_policy = old_policies.get_compression_policy() if old_policies else None
    new_comp_policy = new_policies.get_compression_policy() if new_policies else None

    if old_comp_policy != new_comp_policy:
        changes['compression_policy_changes'] = {
            'old': old_comp_policy,
            'new': new_comp_policy,
        }

    # Compare retention policy
    old_ret_policy = old_policies.get_retention_policy() if old_policies else None
    new_ret_policy = new_policies.get_retention_policy() if new_policies else None

    if old_ret_policy != new_ret_policy:
        changes['retention_policy_changes'] = {
            'old': old_ret_policy,
            'new': new_ret_policy,
        }

    # Return None if no changes
    if all(change is None for change in changes.values()):
        return None

    return changes
