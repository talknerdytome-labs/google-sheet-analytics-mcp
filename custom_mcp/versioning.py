"""
Context Versioning Module for MCP

This module provides functionality to track context versions and history,
enabling the system to maintain a record of how context evolves over time.
"""

import logging
import time
from typing import Dict, List, Optional, Set, Union, Any
import json
from pathlib import Path
import uuid

from .interface import Context, ContextType

logger = logging.getLogger(__name__)


class ContextVersion:
    """
    Represents a specific version of a context.
    """
    
    def __init__(
        self,
        version_id: str,
        context: Context,
        timestamp: float,
        parent_version_id: Optional[str] = None,
        change_description: Optional[str] = None
    ):
        """
        Initialize a context version.
        
        Args:
            version_id: Unique identifier for this version
            context: The context object for this version
            timestamp: Unix timestamp when this version was created
            parent_version_id: ID of the parent version (if any)
            change_description: Description of changes from parent version
        """
        self.version_id = version_id
        self.context = context
        self.timestamp = timestamp
        self.parent_version_id = parent_version_id
        self.change_description = change_description
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.
        
        Returns:
            Dictionary representation of this version
        """
        return {
            "version_id": self.version_id,
            "context": self.context.model_dump(),
            "timestamp": self.timestamp,
            "parent_version_id": self.parent_version_id,
            "change_description": self.change_description
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContextVersion':
        """
        Create a ContextVersion from a dictionary.
        
        Args:
            data: Dictionary representation of a version
            
        Returns:
            ContextVersion object
        """
        return cls(
            version_id=data["version_id"],
            context=Context.model_validate(data["context"]),
            timestamp=data["timestamp"],
            parent_version_id=data.get("parent_version_id"),
            change_description=data.get("change_description")
        )


class ContextVersionManager:
    """
    Manages versions and history for context objects.
    
    This class provides methods to track context versions, create new versions,
    and retrieve version history.
    """
    
    def __init__(self, storage_dir: str = "./cache/context_versions"):
        """
        Initialize the context version manager.
        
        Args:
            storage_dir: Directory to store version history
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache of context versions by context ID
        self.version_cache: Dict[str, List[ContextVersion]] = {}
        
        # Cache of current version IDs by context ID
        self.current_version_ids: Dict[str, str] = {}
        
        logger.info(f"Context Version Manager initialized with storage dir: {storage_dir}")
    
    def create_initial_version(self, context: Context) -> str:
        """
        Create the initial version of a context.
        
        Args:
            context: The context object
            
        Returns:
            Version ID of the created version
        """
        context_id = context.metadata.context_id
        version_id = str(uuid.uuid4())
        
        # Create version object
        version = ContextVersion(
            version_id=version_id,
            context=context,
            timestamp=time.time(),
            parent_version_id=None,
            change_description="Initial version"
        )
        
        # Add to cache
        if context_id not in self.version_cache:
            self.version_cache[context_id] = []
            
        self.version_cache[context_id].append(version)
        self.current_version_ids[context_id] = version_id
        
        # Save to disk
        self._save_versions(context_id)
        
        return version_id
    
    def create_new_version(
        self,
        context: Context,
        change_description: str
    ) -> str:
        """
        Create a new version of a context.
        
        Args:
            context: The updated context object
            change_description: Description of changes from previous version
            
        Returns:
            Version ID of the created version
        """
        context_id = context.metadata.context_id
        
        # Check if context exists
        if context_id not in self.version_cache:
            # If not, create initial version
            return self.create_initial_version(context)
        
        # Get parent version ID
        parent_version_id = self.current_version_ids.get(context_id)
        
        # Create new version ID
        version_id = str(uuid.uuid4())
        
        # Create version object
        version = ContextVersion(
            version_id=version_id,
            context=context,
            timestamp=time.time(),
            parent_version_id=parent_version_id,
            change_description=change_description
        )
        
        # Add to cache
        self.version_cache[context_id].append(version)
        self.current_version_ids[context_id] = version_id
        
        # Save to disk
        self._save_versions(context_id)
        
        return version_id
    
    def get_version_history(self, context_id: str) -> List[ContextVersion]:
        """
        Get the version history for a context.
        
        Args:
            context_id: ID of the context
            
        Returns:
            List of ContextVersion objects in chronological order
        """
        # Check cache first
        if context_id in self.version_cache:
            versions = self.version_cache[context_id]
            # Sort by timestamp
            return sorted(versions, key=lambda v: v.timestamp)
        
        # Try to load from disk
        versions_file = self.storage_dir / f"{context_id}.json"
        if versions_file.exists():
            try:
                with open(versions_file, "r") as f:
                    versions_data = json.load(f)
                    
                # Convert to ContextVersion objects
                versions = [ContextVersion.from_dict(v) for v in versions_data]
                
                # Update cache
                self.version_cache[context_id] = versions
                
                # Update current version ID
                if versions:
                    latest_version = max(versions, key=lambda v: v.timestamp)
                    self.current_version_ids[context_id] = latest_version.version_id
                
                # Sort by timestamp
                return sorted(versions, key=lambda v: v.timestamp)
            except Exception as e:
                logger.error(f"Error loading version history for {context_id}: {e}")
        
        # No versions found
        return []
    
    def get_version(self, context_id: str, version_id: str) -> Optional[Context]:
        """
        Get a specific version of a context.
        
        Args:
            context_id: ID of the context
            version_id: ID of the version to retrieve
            
        Returns:
            Context object for the specified version, or None if not found
        """
        versions = self.get_version_history(context_id)
        
        for version in versions:
            if version.version_id == version_id:
                return version.context
                
        return None
    
    def get_current_version(self, context_id: str) -> Optional[Context]:
        """
        Get the current version of a context.
        
        Args:
            context_id: ID of the context
            
        Returns:
            Context object for the current version, or None if not found
        """
        if context_id not in self.current_version_ids:
            # Try to load versions from disk
            self.get_version_history(context_id)
            
        if context_id in self.current_version_ids:
            version_id = self.current_version_ids[context_id]
            return self.get_version(context_id, version_id)
            
        return None
    
    def _save_versions(self, context_id: str) -> bool:
        """
        Save versions to disk.
        
        Args:
            context_id: ID of the context
            
        Returns:
            True if successful, False otherwise
        """
        if context_id not in self.version_cache:
            return False
            
        versions = self.version_cache[context_id]
        versions_data = [v.to_dict() for v in versions]
        
        versions_file = self.storage_dir / f"{context_id}.json"
        
        try:
            with open(versions_file, "w") as f:
                json.dump(versions_data, f, indent=2)
                
            return True
        except Exception as e:
            logger.error(f"Error saving versions for {context_id}: {e}")
            return False
    
    def compare_versions(
        self,
        context_id: str,
        version_id1: str,
        version_id2: str
    ) -> Dict[str, Any]:
        """
        Compare two versions of a context.
        
        Args:
            context_id: ID of the context
            version_id1: ID of the first version
            version_id2: ID of the second version
            
        Returns:
            Dictionary with comparison results
        """
        # Get the two versions
        context1 = self.get_version(context_id, version_id1)
        context2 = self.get_version(context_id, version_id2)
        
        if not context1 or not context2:
            return {"error": "One or both versions not found"}
            
        # Compare metadata
        metadata_diff = {}
        for key in context1.metadata.__dict__:
            if key in ["context_id", "timestamp"]:
                continue
                
            value1 = getattr(context1.metadata, key)
            value2 = getattr(context2.metadata, key)
            
            if value1 != value2:
                metadata_diff[key] = {
                    "before": value1,
                    "after": value2
                }
        
        # Compare content
        content_diff = {}
        
        # Compare text content
        if context1.content.text != context2.content.text:
            content_diff["text"] = {
                "changed": True,
                "length_before": len(context1.content.text),
                "length_after": len(context2.content.text)
            }
        
        # Compare structured data
        if context1.content.structured_data != context2.content.structured_data:
            content_diff["structured_data"] = {
                "changed": True
            }
        
        return {
            "metadata_diff": metadata_diff,
            "content_diff": content_diff,
            "version1": {
                "id": version_id1,
                "timestamp": next(v.timestamp for v in self.version_cache[context_id] if v.version_id == version_id1)
            },
            "version2": {
                "id": version_id2,
                "timestamp": next(v.timestamp for v in self.version_cache[context_id] if v.version_id == version_id2)
            }
        }
    
    def get_version_tree(self, context_id: str) -> Dict[str, Any]:
        """
        Get the version tree for a context.
        
        Args:
            context_id: ID of the context
            
        Returns:
            Dictionary representing the version tree
        """
        versions = self.get_version_history(context_id)
        
        if not versions:
            return {}
            
        # Build tree
        tree = {}
        nodes = {}
        
        for version in versions:
            node = {
                "version_id": version.version_id,
                "timestamp": version.timestamp,
                "change_description": version.change_description,
                "children": []
            }
            
            nodes[version.version_id] = node
            
            if version.parent_version_id:
                # Add as child to parent
                if version.parent_version_id in nodes:
                    nodes[version.parent_version_id]["children"].append(node)
            else:
                # Root node
                tree = node
                
        return tree 