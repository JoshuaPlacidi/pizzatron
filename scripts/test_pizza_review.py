#!/usr/bin/env python3
"""
Simple test script for review_pizza_images() function
Tests the AI pizza review functionality with sample images
Creates visual comparison of scores and reviews
Uses async processing for faster execution
"""

import os
import sys
import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path
import numpy as np
import asyncio
import concurrent.futures
import time
from PIL import Image, ImageOps
import io

# Configuration
MAX_REVIEWS = 7  # Maximum number of pizza reviews to run

# Add parent directory to path to import from src
sys.path.append(str(Path(__file__).parent.parent))

def create_test_images_if_needed():
    """Create test pizza images directory structure if it doesn't exist"""
    project_root = Path(__file__).parent.parent
    pizza_images_dir = project_root / "src" / "static" / "images" / "pizzas"
    
    # Create directory if it doesn't exist
    pizza_images_dir.mkdir(parents=True, exist_ok=True)
    
    return pizza_images_dir

def find_test_images():
    """Find existing pizza images for testing"""
    pizza_images_dir = create_test_images_if_needed()
    
    # Look for existing pizza images
    image_files = []
    for ext in ['*.jpg', '*.jpeg', '*.png']:
        image_files.extend(pizza_images_dir.glob(ext))
    
    # Convert to static paths (as expected by the function)
    static_paths = [f"/static/images/pizzas/{img.name}" for img in image_files]
    
    return static_paths[:MAX_REVIEWS]  # Use configurable limit

def load_and_fix_image(image_path: str):
    """Load and fix image orientation for display"""
    local_path = os.path.join("src", image_path.lstrip("/"))
    try:
        with open(local_path, 'rb') as f:
            image_bytes = f.read()
        
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
        print(f"Warning: Could not load image {local_path}: {e}")
        return None

def mock_review_pizza_images(pizza_image_paths: list, chef_name: str) -> dict:
    """
    Modified version of review_pizza_images that reads categories from database
    Similar to the original function but can be used independently for testing
    """
    from src.ai import client
    import base64
    
    # Get review categories from database
    from src.db import db_manager
    
    session = db_manager.get_session()
    try:
        from src.db import ReviewCategory
        categories = session.query(ReviewCategory).all()
        category_names = [cat.name for cat in categories]
    finally:
        session.close()
    
    # Fallback to hardcoded categories if database is empty
    if not category_names:
        category_names = ["Appearance", "Crust", "Cheese", "Toppings", "Overall"]
        print("Warning: No categories found in database, using fallback categories")
    
    # Load system prompt
    with open("src/prompts/pizza_review_system_prompt.txt", "r") as prompt_file:
        system_prompt = prompt_file.read().format(chef_name=chef_name)

    # Build multimodal input (text + images)
    image_parts = []
    for image_path in pizza_image_paths:
        local_path = os.path.join("src", image_path.lstrip("/"))
        try:
            with open(local_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
                # Responses API multimodal part
                image_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}"
                    }
                })
        except Exception as e:
            print(f"Warning: could not read image {local_path}: {e}")

    # Guard against no images
    if not image_parts:
        return {
            "review_summary": "No images supplied for review.",
            "scores": {cat_name: 0 for cat_name in category_names},
        }

    # Build a JSON Schema for structured output (1-5 scale)
    score_props = {cat: {"type": "integer", "minimum": 1, "maximum": 5} for cat in category_names}
    json_schema = {
        "name": "PizzaReview",
        "schema": {
            "type": "object",
            "properties": {
                "review_summary": {"type": "string"},
                "scores": {
                    "type": "object",
                    "properties": score_props,
                    "required": list(score_props.keys()),
                    "additionalProperties": False
                }
            },
            "required": ["review_summary", "scores"],
            "additionalProperties": False
        }
    }

    user_prompt = (
        f"Here is the submission from chef {chef_name}. "
        f"Please review it and produce ONLY JSON matching the schema."
    )

    # Use chat.completions.create with explicit json_schema response_format
    response = client.chat.completions.create(
        model="gpt-5",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [{"type": "text", "text": user_prompt}] + image_parts},
        ],
        response_format={"type": "json_schema", "json_schema": json_schema},
    )

    review = response.choices[0].message.content
    return json.loads(review)

