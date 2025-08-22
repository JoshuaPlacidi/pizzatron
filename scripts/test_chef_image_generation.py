#!/usr/bin/env python3
"""
Simple test script for generate_chef_image() function
Shows before/after comparison for multiple test images
Uses async processing for faster execution
"""

import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from PIL import Image, ImageOps
import io
import os
import sys
import asyncio
import concurrent.futures
import time
from pathlib import Path

# Add parent directory to path to import from src
sys.path.append(str(Path(__file__).parent.parent))
from src.ai import generate_chef_image

def load_test_images():
    """Load test images from the chefs directory"""
    # Get the project root directory (parent of scripts)
    project_root = Path(__file__).parent.parent
    chef_images_dir = project_root / "src" / "static" / "images" / "chefs"
    
    # Look for existing chef images (excluding AI generated ones)
    image_files = []
    for ext in ['*.jpg', '*.jpeg', '*.png']:
        for file in chef_images_dir.glob(ext):
            # Skip AI-generated images
            if not file.name.startswith('chef_ai_'):
                image_files.append(file)
    
    return image_files[:5]  # Take first 5 images

def fix_image_orientation(image_bytes: bytes) -> Image.Image:
    """Fix image orientation using EXIF data and ensure proper display"""
    try:
        # Open image and apply EXIF orientation correction
        image = Image.open(io.BytesIO(image_bytes))
        image = ImageOps.exif_transpose(image)
        
        # Convert to RGB if needed for consistent display
        if image.mode in ('RGBA', 'LA', 'P'):
            # Create white background for transparent images
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            if image.mode in ('RGBA', 'LA'):
                background.paste(image, mask=image.split()[-1])
            else:
                background.paste(image)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
            
        return image
    except Exception as e:
        print(f"Warning: Could not fix image orientation: {e}")
        # Fallback to basic loading
        return Image.open(io.BytesIO(image_bytes))

async def generate_chef_image_async(image_bytes: bytes, filename: str) -> tuple:
    """Async wrapper for generate_chef_image function"""
    loop = asyncio.get_event_loop()
    
    def run_generation():
        try:
            result = generate_chef_image(image_bytes)
            return result, None
        except Exception as e:
            return None, str(e)
    
    # Run the blocking function in a thread pool
    with concurrent.futures.ThreadPoolExecutor() as executor:
        result, error = await loop.run_in_executor(executor, run_generation)
    
    return filename, result, error

async def test_chef_image_generation_async():
    """Test the generate_chef_image function with async processing"""
    test_images = load_test_images()
    
    if not test_images:
        print("No test images found in src/static/images/chefs/")
        print("Please add some reference images to test with.")
        return
    
    print(f"Testing with {len(test_images)} images...")
    print("Loading original images...")
    
    # Load all original images first
    original_images = []
    image_bytes_list = []
    
    for image_path in test_images:
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
        
        # Fix orientation for display
        original_img = fix_image_orientation(image_bytes)
        original_images.append((image_path.name, original_img))
        image_bytes_list.append((image_bytes, image_path.name))
    
    # Set up matplotlib figure - horizontal layout (2 rows, N columns)
    # 50% smaller than original: was (12, 4 * len), now (6 * len, 4)
    fig, axes = plt.subplots(2, len(test_images), figsize=(3 * len(test_images), 4))
    if len(test_images) == 1:
        axes = axes.reshape(-1, 1)
    
    fig.suptitle('Chef Image Generation Test: Before vs After', fontsize=14, fontweight='bold')
    
    # Display all original images first (top row)
    for i, (filename, original_img) in enumerate(original_images):
        axes[0, i].imshow(original_img)
        axes[0, i].set_title(f'Original: {filename}', fontweight='bold', fontsize=10)
        axes[0, i].axis('off')
        
        # Set placeholder for AI image (bottom row)
        axes[1, i].text(0.5, 0.5, 'Generating...', 
                       ha='center', va='center', transform=axes[1, i].transAxes,
                       bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.3))
        axes[1, i].set_title('AI Generated - Processing...', fontweight='bold', color='orange', fontsize=10)
        axes[1, i].axis('off')
    
    # Show the plot with originals and placeholders
    plt.draw()
    plt.pause(0.1)
    
    # Start async processing
    print("🚀 Starting parallel AI image generation...")
    start_time = time.time()
    
    # Create tasks for all images
    tasks = [
        generate_chef_image_async(image_bytes, filename) 
        for image_bytes, filename in image_bytes_list
    ]
    
    # Process all images concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    end_time = time.time()
    total_time = end_time - start_time
    
    print(f"⚡ Completed all generations in {total_time:.2f} seconds!")
    
    # Update the plot with results (bottom row)
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"  ✗ {original_images[i][0]}: {result}")
            axes[1, i].clear()
            axes[1, i].text(0.5, 0.5, f'Error:\n{str(result)}', 
                           ha='center', va='center', transform=axes[1, i].transAxes,
                           bbox=dict(boxstyle='round', facecolor='red', alpha=0.3))
            axes[1, i].set_title('Failed', fontweight='bold', color='red', fontsize=10)
            axes[1, i].axis('off')
        else:
            filename, ai_image_bytes, error = result
            if error:
                print(f"  ✗ {filename}: {error}")
                axes[1, i].clear()
                axes[1, i].text(0.5, 0.5, f'Error:\n{error}', 
                               ha='center', va='center', transform=axes[1, i].transAxes,
                               bbox=dict(boxstyle='round', facecolor='red', alpha=0.3))
                axes[1, i].set_title('Failed', fontweight='bold', color='red', fontsize=10)
                axes[1, i].axis('off')
            else:
                print(f"  ✓ {filename}: Success!")
                # Fix orientation for AI generated image too
                ai_img = fix_image_orientation(ai_image_bytes)
                axes[1, i].clear()
                axes[1, i].imshow(ai_img)
                axes[1, i].set_title('AI Generated', fontweight='bold', color='green', fontsize=10)
                axes[1, i].axis('off')
    
    plt.tight_layout()
    plt.draw()
    
    # Save the plot as PNG
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_filename = f"chef_image_test_results_{timestamp}.png"
    
    # Get the project root directory (parent of scripts)
    project_root = Path(__file__).parent.parent
    output_path = project_root / output_filename
    
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    
    avg_time_per_image = total_time / len(test_images)
    print(f"\n📊 Performance Summary:")
    print(f"   Total time: {total_time:.2f}s")
    print(f"   Average per image: {avg_time_per_image:.2f}s")
    print(f"   Images processed: {len(test_images)}")
    print(f"\n💾 Results saved to: {output_filename}")
    print("\nTest complete! Review the results to improve your prompt.")
    
    # Keep the plot open
    plt.show()

def test_chef_image_generation():
    """Synchronous wrapper for the async test function"""
    asyncio.run(test_chef_image_generation_async())

if __name__ == "__main__":
    test_chef_image_generation()
