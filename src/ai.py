from openai import OpenAI
import base64
from dotenv import load_dotenv
import json
import os
import time
from typing import List
from PIL import Image, ImageOps
import io

load_dotenv()

client = OpenAI()

def generate_chef_image(reference_image_bytes: bytes):
    import time
    
    # Process input image to ensure correct orientation
    try:
        # Open the image and fix orientation using EXIF data
        input_image = Image.open(io.BytesIO(reference_image_bytes))
        
        # Apply EXIF orientation correction
        input_image = ImageOps.exif_transpose(input_image)
        
        # Convert to RGB if needed (remove alpha channel)
        if input_image.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            background = Image.new('RGB', input_image.size, (255, 255, 255))
            if input_image.mode == 'P':
                input_image = input_image.convert('RGBA')
            background.paste(input_image, mask=input_image.split()[-1] if input_image.mode in ('RGBA', 'LA') else None)
            input_image = background
        elif input_image.mode != 'RGB':
            input_image = input_image.convert('RGB')
        
        # Save the processed image back to bytes
        processed_image_bytes = io.BytesIO()
        input_image.save(processed_image_bytes, format='PNG')
        processed_image_bytes = processed_image_bytes.getvalue()
        
    except Exception as e:
        print(f"Warning: Could not process input image orientation: {e}")
        # Fall back to original bytes if processing fails
        processed_image_bytes = reference_image_bytes
    
    with open("src/prompts/chef_image.txt", "r") as prompt_file:
        prompt = prompt_file.read()

    max_retries = 3
    retry_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            result = client.images.edit(
                model="gpt-image-1",
                image=processed_image_bytes,
                prompt=prompt,
                size="1024x1024",
            )

            image_base64 = result.data[0].b64_json
            image_bytes = base64.b64decode(image_base64)

            return image_bytes
            
        except Exception as e:
            print(f"AI generation attempt {attempt + 1} failed: {e}")
            
            if attempt == max_retries - 1:
                # Last attempt failed, re-raise the exception
                raise e
            
            # Wait before retrying
            print(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff


def review_pizza_images(pizza_image_paths: list, chef_name: str) -> dict:
    """
    Review pizza images using GPT-5 via the Responses API.

    Args:
        pizza_image_paths: List of /static image paths (e.g. "/static/images/pizzas/foo.jpg")
        chef_name: Name of the chef who made the pizza

    Returns:
        dict with keys:
          - review_summary: str
          - scores: dict of category -> int (1-5)
    """
    # Get review categories from database
    from .db import db_manager
    
    session = db_manager.get_session()
    try:
        from .db import ReviewCategory
        categories = session.query(ReviewCategory).all()
        category_names = [cat.name for cat in categories]
    finally:
        session.close()
    
    # load system prompt
    with open("src/prompts/pizza_review_system_prompt.txt", "r") as prompt_file:
        system_prompt = prompt_file.read().format(chef_name=chef_name)

    # --- build multimodal input (text + images) ---
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

    # (remove the Pydantic ResponseFormat class)

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
        response_format={"type": "json_schema", "json_schema": json_schema},    )

    review = response.choices[0].message.content

    return json.loads(review)


if __name__ == "__main__":
    review = review_pizza_images(
        ["static/images/pizzas/pizza_6_2_59a16b4a.jpeg"],
        "Chef 1",
    )
    print(review)