async def review_pizza_async(image_path: str, chef_alias: str) -> tuple:
    """Async wrapper for pizza review function"""
    loop = asyncio.get_event_loop()
    
    def run_review():
        try:
            result = mock_review_pizza_images([image_path], f"Chef {chef_alias}")
            return result, None
        except Exception as e:
            return None, str(e)
    
    # Run the blocking function in a thread pool
    with concurrent.futures.ThreadPoolExecutor() as executor:
        result, error = await loop.run_in_executor(executor, run_review)
    
    return chef_alias, image_path, result, error

def create_visualization(results, image_data):
    """Create a matplotlib visualization showing pizza images, scores and reviews"""
    if not results:
        print("No results to visualize")
        return
    
    num_pizzas = len(results)
    
    # Set up the figure - larger to accommodate images
    fig = plt.figure(figsize=(20, 4 * num_pizzas))
    
    # Create a grid layout: images on left, heatmap in middle, reviews on right
    gs = fig.add_gridspec(num_pizzas, 4, width_ratios=[1, 2, 2, 1.5], hspace=0.3, wspace=0.3)
    
    # Extract data for plotting
    chef_names = list(results.keys())
    categories = list(results[chef_names[0]]['scores'].keys())
    
    # Create scores matrix
    scores_matrix = []
    for chef in chef_names:
        scores_matrix.append([results[chef]['scores'][cat] for cat in categories])
    scores_matrix = np.array(scores_matrix)
    
    # Main title
    fig.suptitle('PIZZATRON Pizza Review Results', fontsize=20, fontweight='bold', y=0.95)
    
    # For each pizza, create a row with: image | scores heatmap | review text | avg score
    for i, chef_name in enumerate(chef_names):
        # Column 1: Pizza Image
        ax_img = fig.add_subplot(gs[i, 0])
        if chef_name in image_data and image_data[chef_name] is not None:
            ax_img.imshow(image_data[chef_name])
            ax_img.set_title(f'{chef_name}\nPizza Image', fontweight='bold', fontsize=12)
        else:
            ax_img.text(0.5, 0.5, 'Image\nNot Found', ha='center', va='center', 
                       transform=ax_img.transAxes, fontsize=12)
            ax_img.set_title(f'{chef_name}', fontweight='bold', fontsize=12)
        ax_img.axis('off')
        
        # Column 2: Individual scores heatmap for this pizza
        ax_scores = fig.add_subplot(gs[i, 1])
        pizza_scores = scores_matrix[i:i+1]  # Single row
        im = ax_scores.imshow(pizza_scores, cmap='RdYlGn', aspect='auto', vmin=1, vmax=5)
        
        # Set ticks and labels
        ax_scores.set_xticks(range(len(categories)))
        ax_scores.set_xticklabels(categories, rotation=45, ha='right')
        ax_scores.set_yticks([0])
        ax_scores.set_yticklabels([chef_name])
        
        # Add score values
        for j in range(len(categories)):
            ax_scores.text(j, 0, scores_matrix[i, j], 
                          ha="center", va="center", color="black", fontweight='bold', fontsize=14)
        
        ax_scores.set_title('Category Scores', fontweight='bold', fontsize=12)
        
        # Column 3: Review text
        ax_review = fig.add_subplot(gs[i, 2])
        ax_review.axis('off')
        ax_review.set_title('PIZZATRON Review', fontweight='bold', fontsize=12)
        
        # Add review text with better formatting
        review_text = results[chef_name]['review_summary']
        # Simple text wrapping
        words = review_text.split()
        lines = []
        current_line = []
        for word in words:
            if len(' '.join(current_line + [word])) > 60:
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                current_line.append(word)
        if current_line:
            lines.append(' '.join(current_line))
        
        # Display wrapped text
        y_start = 0.9
        for line_idx, line in enumerate(lines):
            ax_review.text(0.05, y_start - (line_idx * 0.15), line, fontsize=11, 
                          transform=ax_review.transAxes, wrap=True, 
                          bbox=dict(boxstyle='round,pad=0.3', facecolor='lightgray', alpha=0.3))
        
        # Column 4: Average score with big number
        ax_avg = fig.add_subplot(gs[i, 3])
        avg_score = np.mean(scores_matrix[i])
        
        # Color based on score
        color = 'red' if avg_score < 2.5 else 'orange' if avg_score < 3.5 else 'green'
        
        ax_avg.text(0.5, 0.6, f'{avg_score:.1f}', ha='center', va='center', 
                   transform=ax_avg.transAxes, fontsize=48, fontweight='bold', color=color)
        ax_avg.text(0.5, 0.3, 'Average\nScore', ha='center', va='center', 
                   transform=ax_avg.transAxes, fontsize=14, fontweight='bold')
        ax_avg.text(0.5, 0.1, '(out of 5)', ha='center', va='center', 
                   transform=ax_avg.transAxes, fontsize=10)
        ax_avg.set_xlim(0, 1)
        ax_avg.set_ylim(0, 1)
        ax_avg.axis('off')
    
    # Add a small colorbar at the bottom
    cbar_ax = fig.add_axes([0.35, 0.02, 0.3, 0.02])
    cbar = plt.colorbar(im, cax=cbar_ax, orientation='horizontal')
    cbar.set_label('Score Scale (1=Poor, 5=Excellent)', fontsize=12)
    
    # Save the visualization
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_filename = f"pizza_reviews_visualization_{timestamp}.png"
    project_root = Path(__file__).parent.parent
    output_path = project_root / output_filename
    
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"📊 Visualization saved to: {output_filename}")
    
    plt.show()

