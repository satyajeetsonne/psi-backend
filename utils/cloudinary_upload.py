"""
Cloudinary image upload utility
Handles uploading images to Cloudinary cloud storage
"""

import os
import logging
import time
import cloudinary
import cloudinary.uploader

logger = logging.getLogger(__name__)

# Configure Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure_cdn_url=True,
)


def upload_image_to_cloudinary(file_content: bytes, filename: str) -> dict:
    """
    Upload image to Cloudinary with optimization.
    
    Args:
        file_content: Image file bytes
        filename: Original filename
        
    Returns:
        Dict with 'url' and 'public_id' keys
    """
    try:
        start_time = time.time()
        logger.info(f"Starting Cloudinary upload for {filename} ({len(file_content) / 1024:.1f}KB)...")
        
        # Upload to Cloudinary with optimizations
        result = cloudinary.uploader.upload(
            file_content,
            resource_type="auto",
            folder="outfit-images",
            public_id=filename.split('.')[0],  # Remove extension
            overwrite=False,
            tags=["outfit", "fashion"],
            use_filename=True,
            unique_filename=True,
            # Performance optimizations
            fetch_timeout=30,  # 30 second timeout
            timeout=30,  # Connection timeout
            # Transformations for faster processing
            eager=[
                {"width": 500, "height": 500, "crop": "thumb", "gravity": "face"},
                {"width": 200, "height": 200, "crop": "thumb", "gravity": "face"},
            ],
            eager_async=False,  # Wait for thumbnails (faster client response overall)
        )
        
        upload_time = time.time() - start_time
        logger.info(f"Cloudinary upload completed in {upload_time:.2f}s - URL: {result.get('secure_url')}")
        
        return {
            "url": result.get("secure_url"),
            "public_id": result.get("public_id"),
        }
    except Exception as e:
        logger.error(f"Failed to upload image to Cloudinary: {e}", exc_info=True)
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
        start_time = time.time()
        logger.info(f"Deleting image from Cloudinary: {public_id}")
        
        result = cloudinary.uploader.destroy(public_id)
        delete_time = time.time() - start_time
        success = result.get("result") == "ok"
        
        if success:
            logger.info(f"Successfully deleted image in {delete_time:.2f}s")
        else:
            logger.warning(f"Delete returned non-ok status: {result}")
        
        return success
    except Exception as e:
        logger.exception(f"Failed to delete image from Cloudinary: {public_id}")
        return False
