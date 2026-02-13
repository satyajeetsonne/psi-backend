"""
Cloudinary image upload utility
Handles uploading images to Cloudinary cloud storage
"""

import os
import logging
import cloudinary
import cloudinary.uploader

logger = logging.getLogger(__name__)

# Configure Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)


def upload_image_to_cloudinary(file_content: bytes, filename: str) -> dict:
    """
    Upload image to Cloudinary.
    
    Args:
        file_content: Image file bytes
        filename: Original filename
        
    Returns:
        Dict with 'url' and 'public_id' keys
    """
    try:
        # Upload to Cloudinary
        result = cloudinary.uploader.upload(
            file_content,
            resource_type="auto",
            folder="outfit-images",
            public_id=filename.split('.')[0],  # Remove extension
            overwrite=False,
            tags=["outfit", "fashion"],
        )
        
        return {
            "url": result.get("secure_url"),
            "public_id": result.get("public_id"),
        }
    except Exception as e:
        logger.error(f"Failed to upload image to Cloudinary: {e}")
        raise


def delete_image_from_cloudinary(public_id: str) -> bool:
    """
    Delete image from Cloudinary.
    
    Args:
        public_id: Cloudinary public ID of the image
        
    Returns:
        True if deleted, False otherwise
    """
    try:
        result = cloudinary.uploader.destroy(public_id)
        return result.get("result") == "ok"
    except Exception:
        logger.exception(f"Failed to delete image from Cloudinary: {public_id}")
        return False