async def test_pizza_review_async():
    """Test the review_pizza_images function with async processing and visual output"""
    
    # Find test images
    pizza_image_paths = find_test_images()
    
    if not pizza_image_paths:
        print("❌ No pizza images found!")
        print("Please add some pizza images to: src/static/images/pizzas/")
        print("Supported formats: .jpg, .jpeg, .png")
        return
    
    print(f"🍕 Testing pizza review with {len(pizza_image_paths)} images (MAX_REVIEWS = {MAX_REVIEWS}):")
    for path in pizza_image_paths:
        print(f"   - {path}")
    
    # Create fake chef aliases - extend list to support more reviews
    chef_aliases = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta", "Iota", "Kappa"]
    
    print(f"\n🚀 Starting parallel pizza reviews for {len(pizza_image_paths)} chefs...")
    start_time = time.time()
    
    # Create tasks for all pizza reviews
    tasks = [
        review_pizza_async(pizza_image_paths[i], chef_aliases[i])
        for i in range(len(pizza_image_paths))
    ]
    
    # Process all reviews concurrently
    results_list = await asyncio.gather(*tasks, return_exceptions=True)
    
    end_time = time.time()
    total_time = end_time - start_time
    
    print(f"⚡ Completed all reviews in {total_time:.2f} seconds!")
    
    # Process results and load images
    results = {}
    image_data = {}
    
    for result in results_list:
        if isinstance(result, Exception):
            print(f"  ✗ Exception occurred: {result}")
        else:
            chef_alias, image_path, review_result, error = result
            if error:
                print(f"  ✗ Chef {chef_alias}: {error}")
            else:
                print(f"  ✓ Chef {chef_alias}: Success!")
                print(f"    Summary: {review_result['review_summary'][:50]}...")
                chef_name = f"Chef {chef_alias}"
                results[chef_name] = review_result
                # Load the corresponding image
                image_data[chef_name] = load_and_fix_image(image_path)
    
    if results:
        avg_time_per_review = total_time / len(results)
        print(f"\n📊 Performance Summary:")
        print(f"   Total time: {total_time:.2f}s")
        print(f"   Average per review: {avg_time_per_review:.2f}s")
        print(f"   Reviews completed: {len(results)}")
        
        print(f"\n📊 Creating visualization for {len(results)} reviews...")
        create_visualization(results, image_data)
    else:
        print("\n❌ No successful reviews to visualize")
    
    print("\n🎉 Pizza review test complete!")

def test_pizza_review():
    """Synchronous wrapper for the async test function"""
    asyncio.run(test_pizza_review_async())

if __name__ == "__main__":
    test_pizza_review() 